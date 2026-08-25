"""Order lifecycle.

    draft -> awaiting_payment -> paid -> rendering -> delivered
                                   |                     |
                                   +------> failed       +--> refunded

The order in which those transitions happen is deliberate and load-bearing:

PHOTOS BEFORE PAYMENT. The customer uploads first, we validate the set, and only
then do we take money. Every other ordering means occasionally charging someone
whose photos cannot make a film -- which is a refund, an apology, and the one
review that says "they took my money and then told me no".
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from . import catalog_bridge as cat
from .db import Database, new_id, now

LIVE = ("awaiting_payment", "paid", "rendering")
TERMINAL = ("delivered", "failed", "refunded")

# Only these moves are legal. Anything else is a bug, and it fails loudly rather
# than leaving an order in a state no code path expects.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("awaiting_payment", "failed"),
    "awaiting_payment": ("paid", "failed"),
    "paid": ("rendering", "failed", "refunded"),
    "rendering": ("delivered", "failed"),
    "delivered": ("refunded",),
    "failed": ("paid",),          # a retried payment can revive a failed draft
    "refunded": (),
}


class OrderError(Exception):
    pass


@dataclass(frozen=True)
class Readiness:
    ok: bool
    photos: int
    required: int
    problems: tuple[str, ...]


def create(db: Database, customer_id: str, sku_id: str) -> str:
    s = cat.get(sku_id)
    oid = new_id("ord")
    with db.tx() as c:
        ref = c.execute("SELECT referred_by FROM customers WHERE id = ?",
                        (customer_id,)).fetchone()
        if ref is None:
            raise OrderError("no such customer")
        c.execute("INSERT INTO orders(id, customer_id, sku, vertical, price_cents,"
                  " status, brief, referred_by, created_at)"
                  " VALUES(?,?,?,?,?,?,?,?,?)",
                  (oid, customer_id, sku_id, s.vertical,
                   cat.price_cents(sku_id), "draft", "{}",
                   ref["referred_by"], now()))
        db.log(c, "order.created", oid, sku_id)
    return oid


def get(db: Database, order_id: str, *, customer_id: str | None = None):
    with db.tx() as c:
        row = c.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if row is None:
        return None
    if customer_id is not None and row["customer_id"] != customer_id:
        return None          # not found, not forbidden: do not confirm it exists
    return row


def set_brief(db: Database, order_id: str, brief: dict) -> None:
    with db.tx() as c:
        c.execute("UPDATE orders SET brief = ? WHERE id = ? AND status IN"
                  " ('draft','awaiting_payment')",
                  (json.dumps(brief, ensure_ascii=False), order_id))


def transition(conn: sqlite3.Connection, db: Database, order_id: str,
               to: str) -> None:
    row = conn.execute("SELECT status FROM orders WHERE id = ?",
                       (order_id,)).fetchone()
    if row is None:
        raise OrderError("no such order")
    frm = row["status"]
    if to == frm:
        return                               # idempotent: webhook redelivery
    if to not in TRANSITIONS.get(frm, ()):
        raise OrderError(f"cannot go {frm} -> {to}")
    stamp = {"paid": "paid_at", "delivered": "delivered_at"}.get(to)
    if stamp:
        conn.execute(f"UPDATE orders SET status = ?, {stamp} = ? WHERE id = ?",
                     (to, now(), order_id))
    else:
        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (to, order_id))
    db.log(conn, f"order.{to}", order_id, frm)


def readiness(db: Database, order_id: str) -> Readiness:
    """Can this order actually be made? Answered BEFORE payment, every time."""
    o = get(db, order_id)
    if o is None:
        return Readiness(False, 0, 0, ("no such order",))
    need = cat.required_photos(o["sku"])
    with db.tx() as c:
        n = c.execute("SELECT count(*) FROM uploads WHERE order_id = ?",
                      (order_id,)).fetchone()[0]
        brief = json.loads(o["brief"] or "{}")
    problems: list[str] = []
    if n < need:
        problems.append(f"{need} photographs minimum — you have {n}")
    missing = [q for q in cat.intake_for(o["vertical"])
               if not str(brief.get(q, "")).strip()]
    if missing:
        problems.append("still needed: " + "; ".join(missing))
    return Readiness(not problems, n, need, tuple(problems))


def list_for_customer(db: Database, customer_id: str) -> list:
    with db.tx() as c:
        return c.execute(
            "SELECT * FROM orders WHERE customer_id = ? ORDER BY created_at DESC",
            (customer_id,)).fetchall()


def deliverables(db: Database, order_id: str) -> list:
    with db.tx() as c:
        return c.execute("SELECT * FROM deliverables WHERE order_id = ?"
                         " ORDER BY kind", (order_id,)).fetchall()
