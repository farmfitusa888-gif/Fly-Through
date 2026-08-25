"""Rate limiting, in the database rather than in memory.

In-process counters are wrong here for two reasons that both bite in production:
uvicorn workers do not share memory, so N workers means N times the limit; and a
restart forgets everything, so a restart loop is an unlimited endpoint.

The events table is already append-only and already indexed by (subject, at),
which is exactly the shape a sliding window needs. No new table, no Redis.

The endpoint that matters most is /login. Without a limit anyone can post a
stranger's address in a loop and have us mail-bomb someone who is not even a
customer -- a way to get the sending domain blocklisted using our own service.
"""

from __future__ import annotations

from dataclasses import dataclass

from .db import Database, now


@dataclass(frozen=True)
class Limit:
    count: int
    per_seconds: int

    def __str__(self) -> str:
        unit = ("second" if self.per_seconds == 1 else
                "minute" if self.per_seconds == 60 else
                "hour" if self.per_seconds == 3600 else
                f"{self.per_seconds} seconds")
        return f"{self.count} per {unit}"


# Deliberately generous for a human and useless for a script. A real person asks
# for a sign-in link once, maybe three times if their mail is slow.
LOGIN_PER_EMAIL = Limit(5, 3600)
LOGIN_PER_IP = Limit(20, 3600)
ENROL_PER_IP = Limit(5, 3600)
UPLOAD_PER_ORDER = Limit(60, 3600)


class TooMany(Exception):
    """Carries a message meant for the person, not a status code."""


def hit(db: Database, kind: str, subject: str, limit: Limit) -> None:
    """Record an attempt; raise if the window is already full.

    Counts BEFORE inserting, so the limit is the number of successful passes and
    not one more than that.
    """
    if not subject:
        return
    since = now() - limit.per_seconds
    key = f"rate.{kind}"
    with db.tx() as c:
        used = c.execute(
            "SELECT count(*) FROM events WHERE kind = ? AND subject = ? AND at >= ?",
            (key, subject, since)).fetchone()[0]
        if used >= limit.count:
            raise TooMany(
                "That has been tried too many times. Wait an hour and try again "
                "— or email us and a human will sort it out.")
        c.execute("INSERT INTO events(at, kind, subject) VALUES(?,?,?)",
                  (now(), key, subject))


def client_ip(request) -> str:
    """Behind a proxy the socket address is the proxy. Trust the LAST hop of
    X-Forwarded-For, which is the one our own proxy appended -- earlier entries
    are supplied by the client and are trivially forged."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[-1].strip()
    return getattr(getattr(request, "client", None), "host", "") or ""


def sweep(db: Database, older_than_s: int = 7 * 24 * 3600) -> int:
    """Rate rows are the only events we are allowed to delete: they are counters,
    not history. Everything else in that table is the audit trail."""
    with db.tx() as c:
        return c.execute("DELETE FROM events WHERE kind LIKE 'rate.%' AND at < ?",
                         (now() - older_than_s,)).rowcount
