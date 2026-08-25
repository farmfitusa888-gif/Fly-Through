#!/usr/bin/env python3
"""What switching render provider does to every price in the catalogue.

    python3 model/provider_switch.py                  # current provider only
    python3 model/provider_switch.py --usd-per-sec 0.08

The question a switch actually raises is not "is it cheaper per second" -- it
is "does anything I sell stop working, and does anything become worth
re-pricing". Those have different answers, because render cost is a rounding
error at the ad-cut tiers and is not at the walkaround tier.

Pass --usd-per-sec ONLY with a number read off the provider's own pricing page.
This script will not invent one, and it prints the provenance of everything it
uses so a table can never be mistaken for more certainty than it has.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
sys.path.insert(0, str(ROOT / "pipeline"))

from catalog import CATALOG                                  # noqa: E402
from flythrough.cost import ACTIVE, usd_per_second           # noqa: E402

PAYMENT_PCT, PAYMENT_FLAT = 0.029, 0.30

# Below this, a change in render cost cannot move the price. Stated rather than
# implied, because "the margin barely moved" is a judgement and should be one
# somebody can argue with.
MATERIAL_MARGIN_SHIFT = 0.02      # two percentage points


def margin_at(sku, usd_sec: float) -> dict:
    render = sku.seconds * sku.quantity * usd_sec
    fees = sku.price * PAYMENT_PCT + PAYMENT_FLAT
    gp = sku.price - render - fees
    return {"render": render, "gp": gp, "pct": gp / sku.price}


def report(candidate: float | None) -> int:
    current = usd_per_second("wan2-7", "1080p")
    line = "-" * 78

    print(line)
    print("RENDER COST, AND WHAT IT CAN AND CANNOT MOVE")
    print(line)
    print(f"Current provider : {ACTIVE.name}  ${current:.4f}/sec"
          f"  [{'VERIFIED' if ACTIVE.verified else 'UNVERIFIED'}]")
    print(f"                   {ACTIVE.source}")
    if candidate is None:
        print("\nNo candidate rate given. Re-run with --usd-per-sec <rate read")
        print("from the provider's own pricing page> to see the effect.")
    else:
        delta = (candidate - current) / current
        print(f"Candidate        : ${candidate:.4f}/sec   "
              f"{delta:+.0%} vs current  [SUPPLIED BY OPERATOR]")
    print()

    print(f"{'SKU':<20}{'Price':>8}{'Render now':>12}"
          + (f"{'Render new':>12}{'Margin now':>12}{'Margin new':>12}" if candidate
             else f"{'Margin':>10}"))
    worst_shift, worst_sku = 0.0, ""
    below_cost = []
    for sku in CATALOG:
        now = margin_at(sku, current)
        if candidate is None:
            print(f"{sku.id:<20}{'$%.0f' % sku.price:>8}"
                  f"{'$%.2f' % now['render']:>12}{now['pct']:>9.1%}")
            continue
        new = margin_at(sku, candidate)
        shift = abs(new["pct"] - now["pct"])
        if shift > worst_shift:
            worst_shift, worst_sku = shift, sku.id
        if new["gp"] <= 0:
            below_cost.append(sku.id)
        print(f"{sku.id:<20}{'$%.0f' % sku.price:>8}"
              f"{'$%.2f' % now['render']:>12}{'$%.2f' % new['render']:>12}"
              f"{now['pct']:>11.1%}{new['pct']:>11.1%}")

    if candidate is None:
        return 0

    print()
    print(line)
    print("WHAT THIS ACTUALLY MEANS")
    print(line)
    if below_cost:
        print(f"  STOP. These sell below cost at the candidate rate: "
              f"{', '.join(below_cost)}")
        print("  Re-price them or do not switch.")
    else:
        print("  Nothing sells below cost at the candidate rate.")
    print(f"  Largest margin shift: {worst_shift:.1%} on {worst_sku}.")
    if worst_shift < MATERIAL_MARGIN_SHIFT:
        print(f"  That is under {MATERIAL_MARGIN_SHIFT:.0%}, so no price on the")
        print("  site needs to change. Switch or do not switch on reliability,")
        print("  anchoring quality and API sanity -- not on this.")
    else:
        print(f"  That is over {MATERIAL_MARGIN_SHIFT:.0%}. Re-run")
        print("  model/unit_economics.py and model/ad_pricing.py before deciding.")
    print()
    print("  Render cost is a rounding error at the ad-cut tiers and is not at")
    print("  the walkaround tier, which is why the volume plans are the only")
    print("  place a per-second change is worth watching.")
    print(line)
    return 1 if below_cost else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--usd-per-sec", type=float, default=None,
                    help="candidate rate, READ from the provider's pricing page")
    a = ap.parse_args()
    if a.usd_per_sec is not None and a.usd_per_sec <= 0:
        print("a rate must be positive", file=sys.stderr)
        return 2
    return report(a.usd_per_sec)


if __name__ == "__main__":
    raise SystemExit(main())
