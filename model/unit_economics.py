"""FlyThrough unit economics and revenue model.

Every cost input here is either (a) read from a provider's own pricing tool, or
(b) an explicitly labelled assumption with the reason it was chosen. Nothing is
asserted. Run this file to regenerate every number quoted in business/.

    python3 model/unit_economics.py

Assumptions marked ASSUMPTION are planning inputs, not measured facts. Replace
them with observed values after the first 20 real jobs; the whole model updates.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from flythrough.cost import REROLL_RATE, USD_PER_CREDIT, quote  # noqa: E402

# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

# VERIFIED 2026-08-20 from openart_model_cost: Wan 2.7 image2video 1080p costs
# 35 credits/second, linear in duration (175cr @5s, 350cr @10s).
STANDARD_RUNTIME_S = 42      # 8 shots, the tour length that fits an MLS video slot
STANDARD_SHOTS = 8

# ASSUMPTION: $0.0030/credit, from the reported $15 / 5,000-credit add-on pack.
# openart.ai was unreachable from the build environment, so this is unconfirmed.
# It is the single largest sensitivity in the model -- see sensitivity() below.

# ASSUMPTION: operator minutes per job once the pipeline is running. Derived from
# the steps that actually require a human: intake check, label review, plan
# review, spot-check the 8 clips, assemble, deliver.
MINUTES_PER_JOB = 25
TARGET_HOURLY = 75.0         # what the operator's hour must be worth to be worth doing

# ASSUMPTION: ancillary per-job costs (storage, delivery page hosting, payment fees).
# Payment processing at 2.9% + $0.30 is the only one that is a published rate.
PAYMENT_PCT = 0.029
PAYMENT_FLAT = 0.30
HOSTING_PER_JOB = 0.05       # ASSUMPTION: object storage + bandwidth for one delivery


@dataclass(frozen=True)
class Tier:
    name: str
    price: float
    runtime_s: int
    shots: int
    vertical: bool
    revisions: int
    note: str


TIERS: tuple[Tier, ...] = (
    Tier("Single Listing",  149.0, 30, 6,  False, 1,
         "One 30s master. The trial purchase -- priced to be an easy yes."),
    Tier("Listing Pro",     249.0, 42, 8,  True,  2,
         "The default. 42s master + 9:16 vertical + thumbnail."),
    Tier("Signature",       399.0, 60, 12, True,  3,
         "Luxury listings. 60s, twilight pass, priority turnaround."),
)

# Retainer: the number that actually makes this a business rather than a hustle.
RETAINER_PRICE = 899.0
RETAINER_LISTINGS = 5


def cogs(runtime_s: int, shots: int, price: float, *, reroll: float = REROLL_RATE) -> dict:
    """Cost of goods for one delivered job."""
    q = quote(seconds=runtime_s, shots=shots, model="wan2-7", tier="1080p", reroll_rate=reroll)
    render = q.expected_usd
    payment = price * PAYMENT_PCT + PAYMENT_FLAT
    labour = TARGET_HOURLY * (MINUTES_PER_JOB / 60)
    return {
        "render_credits": q.expected_credits,
        "render": render,
        "payment": payment,
        "hosting": HOSTING_PER_JOB,
        "cash_cogs": render + payment + HOSTING_PER_JOB,
        "labour_at_target": labour,
    }


def margins(t: Tier) -> dict:
    c = cogs(t.runtime_s, t.shots, t.price)
    cash_gp = t.price - c["cash_cogs"]
    return {
        "tier": t.name,
        "price": t.price,
        **c,
        "cash_gross_profit": cash_gp,
        "cash_gross_margin": cash_gp / t.price,
        "profit_after_labour": cash_gp - c["labour_at_target"],
        "effective_hourly": cash_gp / (MINUTES_PER_JOB / 60),
    }


def revenue_math(monthly_target: float, t: Tier, *, close_rate: float, reply_rate: float) -> dict:
    """target / price = jobs; jobs / close = conversations; / reply = outreach."""
    jobs = monthly_target / t.price
    conversations = jobs / close_rate
    outreach = conversations / reply_rate
    return {
        "tier": t.name,
        "monthly_target": monthly_target,
        "jobs_per_month": jobs,
        "jobs_per_week": jobs / 4.33,
        "conversations_needed": conversations,
        "outreach_needed": outreach,
        "outreach_per_working_day": outreach / 21,
        "operator_hours": jobs * MINUTES_PER_JOB / 60,
    }


def sensitivity() -> list[dict]:
    """What happens to margin if the unverified credit price is wrong."""
    t = TIERS[1]
    rows = []
    for mult, label in ((1.0, "as modelled"), (2.0, "2x credit price"),
                        (3.0, "3x credit price"), (5.0, "5x credit price")):
        q = quote(seconds=t.runtime_s, shots=t.shots, model="wan2-7", tier="1080p")
        render = q.expected_credits * USD_PER_CREDIT * mult
        payment = t.price * PAYMENT_PCT + PAYMENT_FLAT
        gp = t.price - render - payment - HOSTING_PER_JOB
        rows.append({
            "case": label,
            "usd_per_credit": USD_PER_CREDIT * mult,
            "render_cost": render,
            "cash_gross_profit": gp,
            "cash_gross_margin": gp / t.price,
        })
    return rows


def constraint_analysis(t: Tier) -> dict:
    """Which input actually binds this business: credits or operator time.

    Render cost is a rounding error against the price, so re-rolls never threaten
    cash margin -- they threaten throughput. The number that matters is how many
    minutes a job can absorb before it stops clearing the target hourly rate.
    """
    c = cogs(t.runtime_s, t.shots, t.price)
    cash_gp = t.price - c["cash_cogs"]
    max_minutes = cash_gp / TARGET_HOURLY * 60
    # Credits would have to rise this far to consume the whole gross profit.
    credit_multiple = cash_gp / c["render"] if c["render"] else float("inf")
    return {
        "cash_gross_profit": cash_gp,
        "max_minutes_at_target_hourly": max_minutes,
        "budgeted_minutes": MINUTES_PER_JOB,
        "time_headroom_multiple": max_minutes / MINUTES_PER_JOB,
        "credit_price_multiple_to_zero_margin": credit_multiple,
    }


def _money(x: float) -> str:
    return f"${x:,.2f}"


def report() -> None:
    line = "-" * 78
    print(line)
    print("FLYTHROUGH -- UNIT ECONOMICS")
    print(line)
    print(f"Render rate   35 credits/sec @1080p  (VERIFIED 2026-08-20)")
    print(f"Credit price  ${USD_PER_CREDIT:.4f}/credit  (ASSUMPTION - unverified)")
    print(f"Re-roll rate  {REROLL_RATE:.0%}  (ASSUMPTION)")
    print(f"Operator time {MINUTES_PER_JOB} min/job  (ASSUMPTION)")
    print()

    print("PER-JOB MARGIN BY TIER")
    print(f"{'Tier':<16}{'Price':>9}{'Render':>9}{'Fees':>8}{'CashGP':>10}{'Margin':>9}{'$/hr':>10}")
    for t in TIERS:
        m = margins(t)
        print(f"{m['tier']:<16}{_money(m['price']):>9}{_money(m['render']):>9}"
              f"{_money(m['payment']):>8}{_money(m['cash_gross_profit']):>10}"
              f"{m['cash_gross_margin']:>8.1%}{_money(m['effective_hourly']):>10}")

    rq = quote(seconds=TIERS[1].runtime_s * RETAINER_LISTINGS,
               shots=TIERS[1].shots * RETAINER_LISTINGS, model="wan2-7", tier="1080p")
    r_render = rq.expected_usd
    r_pay = RETAINER_PRICE * PAYMENT_PCT + PAYMENT_FLAT
    r_gp = RETAINER_PRICE - r_render - r_pay - HOSTING_PER_JOB * RETAINER_LISTINGS
    print(f"{'Retainer x5':<16}{_money(RETAINER_PRICE):>9}{_money(r_render):>9}"
          f"{_money(r_pay):>8}{_money(r_gp):>10}{r_gp / RETAINER_PRICE:>8.1%}"
          f"{_money(r_gp / (MINUTES_PER_JOB * RETAINER_LISTINGS / 60)):>10}")
    print(f"  (= {_money(RETAINER_PRICE / RETAINER_LISTINGS)}/listing, "
          f"{1 - RETAINER_PRICE / RETAINER_LISTINGS / TIERS[1].price:.0%} off Listing Pro)")
    print()

    print("SENSITIVITY -- if the unverified credit price is wrong")
    print(f"{'Case':<20}{'$/credit':>11}{'Render':>10}{'CashGP':>11}{'Margin':>9}")
    for row in sensitivity():
        print(f"{row['case']:<20}{row['usd_per_credit']:>11.4f}"
              f"{_money(row['render_cost']):>10}{_money(row['cash_gross_profit']):>11}"
              f"{row['cash_gross_margin']:>9.1%}")
    ca = constraint_analysis(TIERS[1])
    print()
    print("WHAT ACTUALLY BINDS THIS BUSINESS")
    print(f"  Credits would have to cost {ca['credit_price_multiple_to_zero_margin']:.0f}x more")
    print(f"  to erase Listing Pro's gross profit. Render cost is not the constraint,")
    print(f"  so re-rolls cost time, not margin.")
    print(f"  A job can absorb {ca['max_minutes_at_target_hourly']:.0f} minutes before it stops")
    print(f"  clearing {_money(TARGET_HOURLY)}/hr -- {ca['time_headroom_multiple']:.1f}x the "
          f"{MINUTES_PER_JOB}-minute budget.")
    print("  => Operator minutes are the scarce input. Automate review, not render.")
    print()

    print("REVENUE MATH -- Listing Pro at $249")
    print(f"{'Target/mo':>10}{'Jobs':>7}{'Jobs/wk':>9}{'Convos':>9}"
          f"{'Outreach':>10}{'/day':>7}{'Hours':>7}")
    for target in (2_000, 5_000, 10_000, 20_000):
        r = revenue_math(target, TIERS[1], close_rate=0.20, reply_rate=0.08)
        print(f"{_money(target):>10}{r['jobs_per_month']:>7.0f}{r['jobs_per_week']:>9.1f}"
              f"{r['conversations_needed']:>9.0f}{r['outreach_needed']:>10.0f}"
              f"{r['outreach_per_working_day']:>7.0f}{r['operator_hours']:>7.1f}")
    print("  ASSUMPTION: 8% reply rate, 20% close on a replied conversation.")
    print("  Read the /day column as the real constraint: it is the number of")
    print("  agents that must be contacted every working day to hit the target.")
    print(line)


if __name__ == "__main__":
    report()
