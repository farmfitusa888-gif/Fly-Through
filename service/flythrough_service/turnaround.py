"""How long an order takes from paid to delivered, against what was promised.

This exists because `business/12-render-provider.md` names one trigger for
buying an automatic renderer: the operator becoming the reason a delivery is
late. That is a measurement, not a feeling, and the data for it is already in
the orders table -- `paid_at` and `delivered_at`, on every order that ever
completed.

The promise is not invented here either. Every SKU in the catalogue carries a
`turnaround` string because it is the sentence next to the money, so an order
is judged against the promise its own customer bought, not against a number
somebody picked for a dashboard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import catalog_bridge as cat
from .db import now

# A weekly-batch SKU is not late at hour 25 -- it was never sold as a same-day
# job. Judged against seven days so it still appears, and still fails if it
# genuinely stalls.
BATCH_HOURS = 24 * 7

# Below this share of orders hitting their promise, the operator is the
# bottleneck and it is time to read the provider decision again. Deliberately
# not 100%: one late order in a small sample is noise, and a threshold that
# trips on noise gets ignored, which is worse than not having one.
ON_TIME_FLOOR = 0.9

# Under this many delivered orders there is no rate worth reporting. Same
# reasoning as outcomes.MIN_SAMPLES: three orders cannot tell you anything
# about throughput.
MIN_SAMPLES = 8


def promised_hours(sku_id: str) -> float:
    """Hours the SKU's own turnaround line promises, or 0 if it promises none."""
    sku = cat.skus().get(sku_id)
    text = (sku.turnaround if sku else "").lower()
    if "batch" in text or "weekly" in text:
        return BATCH_HOURS
    m = re.search(r"(\d+)\s*hour", text)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+)\s*day", text)
    return float(m.group(1)) * 24 if m else 0.0


@dataclass(frozen=True)
class Turnaround:
    delivered: int            # orders measured
    median_hours: float       # typical paid -> delivered
    slowest_hours: float
    on_time: int              # of those measured
    on_time_rate: float
    waiting: int              # paid but not delivered right now
    oldest_waiting_hours: float
    overdue_now: int          # waiting and already past their promise
    enough: bool              # sample big enough to read anything into
    pressured: bool           # the provider-switch trigger, tripped

    @property
    def headline(self) -> str:
        if not self.enough:
            return (f"{self.delivered} delivered so far — "
                    f"{MIN_SAMPLES} needed before the rate means anything")
        if self.pressured:
            return (f"{self.on_time_rate:.0%} on time. Below "
                    f"{ON_TIME_FLOOR:.0%} the operator is the bottleneck — "
                    f"read business/12-render-provider.md")
        return f"{self.on_time_rate:.0%} on time, median {self.median_hours:.1f}h"


def measure(db, *, limit: int = 50, at: int | None = None) -> Turnaround:
    """Read the gap off the orders table. No new storage, no new writes."""
    at = now() if at is None else at
    with db.tx() as c:
        done = c.execute(
            "SELECT sku, paid_at, delivered_at FROM orders"
            " WHERE delivered_at IS NOT NULL AND paid_at IS NOT NULL"
            " ORDER BY delivered_at DESC LIMIT ?", (limit,)).fetchall()
        open_ = c.execute(
            "SELECT sku, paid_at FROM orders WHERE paid_at IS NOT NULL"
            " AND delivered_at IS NULL AND status NOT IN"
            " ('refunded','cancelled')").fetchall()

    hours, on_time = [], 0
    for r in done:
        h = (r["delivered_at"] - r["paid_at"]) / 3600.0
        hours.append(h)
        promised = promised_hours(r["sku"])
        # A SKU with no stated promise cannot be missed. Counting it as on time
        # would flatter the rate; counting it as late would punish an order
        # nobody was ever promised anything about.
        if not promised or h <= promised:
            on_time += 1

    waits = [(at - r["paid_at"]) / 3600.0 for r in open_]
    overdue = sum(1 for r in open_
                  if promised_hours(r["sku"])
                  and (at - r["paid_at"]) / 3600.0 > promised_hours(r["sku"]))

    enough = len(hours) >= MIN_SAMPLES
    rate = (on_time / len(hours)) if hours else 0.0
    return Turnaround(
        delivered=len(hours),
        median_hours=_median(hours),
        slowest_hours=max(hours, default=0.0),
        on_time=on_time,
        on_time_rate=rate,
        waiting=len(waits),
        oldest_waiting_hours=max(waits, default=0.0),
        overdue_now=overdue,
        enough=enough,
        pressured=enough and rate < ON_TIME_FLOOR,
    )


def _median(xs: list[float]) -> float:
    """Median, not mean. One order delivered a week late because the customer
    sent the wrong photographs should not move the number that decides whether
    to buy a renderer."""
    if not xs:
        return 0.0
    s = sorted(xs)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
