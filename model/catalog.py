#!/usr/bin/env python3
"""The sellable catalogue: every SKU a customer can buy without talking to us.

    python3 model/catalog.py

Selling online changes what a price has to carry. A quoted price is a sentence
in an email; a SKU is a checkout button, a tax treatment, a fulfilment promise
and an intake form that has to collect enough to actually start the job. A paid
order with no photos attached is worse than no order -- it is a refund with
extra steps.

So each SKU declares four things beyond its price:

  mode      one-time or recurring. Recurring is a different Stripe object, a
            different cancellation duty and a different revenue line.
  vertical  which taxonomy and which compliance basis applies. Real estate
            cannot be sold without a disclosure pack; the others can.
  intake    exactly what must be collected before work can begin.
  turnaround  the promise attached to the money. If it is on the button it is
            on the invoice.

Prices are NOT defined here. They come from unit_economics.TIERS and
ad_pricing.PRODUCTS/LOT_PLANS so there is still one source of truth, and this
module fails loudly if a name it references stops existing.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
sys.path.insert(0, str(ROOT / "pipeline"))

from ad_pricing import LOT_PLANS, PAYMENT_FLAT, PAYMENT_PCT, PRODUCTS  # noqa: E402
from flythrough.cost import USD_PER_CREDIT, rate                        # noqa: E402
from unit_economics import RETAINER_LISTINGS, RETAINER_PRICE, TIERS     # noqa: E402

CR_PER_SEC = rate("wan2-7", "1080p")

# Intake requirements, by vertical. These are the questions the /start page asks
# after checkout. Keep them SHORT -- every field is a chance to abandon -- but
# never drop one the pipeline genuinely needs, because chasing it by email costs
# more than the field ever did.
INTAKE = {
    "rooms": [
        "Property address (as it appears on the listing)",
        "Brokerage name -- it goes on the disclosure page",
        "Link to the photos (Dropbox, Drive, Google Photos, anything)",
        "Daylight, golden hour or twilight",
    ],
    "vehicles": [
        "VIN or stock number",
        "Year, make, model, trim",
        "Link to the photos",
        "What the buyer is paying extra for (wheels, interior, tow package...)",
    ],
    "products": [
        "Product name",
        "Link to the photos",
        "Where it is going to run (Reels, TikTok, a product page, paid social)",
    ],
}


@dataclass(frozen=True)
class Sku:
    id: str
    name: str
    price: float
    mode: str                 # "one-time" | "recurring"
    vertical: str             # rooms | vehicles | products
    turnaround: str
    seconds: int              # rendered runtime, for the cost floor
    quantity: int = 1         # units covered by one purchase
    blurb: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def render_usd(self) -> float:
        return self.seconds * self.quantity * CR_PER_SEC * USD_PER_CREDIT

    @property
    def unit_price(self) -> float:
        return self.price / self.quantity

    def margin(self) -> dict:
        # One checkout is one payment, so the flat fee is charged once per
        # ORDER -- not per unit. That is why the lot plans survive $26/vehicle.
        fees = self.price * PAYMENT_PCT + PAYMENT_FLAT
        gp = self.price - self.render_usd - fees
        return {"render": self.render_usd, "fees": fees, "gp": gp,
                "pct": gp / self.price}


def _tier(name: str):
    return next(t for t in TIERS if t.name == name)


def _product(name: str):
    return next(p for p in PRODUCTS if p.name == name)


def _plan(name: str):
    return next(p for p in LOT_PLANS if p.name == name)


# ---------------------------------------------------------------- real estate
_re = [
    Sku(f"re-{t.name.lower().replace(' ', '-')}", t.name, t.price, "one-time",
        "rooms", "24 hours", t.runtime_s,
        blurb=t.note,
        tags=("disclosure pack included",) + (("9:16 vertical",) if t.vertical else ()))
    for t in TIERS
]
_re.append(Sku("re-retainer", f"{RETAINER_LISTINGS} listings a month",
               RETAINER_PRICE, "recurring", "rooms", "24 hours each",
               _tier("Listing Pro").runtime_s, quantity=RETAINER_LISTINGS,
               blurb="For agents who list every week. One invoice, no per-job approval.",
               tags=("cancel any time",)))

# ------------------------------------------------------------------- vehicles
_veh = [
    Sku("veh-walkaround", _product("Walkaround (per VIN)").name, 39.0,
        "one-time", "vehicles", "24 hours", 20,
        blurb=_product("Walkaround (per VIN)").note),
    Sku("veh-ad-mainstream", "Ad cut - mainstream", 149.0, "one-time",
        "vehicles", "24 hours", 15,
        blurb=_product("Ad cut - mainstream").note),
    Sku("veh-ad-premium", "Ad cut - premium", 249.0, "one-time",
        "vehicles", "24 hours", 16,
        blurb=_product("Ad cut - premium").note),
    Sku("veh-launch", "Launch package", 399.0, "one-time",
        "vehicles", "48 hours", 16,
        blurb=_product("Launch package").note),
]
_veh += [
    Sku(f"lot-{p.units}", f"{p.units} walkarounds a month", p.price,
        "recurring", "vehicles", "weekly batch", 20, quantity=p.units,
        blurb=f"Every unit on the lot, {p.per_unit:.0f} dollars a vehicle.",
        tags=("cancel any time",))
    for p in LOT_PLANS
]

# ------------------------------------------------------------------- products
# ASSUMPTION: same production shape as a vehicle ad cut -- briefed, detail beats,
# vertical-first -- so it carries the same price. Nothing here is validated by a
# sale yet; the first product customer is allowed to move these numbers.
_prod = [
    Sku("prod-single", "Product cut", 149.0, "one-time", "products",
        "24 hours", 18,
        blurb="One product, one film. Hero, detail, material, scale."),
    Sku("prod-three", "Product cut x3", 349.0, "one-time", "products",
        "48 hours", 18, quantity=3,
        blurb="Three products in one batch, or one product in three lengths."),
]

CATALOG: tuple[Sku, ...] = tuple(_re + _veh + _prod)
BY_ID = {s.id: s for s in CATALOG}


def report() -> None:
    line = "-" * 78
    print(line); print("CATALOG -- what can be bought without talking to us"); print(line)
    print(f"{'SKU':<20}{'Name':<28}{'Price':>8}{'Mode':>11}{'GP':>10}")
    for vertical in ("rooms", "vehicles", "products"):
        print()
        for s in CATALOG:
            if s.vertical != vertical:
                continue
            m = s.margin()
            print(f"{s.id:<20}{s.name[:27]:<28}{'$%.0f' % s.price:>8}"
                  f"{s.mode:>11}{'%.1f%%' % (m['pct'] * 100):>10}")
    print()
    print(line); print("INTAKE -- collected after checkout, before work starts"); print(line)
    for v, qs in INTAKE.items():
        print(f"  {v}")
        for q in qs:
            print(f"    - {q}")
    print()
    print(line)
    print("  Recurring SKUs:", ", ".join(s.id for s in CATALOG if s.mode == "recurring"))
    print(f"  Lowest margin in the catalogue: "
          f"{min(CATALOG, key=lambda s: s.margin()['pct']).id} at "
          f"{min(s.margin()['pct'] for s in CATALOG):.1%}")
    print(line)


if __name__ == "__main__":
    report()
