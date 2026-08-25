"""Stripe webhooks: the only thing that may mark an order paid.

Nothing on the success page changes an order's status. A redirect is a URL the
customer controls -- appending ?paid=1 to it must never be worth anything. Money
is recognised on a signed webhook, or not at all.

Three properties matter more than anything else here, and each is enforced
rather than intended:

  1. SIGNATURE FIRST. Verify before parsing. An unsigned body is not JSON we
     failed to trust, it is bytes we never looked at.
  2. EXACTLY ONCE. Stripe redelivers on any non-2xx, and on its own schedule.
     Every event id is recorded, and the recording happens in the SAME
     transaction as the effect, so "processed" and "did the thing" cannot
     disagree.
  3. 2xx ON ANYTHING WE UNDERSTAND. A 500 makes Stripe retry, forever, on an
     event that will never succeed. Unknown types are acknowledged and ignored.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from . import orders, reseller
from .db import Database, now


class WebhookError(Exception):
    """Bad signature or malformed payload. Answered with 400, never retried."""


def sign(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Build a Stripe-Signature header. Used by the tests, and it is the same
    code path the verifier checks against -- so a test that passes proves the
    verifier accepts genuine Stripe signatures, not merely our own."""
    ts = int(time.time()) if timestamp is None else timestamp
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + payload,
                   hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def verify(payload: bytes, header: str, secret: str, *, tolerance_s: int = 300) -> dict:
    if not secret:
        raise WebhookError("no webhook secret configured")
    parts = dict(p.split("=", 1) for p in (header or "").split(",") if "=" in p)
    try:
        ts = int(parts["t"])
    except (KeyError, ValueError):
        raise WebhookError("malformed signature header") from None
    # Replay window. Without it a captured request stays valid forever.
    if abs(int(time.time()) - ts) > tolerance_s:
        raise WebhookError("signature timestamp outside tolerance")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload,
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, parts.get("v1", "")):
        raise WebhookError("signature mismatch")
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        raise WebhookError("payload is not JSON") from None


def _already(conn, event_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM processed_webhooks WHERE event_id = ?",
                       (event_id,)).fetchone()
    return row is not None


def handle(db: Database, event: dict) -> tuple[str, str | None]:
    """Apply one verified event.

    Returns (description_for_the_log, order_id_that_just_became_paid). The
    caller enqueues the render AFTER this returns, never inside: a worker that
    picks the job up before the payment transaction commits would render an
    order the database does not yet agree was paid.
    """
    eid = event.get("id") or ""
    etype = event.get("type") or ""
    obj = (event.get("data") or {}).get("object") or {}
    if not eid:
        raise WebhookError("event has no id")

    with db.tx() as c:
        if _already(c, eid):
            return f"{etype} already processed", None
        c.execute("INSERT INTO processed_webhooks(event_id, at) VALUES(?,?)",
                  (eid, now()))

        if etype == "checkout.session.completed":
            # Only 'paid' counts. A completed session in another payment_status
            # is an async method still clearing, and marking it paid would ship
            # a film before the money settled.
            if obj.get("payment_status") != "paid":
                return (f"{etype} ignored (payment_status="
                        f"{obj.get('payment_status')})"), None
            oid = (obj.get("client_reference_id")
                   or (obj.get("metadata") or {}).get("order_id"))
            if not oid:
                return f"{etype} carries no order reference", None
            row = c.execute("SELECT id, status, price_cents FROM orders"
                            " WHERE id = ?", (oid,)).fetchone()
            if row is None:
                return f"{etype} for unknown order {oid}", None

            # Charged amount must match what we quoted. If they disagree,
            # someone has edited a Payment Link, and shipping the film would be
            # doing the work for whatever price the link happened to say.
            amount = obj.get("amount_total")
            if amount is not None and int(amount) != row["price_cents"]:
                db.log(c, "payment.amount_mismatch", oid,
                       f"charged {amount} expected {row['price_cents']}")
                return f"{etype} amount mismatch on {oid}", None

            c.execute("UPDATE orders SET stripe_ref = COALESCE(stripe_ref, ?)"
                      " WHERE id = ?", (obj.get("id"), oid))
            if row["status"] in ("draft", "awaiting_payment", "failed"):
                if row["status"] == "draft":
                    orders.transition(c, db, oid, "awaiting_payment")
                orders.transition(c, db, oid, "paid")
            reseller.accrue(c, db, oid)
            return f"order {oid} paid", oid

        if etype in ("charge.refunded", "checkout.session.async_payment_failed"):
            oid = ((obj.get("metadata") or {}).get("order_id")
                   or obj.get("client_reference_id"))
            if not oid:
                return f"{etype} carries no order reference", None
            if etype == "charge.refunded":
                try:
                    orders.transition(c, db, oid, "refunded")
                except orders.OrderError:
                    pass          # already terminal; the reversal still applies
                reseller.reverse(c, db, oid)
                return f"order {oid} refunded", None
            try:
                orders.transition(c, db, oid, "failed")
            except orders.OrderError:
                pass
            return f"order {oid} payment failed", None

        return f"{etype} ignored", None
