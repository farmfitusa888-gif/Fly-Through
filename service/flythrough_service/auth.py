"""Magic-link authentication. No passwords, anywhere.

A password on a service like this is pure liability: it is a thing to store, to
hash correctly, to reset, to rate-limit, to breach. The customer already proved
control of their email address by receiving the order confirmation, so the email
IS the credential. One fewer secret in the database, and no reset flow to get
wrong.

Every token is stored as a sha256 hash. A stolen database backup must not be a
stack of working logins.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import dataclass

from .db import Database, new_id, now


class AuthError(Exception):
    pass


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalise_email(raw: str) -> str:
    e = (raw or "").strip().lower()
    if e.count("@") != 1 or e.startswith("@") or e.endswith("@") or " " in e:
        raise AuthError("that does not look like an email address")
    if "." not in e.split("@", 1)[1]:
        raise AuthError("that does not look like an email address")
    return e


@dataclass(frozen=True)
class Principal:
    """Who is making the request. Exactly one of these is set."""
    customer_id: str | None = None
    reseller_id: str | None = None

    @property
    def is_reseller(self) -> bool:
        return self.reseller_id is not None


def issue_login_token(db: Database, email: str, *, ttl_s: int) -> str:
    email = normalise_email(email)
    token = secrets.token_urlsafe(32)
    with db.tx() as c:
        # One live link per address. Requesting a new one invalidates the old,
        # so a link forwarded or left in an old thread stops working the moment
        # the real owner asks for another.
        c.execute("DELETE FROM login_tokens WHERE email = ?", (email,))
        c.execute("INSERT INTO login_tokens(token_hash, email, expires_at)"
                  " VALUES(?,?,?)", (_hash(token), email, now() + ttl_s))
        db.log(c, "login.requested", email)
    return token


def redeem_login_token(db: Database, token: str, *, session_ttl_s: int) -> tuple[str, Principal]:
    """Returns (session_token, principal). Single use."""
    th = _hash(token)
    with db.tx() as c:
        row = c.execute(
            "SELECT email, expires_at, used_at FROM login_tokens WHERE token_hash = ?",
            (th,)).fetchone()
        if row is None:
            raise AuthError("that link is not valid")
        if row["used_at"] is not None:
            raise AuthError("that link has already been used")
        if row["expires_at"] < now():
            raise AuthError("that link has expired — ask for a new one")
        email = row["email"]
        c.execute("UPDATE login_tokens SET used_at = ? WHERE token_hash = ?",
                  (now(), th))

        # A reseller and a customer can share an address; the reseller identity
        # wins for login because it is the strictly larger dashboard.
        res = c.execute("SELECT id FROM resellers WHERE email = ?", (email,)).fetchone()
        if res is not None:
            principal = Principal(reseller_id=res["id"])
        else:
            cust = c.execute("SELECT id FROM customers WHERE email = ?",
                             (email,)).fetchone()
            if cust is None:
                cid = new_id("cus")
                c.execute("INSERT INTO customers(id, email, created_at)"
                          " VALUES(?,?,?)", (cid, email, now()))
            else:
                cid = cust["id"]
            principal = Principal(customer_id=cid)

        session = secrets.token_urlsafe(32)
        c.execute("INSERT INTO sessions(token_hash, customer_id, reseller_id,"
                  " expires_at, created_at) VALUES(?,?,?,?,?)",
                  (_hash(session), principal.customer_id, principal.reseller_id,
                   now() + session_ttl_s, now()))
        db.log(c, "login.redeemed", email)
    return session, principal


def resolve_session(db: Database, session_token: str | None) -> Principal | None:
    if not session_token:
        return None
    with db.tx() as c:
        row = c.execute(
            "SELECT customer_id, reseller_id, expires_at FROM sessions"
            " WHERE token_hash = ?", (_hash(session_token),)).fetchone()
        if row is None or row["expires_at"] < now():
            return None
        return Principal(customer_id=row["customer_id"],
                         reseller_id=row["reseller_id"])


def end_session(db: Database, session_token: str) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM sessions WHERE token_hash = ?",
                  (_hash(session_token),))


def purge_expired(db: Database) -> int:
    with db.tx() as c:
        a = c.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),)).rowcount
        b = c.execute("DELETE FROM login_tokens WHERE expires_at < ?", (now(),)).rowcount
    return a + b


def csrf_token(session_token: str, secret: str) -> str:
    """Derived from the session, so it needs no storage and dies with it."""
    return hmac.new(secret.encode(), session_token.encode(), hashlib.sha256).hexdigest()


def csrf_ok(session_token: str, secret: str, presented: str) -> bool:
    return hmac.compare_digest(csrf_token(session_token, secret), presented or "")
