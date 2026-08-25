#!/usr/bin/env python3
"""Pricing for vehicle ad cuts, against verified render cost.

    python3 model/ad_pricing.py

Two distinct products came out of the car demos and they are NOT the same offer:

  WALKAROUND  ~20s, tour tempo, every VIN on the lot. A commodity. It exists so
              a dealer can put motion on 300 vehicle detail pages, most of which
              nobody would ever pay to advertise. Priced per unit, sold by volume.

  AD CUT      15-16s, briefed per vehicle, ad or hype tempo, detail beats,
              vertical-first. This is advertising, not inventory documentation.
              It is made for the units worth pushing: new arrivals, halo cars,
              and aged stock that needs help.

The production cost difference between them is trivial. The VALUE difference is
not, and that is what the price should follow.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from flythrough.cost import USD_PER_CREDIT, rate  # noqa: E402

CR_PER_SEC = rate("wan2-7", "1080p")        # VERIFIED 35 cr/s
PAYMENT_PCT, PAYMENT_FLAT = 0.029, 0.30
MINUTES_PER_AD = 20                          # ASSUMPTION: brief, review, assemble
TARGET_HOURLY = 75.0


@dataclass(frozen=True)
class Product:
    name: str
    seconds: int
    beats: int
    price: float
    note: str
    quantity: int = 1
    channel: str = "online"      # "online" = buyable on its own; "in_plan" = a rate

    @property
    def unit_price(self) -> float:
        return self.price / self.quantity

    @property
    def render_usd(self) -> float:
        return self.seconds * self.quantity * CR_PER_SEC * USD_PER_CREDIT

    def margin(self) -> dict:
        fees = self.price * PAYMENT_PCT + PAYMENT_FLAT
        gp = self.price - self.render_usd - fees
        hours = (MINUTES_PER_AD / 60) * (1 + (self.quantity - 1) * 0.5)
        return {"render": self.render_usd, "fees": fees, "gp": gp,
                "pct": gp / self.price, "hourly": gp / hours}


# MINIMUM ORDER. $39 is the right RATE for a walkaround and the wrong PRICE for
# a single online order. At 2.9% + $0.30 the flat fee alone is 0.77 of it, and
# the order overhead that never shows up in a per-unit margin -- the intake
# email, chasing the photo link, the delivery -- is the same whether the invoice
# says $39 or $249. So $39 survives as the in-plan and 3-pack rate, and the
# smallest thing anyone can buy on its own is three.
WALKAROUND_MIN_UNITS = 3

# The 3-pack is priced at the FULL per-VIN rate -- three times $39, no discount.
# A first pass set it at $99 and quietly broke the ladder: $33 a vehicle undercut
# the 25-vehicle plan at $34, so committing to more would have cost more each.
# The minimum order is a floor on order SIZE, not a volume discount. Discounts
# start where the commitment does, at Lot 25.

PRODUCTS = (
    Product("Walkaround x3", 20, 7, 117.0,
            "Minimum online order. Three VINs at the full $39 rate.", quantity=3),
    Product("Walkaround (per VIN)", 20, 7, 39.0,
            "The RATE, not a checkout. Add-on inside a lot plan.",
            channel="in_plan"),
    Product("Ad cut - mainstream", 15, 7, 149.0,
            "Trucks, SUVs, sedans under ~$80k. Briefed, detail beats, vertical."),
    Product("Ad cut - premium", 16, 8, 249.0,
            "Exotic, luxury, performance. Same production, different budget."),
    Product("Launch package", 16, 8, 399.0,
            "Ad cut + 3 platform re-cuts + 3 hook variants for paid social."),
)

# Value-based tiering. Production cost is near-identical across these; what
# differs is the marketing budget attached to the unit.
BANDS = (
    ("Under $40k", "Walkaround x3", 117.0,
     "Ad spend on these units is rarely justified. Sell volume, not ads."),
    ("$40k - $80k", "Ad cut - mainstream", 149.0,
     "A truck at $65k carries a real marketing line. This is the volume ad tier."),
    ("$80k - $200k", "Ad cut - premium", 249.0,
     "Luxury and performance. The dealer is already paying a photographer more."),
    ("$200k+", "Launch package", 399.0,
     "Exotics move on desire and reach. Cheapest line on the invoice by far."),
)


@dataclass(frozen=True)
class LotPlan:
    """Monthly walkaround volume. One invoice, so the flat payment fee is charged
    once for the whole plan rather than once per vehicle -- which is most of why
    the per-unit number can fall below the a-la-carte $39 and still earn more."""
    name: str
    units: int
    price: float

    @property
    def per_unit(self) -> float:
        return self.price / self.units

    def margin(self) -> dict:
        seconds = _by_name("Walkaround (per VIN)").seconds * self.units
        render = seconds * CR_PER_SEC * USD_PER_CREDIT
        fees = self.price * PAYMENT_PCT + PAYMENT_FLAT   # ONE invoice, one flat fee
        gp = self.price - render - fees
        hours = (MINUTES_PER_AD / 60) * self.units * 0.5  # ASSUMPTION: batch halves handling
        return {"render": render, "fees": fees, "gp": gp,
                "pct": gp / self.price, "hourly": gp / hours, "hours": hours}


LOT_PLANS = (
    LotPlan("Lot 25", 25, 850.0),
    LotPlan("Lot 50", 50, 1450.0),
    LotPlan("Lot 100", 100, 2600.0),
)


def _by_name(name: str) -> Product:
    return next(p for p in PRODUCTS if p.name == name)


def report() -> None:
    line = "-" * 76
    print(line)
    print("VEHICLE AD PRICING")
    print(line)
    print(f"Render {CR_PER_SEC} cr/sec @1080p [VERIFIED] x ${USD_PER_CREDIT:.4f}/cr "
          f"[CONFIRMED] = ${CR_PER_SEC * USD_PER_CREDIT:.4f}/sec")
    print(f"Operator {MINUTES_PER_AD} min/ad [ASSUMPTION]")
    print()
    print(f"{'Product':<26}{'Price':>8}{'Render':>9}{'Fees':>8}{'GP':>9}{'Margin':>9}{'$/hr':>9}")
    for p in PRODUCTS:
        m = p.margin()
        print(f"{p.name:<26}{'$%.0f' % p.price:>8}{'$%.2f' % m['render']:>9}"
              f"{'$%.2f' % m['fees']:>8}{'$%.2f' % m['gp']:>9}"
              f"{m['pct']:>8.1%}{'$%.0f' % m['hourly']:>9}")
    print()
    for p in PRODUCTS:
        print(f"  {p.name}: {p.note}")

    print()
    print(line)
    print("LOT PLANS -- walkaround volume, one monthly invoice")
    print(line)
    print(f"{'Plan':<12}{'Units':>7}{'Price':>9}{'Per unit':>10}{'Render':>9}"
          f"{'GP':>10}{'Margin':>9}{'$/hr':>9}")
    for lp in LOT_PLANS:
        m = lp.margin()
        print(f"{lp.name:<12}{lp.units:>7}{'$%.0f' % lp.price:>9}"
              f"{'$%.2f' % lp.per_unit:>10}{'$%.2f' % m['render']:>9}"
              f"{'$%.2f' % m['gp']:>10}{m['pct']:>8.1%}{'$%.0f' % m['hourly']:>9}")
    per_vin = next(p for p in PRODUCTS if p.channel == "in_plan")
    three = PRODUCTS[0]
    print(f"  Smallest online order is ${three.price:.0f} for {three.quantity} "
          f"(${three.unit_price:.0f} each); the in-plan rate is "
          f"${per_vin.price:.0f}/VIN. The plans discount that to buy predictability:")
    print("  one invoice, one batch, one folder drop -- and the account that makes")
    print("  every ad cut an upsell instead of a cold pitch.")

    print()
    print(line)
    print("SELL BY VEHICLE PRICE BAND, NOT BY PRODUCTION COST")
    print(line)
    print(f"{'Band':<16}{'Product':<26}{'Price':>8}")
    for band, prod, price, why in BANDS:
        print(f"{band:<16}{prod:<26}{'$%.0f' % price:>8}")
        print(f"                {why}")
    print()
    print(line)
    print("WHY THESE NUMBERS")
    print(line)
    ferrari = _by_name("Ad cut - premium"); truck = _by_name("Ad cut - mainstream")
    print(f"  The two demo ads cost ${ferrari.render_usd:.2f} and ${truck.render_usd:.2f} to render.")
    print("  Production cost is NOT the pricing input -- it is a rounding error at")
    print("  every tier. What differs is the marketing budget attached to the unit.")
    print()
    print("  Anchors a dealer already knows:")
    print("    a freelance vehicle video          $150-400")
    print("    an agency social spot              $500-2,000")
    print("    a professional photographer's day  $400-800")
    print("  $149 sits under the cheapest freelancer. $249 sits under all of them")
    print("  while looking like the agency product. Neither invites a haggle.")
    print()
    print("  The walkaround at $39 is deliberately NOT an ad. It is the reason a")
    print("  dealer says yes to a monthly number, and it is what makes the ad cut")
    print("  an easy upsell on the units that matter -- you are already in the")
    print("  account, already have the photos, already know their inventory.")
    print()
    print("  Attach rate is the whole model: 150 walkarounds at $39 is $5,850, and")
    print("  10% of them upgraded to a $149 ad cut adds $2,235 for about 5 hours.")
    print(line)


if __name__ == "__main__":
    report()
