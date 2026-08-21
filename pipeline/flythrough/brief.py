"""Creative brief — the layer that makes each cut specific to its subject.

Added after cutting a supercar exactly like a house: same moves, same slow
pacing, same shot order. The output was technically correct and creatively
worthless, and it cost more than the right version would have.

The lesson is that a tour order is not an advert. A tour asks "what is here?" and
answers it in walking order. An advert asks "why should you want this?" and
answers it in the order that builds desire for THAT subject. A Ferrari earns its
price on form and craft, so the cut is fast and it lingers on carbon and wheels.
A work truck earns its price on capability and comfort, so the cut is steadier
and it lingers on the bed and the seats. Same engine, same anchoring, different
argument.

A Brief is that argument, written down and made executable:

    tempo     how fast the cut moves
    style     the light the subject is sold in
    emphasis  facets that get a beat even if the tour order would skip them
    avoid     facets that weaken THIS argument
    open_on   the frame that has to earn the first second
    close_on  the frame the viewer should be left holding

Nothing here spends anything. It decides what to spend on.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Brief:
    """One subject, one argument, one cut."""

    name: str
    vertical: str                    # "vehicles" | "rooms" | "products"
    tempo: str                       # "tour" | "ad" | "hype"
    style: str                       # a key in moves.STYLES
    argument: str                    # the one sentence the cut has to make
    emphasis: tuple[str, ...] = ()   # facets that must get a beat
    avoid: tuple[str, ...] = ()      # facets that weaken this argument
    open_on: str = ""
    close_on: str = ""
    aspect: str = "9:16"
    max_beats: int = 8

    def sequence(self, available: list[str], interior: set[str] | None = None) -> list[str]:
        """Order the facets we have into this brief's argument.

        Two hard constraints, both from the fact that every beat is a CONTINUOUS
        camera move rather than a cut:

        1. **Cross the envelope once.** Outside beats, then go in, then inside
           beats. Bouncing out and in repeatedly generates absurd travel -- the
           camera physically flies through the body shell four times -- and it
           costs a full beat every crossing. An editor cutting real footage can
           bounce freely; we cannot, because we are generating the journey.

        2. **Bookend deliberately.** When open_on and close_on are the same
           facet, the cut returns to where it began, which is a standard advert
           shape. That needs the facet twice, not once, so it is not deduplicated
           away.

        Emphasis orders within each group, because an advert front-loads its
        reason to keep watching.
        """
        interior = interior or set()
        have = [f for f in available if f not in self.avoid]
        if not have:
            return []

        def rank(f: str) -> int:
            return self.emphasis.index(f) if f in self.emphasis else len(self.emphasis)

        outside = sorted([f for f in have if f not in interior], key=rank)
        inside = sorted([f for f in have if f in interior], key=rank)

        # The opener leads its own group.
        if self.open_on in outside:
            outside.remove(self.open_on)
            outside.insert(0, self.open_on)
        elif self.open_on in inside:
            inside.remove(self.open_on)
            inside.insert(0, self.open_on)

        seq = outside + inside

        # The closer ends the cut. If it bookends the opener, it is a deliberate
        # repeat and gets appended rather than moved.
        if self.close_on in have:
            if self.close_on == self.open_on:
                seq = seq[: self.max_beats] + [self.close_on]
            else:
                if self.close_on in seq:
                    seq.remove(self.close_on)
                seq.append(self.close_on)

        return seq[: self.max_beats + 1]


# ---------------------------------------------------------------------------
# Presets. Each is an argument first and a settings bundle second.
# ---------------------------------------------------------------------------

EXOTIC = Brief(
    name="Exotic performance car",
    vertical="vehicles",
    tempo="hype",
    style="showroom",
    argument="This object is a piece of engineering sculpture and you want to be seen in it.",
    emphasis=("hero", "wheels", "rear", "infotainment"),
    avoid=("odometer", "vin", "cargo", "undercarriage", "engine"),
    open_on="hero",
    close_on="hero",
    aspect="9:16",
    max_beats=7,
)

TRUCK = Brief(
    name="Full-size pickup",
    vertical="vehicles",
    tempo="ad",
    style="lot",
    argument="This will do the work and it will be a nice place to sit while it does.",
    emphasis=("hero", "cargo", "front_seats", "infotainment"),
    avoid=("vin", "undercarriage"),
    open_on="hero",
    close_on="rear",
    aspect="9:16",
    max_beats=8,
)

USED_INVENTORY = Brief(
    name="Used lot inventory",
    vertical="vehicles",
    tempo="tour",
    style="lot",
    argument="Here is the whole vehicle, honestly, including the numbers you asked for.",
    emphasis=("hero", "dash", "odometer"),
    avoid=(),
    open_on="hero",
    close_on="odometer",
    aspect="16:9",
    max_beats=8,
)

LUXURY_HOME = Brief(
    name="Luxury listing",
    vertical="rooms",
    tempo="tour",
    style="goldenhour",
    argument="Imagine your life here; take your time.",
    emphasis=("exterior", "living", "kitchen"),
    avoid=("laundry", "garage", "bathroom"),
    open_on="street",
    close_on="aerial",
    aspect="16:9",
    max_beats=10,
)

PRODUCT_LAUNCH = Brief(
    name="Product launch",
    vertical="products",
    tempo="hype",
    style="studio",
    argument="This is beautifully made and it is new.",
    emphasis=("hero", "detail", "material"),
    avoid=("size_chart", "label", "packaging"),
    open_on="hero",
    close_on="hero",
    aspect="9:16",
    max_beats=6,
)

PRESETS: dict[str, Brief] = {
    "exotic": EXOTIC, "truck": TRUCK, "used": USED_INVENTORY,
    "luxury_home": LUXURY_HOME, "product_launch": PRODUCT_LAUNCH,
}


def cost_credits(brief: Brief, available: list[str], *, credits_per_second: int = 35) -> dict:
    """Price a brief before rendering it. Pure -- spends nothing."""
    from .moves import at_tempo, select

    mod = __import__(f"flythrough.{brief.vertical}", fromlist=["resolve"])
    seq = brief.sequence(available, interior=set(getattr(mod, "INTERIOR", set())))
    alt = getattr(mod, "ALTERNATE_ORBIT", True)

    class _F:
        def __init__(self, k, i):
            self.key, self.interior = k, i

    beats, total = [], 0
    for i, (a, b) in enumerate(zip(seq, seq[1:])):
        ra, rb = mod.resolve(a), mod.resolve(b)
        m = at_tempo(select(_F(ra.key, ra.interior), _F(rb.key, rb.interior),
                            index=i, total=len(seq) - 1, alternate_orbit=alt),
                     brief.tempo)
        beats.append((a, b, m.label, m.seconds))
        total += m.seconds
    return {"beats": beats, "seconds": total, "credits": total * credits_per_second}
