"""Vehicle taxonomy — the auto-dealer vertical.

Exists to prove a structural claim: the pipeline is not a real-estate tool with
some generic parts, it is a generic tool with a real-estate taxonomy bolted on.
Swapping this module for rooms.py changes the vertical. Everything else --
planner, viewpoint, cost, render, assemble, inventory, contactsheet -- is
untouched, because the taxonomy was always DATA rather than logic scattered
through the code.

Why dealers are a serious vertical and not a hypothetical:

  - They already photograph every unit systematically, 20-40 frames, to a house
    standard. Our input problem is solved before we arrive.
  - The walkaround video is an established format buyers expect, so we are not
    creating a category, we are undercutting a cost.
  - One dealer group with 300 units in stock is worth roughly thirty individual
    listing agents, and it is one relationship rather than thirty.
  - Units turn over constantly, so it is recurring by nature rather than
    per-transaction.

The compliance basis is DIFFERENT and must not be copied across. Real estate is
governed by NAR Article 12 and, in California, AB 723. Vehicle advertising is
governed by FTC truth-in-advertising rules and state dealer-advertising
regulations, which vary considerably. Do not reuse compliance.py here without a
lawyer in the operating state.
"""

from __future__ import annotations

from dataclasses import dataclass

# Walkaround order. Mirrors how a salesperson actually shows a car: approach and
# stance first, down one flank, the back, then inside, then the details that
# close the sale.
TOUR_ORDER: tuple[str, ...] = (
    "hero",          # three-quarter front, the establishing shot
    "front",
    "driver_side",
    "rear",
    "passenger_side",
    "wheels",
    "engine",
    "door_open",     # the threshold shot -- exterior to interior
    "dash",
    "front_seats",
    "rear_seats",
    "infotainment",
    "cargo",
    "odometer",      # proof shot, never a hero
    "vin",           # proof shot, never a hero
    "undercarriage",
)

_RANK: dict[str, int] = {k: i for i, k in enumerate(TOUR_ORDER)}

ALIASES: dict[str, str] = {
    "threequarter": "hero", "34": "hero", "beauty": "hero", "stance": "hero",
    "grille": "front", "nose": "front", "headlight": "front", "bumper": "front",
    "driver": "driver_side", "leftside": "driver_side", "profile": "driver_side",
    "passenger": "passenger_side", "rightside": "passenger_side",
    "tail": "rear", "back": "rear", "taillight": "rear",
    "wheel": "wheels", "rim": "wheels", "tire": "wheels", "tyre": "wheels",
    "motor": "engine", "enginebay": "engine", "underhood": "engine",
    "door": "door_open", "entry": "door_open",
    "dashboard": "dash", "cockpit": "dash", "cluster": "dash",
    "steeringwheel": "dash", "gauges": "dash",
    "seats": "front_seats", "frontseat": "front_seats", "interior": "front_seats",
    "backseat": "rear_seats", "rearseat": "rear_seats", "secondrow": "rear_seats",
    "screen": "infotainment", "headunit": "infotainment", "nav": "infotainment",
    "radio": "infotainment", "console": "infotainment",
    "boot": "cargo", "hatch": "cargo", "bed": "cargo", "cargoarea": "cargo",
    "trunk": "cargo", "trunkspace": "cargo",
    "miles": "odometer", "mileage": "odometer", "kms": "odometer",
    "chassis": "vin", "sticker": "vin", "window sticker": "vin",
    "underside": "undercarriage", "frame": "undercarriage",
}

# Anchors a walkaround cannot omit and still sell the unit.
REQUIRED_ANCHORS = ("hero", "dash", "front_seats")

# Proof shots. Buyers need them; they must never be the thumbnail.
NON_HERO: frozenset[str] = frozenset({"odometer", "vin", "undercarriage", "wheels"})

# Inside the cabin, for deciding whether a move crosses the body shell.
INTERIOR: frozenset[str] = frozenset({
    "dash", "front_seats", "rear_seats", "infotainment", "odometer", "cargo",
})

# Which face of the vehicle the camera is on -- feeds viewpoint.assess unchanged.
SIDE: dict[str, str] = {
    "hero": "front", "front": "front",
    "driver_side": "left", "passenger_side": "right",
    "rear": "rear", "cargo": "rear",
    "undercarriage": "above",
}

UNKNOWN = "other"


@dataclass(frozen=True)
class Part:
    key: str
    rank: int
    interior: bool

    @property
    def is_known(self) -> bool:
        return self.key != UNKNOWN

    @property
    def hero_eligible(self) -> bool:
        return self.is_known and self.key not in NON_HERO


def _tokens(label: str) -> list[str]:
    out, cur = [], []
    for ch in label.lower():
        if ch.isalpha() or ch.isdigit():
            cur.append(ch)
        else:
            if cur:
                out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def resolve(label: str) -> Part:
    """Map a dealer's filename to a canonical vehicle part.

    Same contract as rooms.resolve, so the planner does not know or care which
    taxonomy it was handed.
    """
    toks = _tokens(label)
    joined = "".join(toks)
    if joined in _RANK:
        return _part(joined)
    if joined in ALIASES:
        return _part(ALIASES[joined])

    # Multi-token phrases first, longest wins. "three-quarter front" is a hero
    # shot, not a front shot, and only the phrase carries that.
    best, best_len = None, 0
    for phrase, cand in ALIASES.items():
        if len(phrase) >= 5 and phrase in joined and len(phrase) > best_len:
            best, best_len = cand, len(phrase)
    if best:
        return _part(best)

    # Then the RIGHTMOST recognised token, because the head noun is what the
    # frame actually IS: "front seats" is seats, not the front of the car. Same
    # rule rooms.py uses, and it was learned the same way -- by getting it wrong.
    head = None
    for tok in toks:
        cand = tok if tok in _RANK else ALIASES.get(tok)
        if cand is not None:
            head = cand
    if head:
        return _part(head)

    # Unresolvable labels are KEPT as UNKNOWN, never dropped and never None --
    # a dealer's odd filename must not crash a job or silently lose a frame.
    return Part(UNKNOWN, len(TOUR_ORDER), False)

def _part(key: str) -> Part:
    return Part(key=key, rank=_RANK[key], interior=key in INTERIOR)
