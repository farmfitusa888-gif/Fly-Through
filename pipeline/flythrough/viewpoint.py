"""Viewpoint continuity — which side of the building a photo was taken from.

Added after a real failure in the first full demo tour. The closing shot paired a
patio still (shot from the lawn, looking at the REAR of the house) with an aerial
still framed over the FRONT. Asked to travel between them in one continuous move,
the model flew up and over and landed on what reads as a different house.

The model behaved correctly. The PLANNER was wrong to pair those frames.

`rooms.py` models which rooms connect. It says nothing about where the camera was
standing, so two photographs of opposite faces of the same building look equally
pairable. For interiors that rarely matters -- rooms genuinely connect. For
exteriors and aerials it matters completely, because there is no path from a
ground view of the back to an overhead view of the front that a single drone move
can plausibly describe.

This module supplies the missing axis. It is advisory by design: it warns and
re-orders rather than refusing, because a photographer who knows the property can
always override a heuristic about their own building.
"""

from __future__ import annotations

from dataclasses import dataclass

# Compass-free sides. Real listings are described relative to the street, not to
# north, and agents say "front" and "out back", never "the south elevation".
FRONT, REAR, LEFT, RIGHT, ABOVE, INSIDE, UNKNOWN = (
    "front", "rear", "left", "right", "above", "inside", "unknown"
)

OPPOSITE: dict[str, str] = {FRONT: REAR, REAR: FRONT, LEFT: RIGHT, RIGHT: LEFT}

# Tokens that place the camera. Longest match wins, so "backyard" beats "back".
SIDE_TOKENS: dict[str, str] = {
    "frontelevation": FRONT, "streetview": FRONT, "curbappeal": FRONT,
    "front": FRONT, "street": FRONT, "driveway": FRONT, "porch": FRONT,
    "entry": FRONT, "facade": FRONT, "approach": FRONT, "frontage": FRONT,
    "rearelevation": REAR, "backyard": REAR, "backgarden": REAR,
    "rear": REAR, "back": REAR, "patio": REAR, "deck": REAR, "pool": REAR,
    "terrace": REAR, "lanai": REAR, "yard": REAR, "garden": REAR,
    "left": LEFT, "leftside": LEFT, "westside": LEFT,
    "right": RIGHT, "rightside": RIGHT, "eastside": RIGHT,
    "side": UNKNOWN,
    "aerial": ABOVE, "drone": ABOVE, "overhead": ABOVE, "birdseye": ABOVE,
    "topdown": ABOVE, "sky": ABOVE,
}

# Rooms whose side is fixed by what they are, regardless of wording.
ROOM_SIDE: dict[str, str] = {
    "street": FRONT, "exterior": FRONT, "entry": FRONT,
    "patio": REAR, "pool": REAR, "yard": REAR,
    "aerial": ABOVE,
}


@dataclass(frozen=True)
class Risk:
    """A flagged transition, with the reason and the fix."""

    index: int
    from_label: str
    to_label: str
    severity: str          # "block" | "warn"
    reason: str
    fix: str


def side_of(label: str, room_key: str) -> str:
    """Where the camera was standing for this photo."""
    from .rooms import INTERIOR

    joined = "".join(c for c in label.lower() if c.isalpha())
    best, best_len = None, 0
    for tok, side in SIDE_TOKENS.items():
        if tok in joined and len(tok) > best_len and side != UNKNOWN:
            best, best_len = side, len(tok)
    if best:
        return best
    if room_key in ROOM_SIDE:
        return ROOM_SIDE[room_key]
    if room_key in INTERIOR:
        return INSIDE
    return UNKNOWN


def declared_side(label: str) -> str:
    """The side an AERIAL label explicitly declares, if any.

    An aerial is always ABOVE, but it is also always shot over one face of the
    building. `side_of` collapses that to ABOVE, which is right for choosing a
    camera move and wrong for checking continuity. This recovers the second axis
    so a correctly-framed aerial -- "13_rear-aerial" -- can pass the check that a
    front-framed one fails.
    """
    joined = "".join(c for c in label.lower() if c.isalpha())
    best, best_len = UNKNOWN, 0
    for tok, side in SIDE_TOKENS.items():
        if side in (FRONT, REAR, LEFT, RIGHT) and tok in joined and len(tok) > best_len:
            best, best_len = side, len(tok)
    return best


def assess(pairs: list[tuple[str, str, str, str]]) -> list[Risk]:
    """Flag transitions no single camera move can plausibly describe.

    `pairs` is (from_label, from_side, to_label, to_side) in tour order.
    """
    risks: list[Risk] = []
    for i, (a_label, a_side, b_label, b_side) in enumerate(pairs):
        # The failure that prompted this module: ground level on one face,
        # straight to an aerial framed over another.
        if b_side == ABOVE and a_side in (FRONT, REAR, LEFT, RIGHT):
            # An aerial that names its own side and matches the ground shot is
            # exactly what the client shot guide asks for. Do not warn on it --
            # a check that fires on correct work trains people to ignore it.
            if declared_side(b_label) == a_side:
                continue
            risks.append(Risk(
                index=i, from_label=a_label, to_label=b_label, severity="warn",
                reason=(
                    f"Rising from a ground view of the {a_side} of the house to an "
                    "aerial frame. If the aerial is not framed over that same "
                    "side, the model must invent a path across the building and "
                    "will typically land on what looks like a different house."
                ),
                fix=(
                    f"Shoot or choose an aerial framed over the {a_side} of the "
                    f"property, and name the file so it says so "
                    f"(e.g. \"13_{a_side}-aerial.jpg\"). Alternatively place the "
                    f"closing rise after a {a_side}-side exterior shot."
                ),
            ))
            continue

        if OPPOSITE.get(a_side) == b_side:
            risks.append(Risk(
                index=i, from_label=a_label, to_label=b_label, severity="block",
                reason=(
                    f"Travels from the {a_side} of the building directly to the "
                    f"{b_side}. No single continuous move crosses the house, so "
                    "the model will cut, teleport, or rebuild the far elevation."
                ),
                fix=(
                    "Insert a side or aerial shot between them, or split into two "
                    "sequences. Never join opposite elevations directly."
                ),
            ))
    return risks


def reorder_for_continuity(items: list[tuple[str, str]]) -> list[int]:
    """Indices reordered so same-side exteriors sit together.

    `items` is (room_key, side) in tour order. Interior order is untouched --
    rooms genuinely connect. Only exterior runs are grouped, so the tour walks
    one face of the building before moving to the next, and any aerial lands
    last where the closing rise belongs.
    """
    order = list(range(len(items)))
    exterior_idx = [i for i, (_, s) in enumerate(items)
                    if s in (FRONT, REAR, LEFT, RIGHT, ABOVE)]
    if len(exterior_idx) < 2:
        return order

    side_rank = {FRONT: 0, LEFT: 1, RIGHT: 2, REAR: 3, ABOVE: 4}
    grouped = sorted(exterior_idx, key=lambda i: (side_rank.get(items[i][1], 9), i))
    for slot, idx in zip(exterior_idx, grouped):
        order[slot] = idx
    return order
