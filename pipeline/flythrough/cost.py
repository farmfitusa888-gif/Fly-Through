"""Render cost model.

Every rate in RATE_CARD was read from OpenArt's own pricing tool on 2026-08-20,
not estimated. Linearity in duration was confirmed by quoting the same model at
both 5s and 10s (Wan 2.7 720p: 125cr @5s, 250cr @10s). Re-verify before quoting
a client -- provider pricing moves, and a stale rate card is how a service
business quietly sells below cost.

Dollar conversion is deliberately a single constant with its provenance stated,
so there is exactly one place to correct when the real number is confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- Verified 2026-08-20 via openart_model_cost -----------------------------
# (model, mode-tier) -> credits per second of finished video.
RATE_CARD: dict[tuple[str, str], int] = {
    ("pixverseV6", "540p"): 10,
    ("pixverseV6", "1080p"): 30,
    ("wan2-7", "720p"): 25,
    ("wan2-7", "1080p"): 35,
    ("kling-3-omni", "std"): 35,
    ("kling-3-omni", "pro"): 35,
    ("byte-plus-seedance-2", "720p"): 80,
}

# Models that accept BOTH a start frame and an end frame. Only these can anchor a
# shot to two real photographs, which is the core constraint of this product.
# A model missing from this set cannot be used for a delivered client shot.
DUAL_ANCHOR: frozenset[str] = frozenset({
    "wan2-7", "kling-3-omni", "byte-plus-seedance-2",
    "byte-plus-seedance-2-fast", "byte-plus-seedance-2-mini",
    "byte-plus-seedance-2-5", "pixverseV6",
})

# USD per OpenArt credit. CONFIRMED by the account holder 2026-08-21:
# 5,000 credits for $15 = $0.0030/credit. This is the top-up (marginal) rate,
# which is the correct one to model with -- at any real volume the subscription
# allowance is exhausted and every further credit costs exactly this.
USD_PER_CREDIT: float = 0.0030
USD_PER_CREDIT_VERIFIED: bool = True

# Share of shots that get re-rendered because the first take drifted. Set from
# observed rework once you have run 20+ real jobs; until then this is the
# planning assumption, and it is stated rather than hidden inside a margin.
REROLL_RATE: float = 0.25


# --- providers ---------------------------------------------------------------
# Credits are OpenArt's unit, not a universal one. Most providers bill in
# dollars per second of finished video, and a model that can only think in
# credits cannot answer the question that actually matters when switching:
# does the margin move?
#
# So a provider is a name, a billing unit, and a way to get to USD per second.
# The credit path below is unchanged and still verified; the USD path exists so
# an alternative can be priced without pretending it uses credits.
#
# NOTHING IS PRE-FILLED for a provider whose pricing has not been read from its
# own page. An invented rate is worse than no rate: it produces a margin table
# that looks authoritative and is wrong, and pricing is the one place this
# business cannot afford to be confidently mistaken.

CREDITS, USD_PER_SECOND = "credits", "usd_per_second"


@dataclass(frozen=True)
class Provider:
    name: str
    unit: str
    # (model, tier) -> credits/sec for CREDITS, or USD/sec for USD_PER_SECOND.
    rates: dict[tuple[str, str], float]
    usd_per_credit: float = 0.0
    verified: bool = False
    source: str = ""

    def usd_per_second(self, model: str, tier: str) -> float:
        key = (model, tier)
        if key not in self.rates:
            known = ", ".join(f"{m}@{t}" for m, t in sorted(self.rates)) or "none"
            raise KeyError(
                f"{self.name} has no recorded rate for {model}@{tier}. "
                f"Recorded: {known}. Read it from the provider's own pricing "
                f"page and add it -- do not estimate, a wrong rate produces a "
                f"margin table that looks authoritative and is not.")
        if self.unit == CREDITS:
            return self.rates[key] * self.usd_per_credit
        return self.rates[key]


OPENART = Provider(
    name="openart",
    unit=CREDITS,
    rates={k: float(v) for k, v in RATE_CARD.items()},
    usd_per_credit=USD_PER_CREDIT,
    verified=True,
    source="openart_model_cost 2026-08-20; credit price confirmed by the "
           "account holder 2026-08-21 (5,000 for $15).",
)

# A candidate second source. Wan 2.7 there does 1080p, 15s and first+last frame
# anchoring, which is what this pipeline needs -- but the PRICE has not been
# read, so there is nothing here. Fill it from fal's own pricing page and set
# verified=True, and every number downstream updates.
FAL = Provider(
    name="fal",
    unit=USD_PER_SECOND,
    rates={},
    verified=False,
    source="queue API verified from fal's docs 2026-08-25; PRICING NOT READ.",
)

PROVIDERS: dict[str, Provider] = {p.name: p for p in (OPENART, FAL)}
ACTIVE: Provider = OPENART


@dataclass(frozen=True)
class Quote:
    """Cost of rendering one plan, with rework priced in."""

    model: str
    tier: str
    seconds: int
    shots: int
    credits_per_second: int
    base_credits: int
    reroll_rate: float
    expected_credits: int
    worst_case_credits: int

    @property
    def base_usd(self) -> float:
        return self.base_credits * USD_PER_CREDIT

    @property
    def expected_usd(self) -> float:
        return self.expected_credits * USD_PER_CREDIT

    @property
    def worst_case_usd(self) -> float:
        return self.worst_case_credits * USD_PER_CREDIT

    def describe(self) -> str:
        dollar_note = "" if USD_PER_CREDIT_VERIFIED else "  (USD est., unverified)"
        return (
            f"{self.model} @ {self.tier}: {self.shots} shots / {self.seconds}s\n"
            f"  base      {self.base_credits:>6} cr  ${self.base_usd:>7.2f}\n"
            f"  expected  {self.expected_credits:>6} cr  ${self.expected_usd:>7.2f}"
            f"   (incl. {self.reroll_rate:.0%} re-roll)\n"
            f"  worst     {self.worst_case_credits:>6} cr  ${self.worst_case_usd:>7.2f}"
            f"   (every shot re-rolled once){dollar_note}"
        )


def usd_per_second(model: str, tier: str,
                   provider: Provider | None = None) -> float:
    """What one second of finished video costs, whoever is rendering it.

    The unit every downstream calculation actually wants. Credits are an
    implementation detail of one provider.
    """
    return (provider or ACTIVE).usd_per_second(model, tier)


def compare(model: str, tier: str, a: Provider, b: Provider) -> dict:
    """Side by side, with the honesty of both stated.

    Refuses rather than guessing when either side has no recorded rate: the
    whole point of this function is to inform a switch, and a comparison
    against an invented number would recommend one on no evidence.
    """
    a_usd = a.usd_per_second(model, tier)
    b_usd = b.usd_per_second(model, tier)
    return {
        "model": f"{model}@{tier}",
        a.name: a_usd, b.name: b_usd,
        "delta_pct": (b_usd - a_usd) / a_usd if a_usd else 0.0,
        "both_verified": a.verified and b.verified,
    }


def rate(model: str, tier: str) -> int:
    """Credits per second for a model/tier, or raise with the valid options."""
    key = (model, tier)
    if key not in RATE_CARD:
        opts = ", ".join(f"{m}@{t}" for m, t in sorted(RATE_CARD))
        raise KeyError(f"no verified rate for {model}@{tier}. Verified: {opts}")
    return RATE_CARD[key]


def quote(
    *,
    seconds: int,
    shots: int,
    model: str = "wan2-7",
    tier: str = "1080p",
    reroll_rate: float = REROLL_RATE,
) -> Quote:
    """Price a plan before rendering it.

    Raises if the model cannot hold two anchor frames -- a single-anchor model
    would let the far end of every shot drift off the real property, which is
    the one failure this product cannot ship.
    """
    if model not in DUAL_ANCHOR:
        raise ValueError(
            f"{model} does not support start+end frame anchoring and cannot be "
            "used for delivered shots."
        )
    cps = rate(model, tier)
    base = cps * seconds
    # Re-rolls are per shot, so the expected overage scales with shot count.
    avg_shot = seconds / shots if shots else 0
    expected = round(base + cps * avg_shot * shots * reroll_rate)
    worst = base * 2
    return Quote(
        model=model,
        tier=tier,
        seconds=seconds,
        shots=shots,
        credits_per_second=cps,
        base_credits=base,
        reroll_rate=reroll_rate,
        expected_credits=expected,
        worst_case_credits=worst,
    )
