"""Transactional email that is not a login link.

Kept apart from mail.py, which is the transport. This module decides WHAT gets
said and WHEN, and it is deliberately short: four messages, no marketing, no
digest, no "we miss you". Every one of them is something the customer would be
annoyed not to receive.

Each send is recorded in `events` before it goes out, keyed by order and kind,
so a retried job or a redelivered webhook cannot send the same notice twice.
Nobody forgives being emailed three times about one order.
"""

from __future__ import annotations

from .db import Database, now

DELIVERED = "notify.delivered"
FAILED = "notify.failed"
RECEIPT = "notify.receipt"
OUTCOME = "notify.outcome"


def _once(db: Database, kind: str, order_id: str) -> bool:
    """True if this notice has not been sent for this order. Claims it if so."""
    with db.tx() as c:
        seen = c.execute(
            "SELECT 1 FROM events WHERE kind = ? AND subject = ? LIMIT 1",
            (kind, order_id)).fetchone()
        if seen:
            return False
        c.execute("INSERT INTO events(at, kind, subject) VALUES(?,?,?)",
                  (now(), kind, order_id))
    return True


def _customer_email(db: Database, order_id: str) -> str | None:
    with db.tx() as c:
        row = c.execute(
            "SELECT cu.email FROM orders o JOIN customers cu ON cu.id = o.customer_id"
            " WHERE o.id = ?", (order_id,)).fetchone()
    return row["email"] if row else None


def receipt(db: Database, mailer, settings, order_id: str, *, what: str,
            amount_cents: int) -> bool:
    to = _customer_email(db, order_id)
    if not to or not _once(db, RECEIPT, order_id):
        return False
    mailer.send(to, f"{settings.brand} — order received",
                f"We have your {what} and your photographs.\n\n"
                f"Paid: ${amount_cents / 100:,.2f}\n\n"
                f"Nothing else is needed from you. We will email again the "
                f"moment the film is ready.\n\n"
                f"{settings.base_url}/orders\n")
    return True


def delivered(db: Database, mailer, settings, order_id: str, *, what: str,
              kinds: list[str]) -> bool:
    """The one message the whole service exists to send."""
    to = _customer_email(db, order_id)
    if not to or not _once(db, DELIVERED, order_id):
        return False
    files = "\n".join(f"  {k}: {settings.base_url}/orders/{order_id}/file/{k}"
                      for k in kinds)
    mailer.send(to, f"{settings.brand} — your film is ready",
                f"Your {what} is done.\n\n{files}\n\n"
                f"Everything is also on {settings.base_url}/orders, and it stays "
                f"there — you can re-download any time.\n\n"
                f"You own this outright. Use it wherever you like.\n")
    return True


def failed(db: Database, mailer, settings, order_id: str, *, what: str) -> bool:
    """Say so, early, in plain words. A customer who has to ask what happened to
    the film they paid for is already a refund."""
    to = _customer_email(db, order_id)
    if not to or not _once(db, FAILED, order_id):
        return False
    mailer.send(to, f"{settings.brand} — a problem with your order",
                f"Your {what} did not come out, and rather than send you "
                f"something we would not want to sign, we have stopped and are "
                f"looking at it by hand.\n\n"
                f"You do not need to do anything. We will either send you the "
                f"finished film or refund you in full — reply to this email if "
                f"you would rather just have the refund now.\n\n"
                f"{settings.contact_email}\n")
    return True


def outcome_request(db: Database, mailer, settings, order_id: str, *,
                    what: str) -> bool:
    """The V3 asset, asked for in one sentence.

    This is the only email here that is not strictly transactional, which is
    exactly why it is one question with a one-word answer and no link to a
    survey. What comes back is worth more than any feature on the roadmap: after
    a couple of hundred of these, the brief that produces a faster sale is
    knowable rather than guessable.
    """
    to = _customer_email(db, order_id)
    if not to or not _once(db, OUTCOME, order_id):
        return False
    mailer.send(to, f"{settings.brand} — did it sell?",
                f"One question about your {what}, and it genuinely helps: "
                f"did it sell?\n\n"
                f"Just reply with a word — sold, still listed, withdrawn — and "
                f"roughly how long it took. We use it to work out which way of "
                f"cutting a film actually moves a listing, and everyone who "
                f"answers gets the benefit of everyone else's answers.\n\n"
                f"Nothing else needed. Thank you.\n")
    return True
