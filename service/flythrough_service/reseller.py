"""Reseller programme: 25% of everything a referred customer ever spends.

CONFIRMED by the account holder. Lifetime, not first-order -- which is the whole
recruiting pitch, and also the thing that makes the attribution rules matter.

Attribution is FIRST-TOUCH and PERMANENT. Whoever introduced a customer keeps
them. Last-touch would mean a second reseller could steal an account by getting
one link in front of an existing customer, and the resulting arguments cost more
than the commission ever would.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
from dataclasses import dataclass

from .db import Database, new_id, now

# Unambiguous when spoken over the phone or typed off a business card: no
# 0/O, 1/I/L. A referral code that gets mistyped is a commission that silently
# goes to nobody.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_RE = re.compile(r"^[A-Z2-9]{6,12}$")


class ResellerError(Exception):
    pass


@dataclass(frozen=True)
class Ledger:
    accrued_cents: int
    payable_cents: int
    paid_cents: int
    orders: int

    @property
    def lifetime_cents(self) -> int:
        return self.accrued_cents + self.payable_cents + self.paid_cents


CODE_LEN = 8


def make_code(name: str) -> str:
    """Always exactly CODE_LEN characters.

    The stem is whatever of the person's name survives the alphabet, which can
    be almost nothing -- "Olivia Lloyd" keeps only the V, because O, I and L are
    all ambiguous. Padding to a fixed length rather than appending a fixed
    number of random characters is what stops that producing a 5-character code
    the validator then rejects, leaving them unable to enrol at all.
    """
    stem = "".join(ch for ch in re.sub(r"[^A-Za-z]", "", name).upper()
                   if ch in ALPHABET)[:4]
    pad = CODE_LEN - len(stem)
    return stem + "".join(secrets.choice(ALPHABET) for _ in range(pad))


def enrol(db: Database, email: str, name: str, *, rate: float,
          lifetime: bool = True, code: str | None = None) -> str:
    from .auth import normalise_email
    email = normalise_email(email)
    with db.tx() as c:
        existing = c.execute("SELECT id FROM resellers WHERE email = ?",
                             (email,)).fetchone()
        if existing:
            raise ResellerError("that address is already enrolled")
        for _ in range(20):
            candidate = (code or make_code(name)).upper()
            if not CODE_RE.match(candidate):
                raise ResellerError("that code is not usable")
            rid = new_id("res")
            try:
                c.execute("INSERT INTO resellers(id,email,name,code,rate,lifetime,"
                          "created_at) VALUES(?,?,?,?,?,?,?)",
                          (rid, email, name, candidate, rate, int(lifetime), now()))
            except sqlite3.IntegrityError:
                if code:
                    raise ResellerError("that code is taken")
                continue      # generated collision -- try another
            db.log(c, "reseller.enrolled", rid, candidate)
            return rid
    raise ResellerError("could not allocate a code")


def by_code(db: Database, code: str):
    if not code:
        return None
    with db.tx() as c:
        return c.execute("SELECT * FROM resellers WHERE code = ?",
                         (code.strip().upper(),)).fetchone()


def attribute(db: Database, customer_id: str, code: str) -> bool:
    """First touch wins, permanently. Returns True only if this call set it."""
    r = by_code(db, code)
    if r is None:
        return False
    with db.tx() as c:
        cur = c.execute("SELECT referred_by FROM customers WHERE id = ?",
                        (customer_id,)).fetchone()
        if cur is None or cur["referred_by"]:
            return False          # already attributed -- never reassign
        c.execute("UPDATE customers SET referred_by = ? WHERE id = ?",
                  (r["id"], customer_id))
        db.log(c, "reseller.attributed", customer_id, r["code"])
    return True


def accrue(conn: sqlite3.Connection, db: Database, order_id: str) -> int:
    """Record commission for a paid order. Called INSIDE the payment
    transaction, so a commission cannot exist for an order that did not pay and
    a paid order cannot silently skip its commission.

    Returns cents accrued (0 if the order has no reseller)."""
    o = conn.execute(
        "SELECT o.id, o.price_cents, o.status, o.customer_id, c.referred_by"
        " FROM orders o JOIN customers c ON c.id = o.customer_id"
        " WHERE o.id = ?", (order_id,)).fetchone()
    if o is None or o["status"] != "paid" or not o["referred_by"]:
        return 0
    r = conn.execute("SELECT * FROM resellers WHERE id = ?",
                     (o["referred_by"],)).fetchone()
    if r is None:
        return 0
    if not r["lifetime"]:
        prior = conn.execute(
            "SELECT count(*) FROM commissions WHERE reseller_id = ? AND order_id IN"
            " (SELECT id FROM orders WHERE customer_id = ?)",
            (r["id"], o["customer_id"])).fetchone()[0]
        if prior:
            return 0              # first-order-only programme, already paid once
    amount = round(o["price_cents"] * r["rate"])
    try:
        conn.execute("INSERT INTO commissions(id,reseller_id,order_id,amount_cents,"
                     "rate,status,created_at) VALUES(?,?,?,?,?,?,?)",
                     (new_id("com"), r["id"], order_id, amount, r["rate"],
                      "accrued", now()))
    except sqlite3.IntegrityError:
        return 0                  # already accrued: webhook redelivery
    db.log(conn, "commission.accrued", r["id"], f"{order_id} {amount}")
    return amount


def reverse(conn: sqlite3.Connection, db: Database, order_id: str) -> int:
    """A refunded order must not pay a commission. Reversal is a status change,
    never a delete -- the ledger is the record of what happened, including the
    things that un-happened."""
    row = conn.execute("SELECT id, reseller_id, amount_cents, status FROM"
                       " commissions WHERE order_id = ?", (order_id,)).fetchone()
    if row is None or row["status"] in ("reversed", "paid"):
        return 0
    conn.execute("UPDATE commissions SET status = 'reversed' WHERE id = ?",
                 (row["id"],))
    db.log(conn, "commission.reversed", row["reseller_id"], order_id)
    return row["amount_cents"]


def ledger(db: Database, reseller_id: str, *, payout_minimum_cents: int) -> Ledger:
    with db.tx() as c:
        rows = c.execute(
            "SELECT status, COALESCE(sum(amount_cents),0) amt, count(*) n"
            " FROM commissions WHERE reseller_id = ? GROUP BY status",
            (reseller_id,)).fetchall()
    by = {r["status"]: (r["amt"], r["n"]) for r in rows}
    accrued = by.get("accrued", (0, 0))[0]
    paid = by.get("paid", (0, 0))[0]
    orders = sum(n for _, n in by.values())
    payable = accrued if accrued >= payout_minimum_cents else 0
    return Ledger(accrued_cents=accrued - payable, payable_cents=payable,
                  paid_cents=paid, orders=orders)
