"""Did it sell?

One question, asked once, thirty days after delivery. The answer is stored
against the brief that produced the film.

This is the compounding asset. Model quality converges and is a subscription
anyone can buy; a competitor with a better renderer still cannot tell a customer
which opening frame moves a listing in their price band, because they have never
delivered a film and asked what happened next. That only accrues to whoever
bothers to ask.

It is deliberately tiny. One question, a one-word answer, no survey, no
dashboard. The value is in the join between the answer and the brief, not in the
collecting.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .db import Database, now

RESULTS = ("sold", "listed", "withdrawn", "unknown")
ASK_AFTER_S = 30 * 24 * 3600

# Words people actually reply with, mapped to the four we store. Matched on WORD
# BOUNDARIES, never as substrings: a bare "no" matched anywhere lit up inside
# "dunno" and recorded an unparseable reply as a confident "still listed". Short
# synonyms are exactly the ones that do this, and they are also the ones people
# actually type.
#
# Anything unmatched becomes "unknown" rather than being dropped -- a reply we
# could not parse is still evidence they engaged, and the raw text is kept so a
# human can read it.
SYNONYMS: tuple[tuple[str, str], ...] = (
    ("under contract", "sold"), ("off ?market", "withdrawn"),
    ("still listed", "listed"), ("still on", "listed"), ("on ?market", "listed"),
    ("sold", "sold"), ("sells?", "sold"), ("closed", "sold"),
    ("pending", "sold"), ("accepted", "sold"), ("went", "sold"),
    ("withdrew", "withdrawn"), ("withdrawn", "withdrawn"),
    ("expired", "withdrawn"), ("cancell?ed", "withdrawn"),
    ("pulled", "withdrawn"), ("delisted", "withdrawn"),
    ("listed", "listed"), ("active", "listed"), ("nope", "listed"),
    ("not yet", "listed"),
)

class OutcomeError(Exception):
    pass


@dataclass(frozen=True)
class Insight:
    """What we can say, and how confident we are allowed to sound.

    `samples` is on the object because a finding from four listings is a
    coincidence and must never be presented as a pattern. The threshold lives
    with the number so it cannot be dropped by a caller in a hurry.
    """
    dimension: str
    value: str
    median_days: float
    samples: int

    @property
    def trustworthy(self) -> bool:
        return self.samples >= MIN_SAMPLES


MIN_SAMPLES = 12


def parse(reply: str) -> tuple[str, int | None]:
    """A free-text reply -> (result, days). Never raises: an unparseable answer
    is recorded as unknown with the raw text kept."""
    import re
    text = (reply or "").strip().lower()
    result = "unknown"
    # Longest pattern first, so "under contract" wins over "contract" and
    # "still listed" is not decided by the bare "listed" later in the list.
    for phrase, mapped in sorted(SYNONYMS, key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{phrase}\b", text):
            result = mapped
            break
    days = None
    m = re.search(r"(\d{1,3})\s*(day|week|month)", text)
    if m:
        n = int(m.group(1))
        days = {"day": n, "week": n * 7, "month": n * 30}[m.group(2)]
    return result, days


def due(db: Database, *, after_s: int = ASK_AFTER_S) -> list[str]:
    """Delivered orders old enough to ask about, that we have not asked yet."""
    cutoff = now() - after_s
    with db.tx() as c:
        rows = c.execute(
            "SELECT o.id FROM orders o LEFT JOIN outcomes x ON x.order_id = o.id"
            " WHERE o.status = 'delivered' AND o.delivered_at IS NOT NULL"
            "   AND o.delivered_at <= ? AND x.order_id IS NULL"
            " ORDER BY o.delivered_at", (cutoff,)).fetchall()
    return [r["id"] for r in rows]


def mark_asked(db: Database, order_id: str) -> None:
    with db.tx() as c:
        c.execute("INSERT OR IGNORE INTO outcomes(order_id, result, asked_at)"
                  " VALUES(?,?,?)", (order_id, "unknown", now()))


def record(db: Database, order_id: str, reply: str) -> tuple[str, int | None]:
    result, days = parse(reply)
    with db.tx() as c:
        exists = c.execute("SELECT 1 FROM orders WHERE id = ?",
                           (order_id,)).fetchone()
        if not exists:
            raise OutcomeError("no such order")
        c.execute(
            "INSERT INTO outcomes(order_id, result, days_to_sell, note,"
            " answered_at) VALUES(?,?,?,?,?)"
            " ON CONFLICT(order_id) DO UPDATE SET result=excluded.result,"
            " days_to_sell=excluded.days_to_sell, note=excluded.note,"
            " answered_at=excluded.answered_at",
            (order_id, result, days, (reply or "")[:500], now()))
        db.log(c, "outcome.recorded", order_id, f"{result} {days}")
    return result, days


def by_dimension(db: Database, dimension: str) -> list[Insight]:
    """Median days-to-sell, grouped by one field of the brief.

    Median, not mean: one listing that sat for two years would drag a mean
    somewhere useless and make the advice wrong in the confident direction.
    """
    import json
    import statistics
    with db.tx() as c:
        rows = c.execute(
            "SELECT o.brief, x.days_to_sell FROM outcomes x"
            " JOIN orders o ON o.id = x.order_id"
            " WHERE x.result = 'sold' AND x.days_to_sell IS NOT NULL").fetchall()
    buckets: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        brief = json.loads(r["brief"] or "{}")
        value = next((v for k, v in brief.items()
                      if dimension.lower() in k.lower()), None)
        if value:
            buckets[str(value).strip().lower()].append(r["days_to_sell"])
    out = [Insight(dimension=dimension, value=v,
                   median_days=statistics.median(d), samples=len(d))
           for v, d in buckets.items()]
    return sorted(out, key=lambda i: i.median_days)


def best_advice(db: Database, dimension: str) -> str | None:
    """One sentence for the brief page, or nothing at all.

    Returns None unless BOTH groups clear the sample floor and the gap is worth
    a customer changing their mind over. Saying nothing is free; saying
    something wrong costs the credibility that makes the rest of this work."""
    ranked = [i for i in by_dimension(db, dimension) if i.trustworthy]
    if len(ranked) < 2:
        return None
    best, worst = ranked[0], ranked[-1]
    gap = worst.median_days - best.median_days
    if gap < 5:
        return None
    return (f"{best.value.title()} listings in our data go under contract about "
            f"{gap:.0f} days sooner than {worst.value}. "
            f"({best.samples + worst.samples} listings.)")


def summary(db: Database) -> dict:
    with db.tx() as c:
        rows = c.execute("SELECT result, count(*) n FROM outcomes"
                         " WHERE answered_at IS NOT NULL GROUP BY result").fetchall()
        asked = c.execute("SELECT count(*) FROM outcomes WHERE asked_at IS NOT NULL"
                          ).fetchone()[0]
    answered = {r["result"]: r["n"] for r in rows}
    total = sum(answered.values())
    return {"asked": asked, "answered": total, "by_result": answered,
            "response_rate": (total / asked) if asked else 0.0}
