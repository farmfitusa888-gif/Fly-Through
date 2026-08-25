"""What the planner needs to know about a vertical, gathered in one place.

`moves.py` was written to be taxonomy-driven from the start -- `build_prompt`,
`negative_prompt` and `select` all take the vocabulary as arguments. `planner.py`
was not: it imported `rooms` directly and called those functions with the
defaults, so every vertical planned as a house.

That is not a cosmetic problem. A Ferrari order was planning with the prompt
"camera orbits the house", the warning "add a rooms.json", and a negative bank
containing "cars appearing, cars disappearing" -- which is a suppression that
protects a driveway in a property tour and deletes the subject of a vehicle
walkaround. `moves.negative_prompt` says exactly that in its own docstring.
Nothing was passing it the extras that would have prevented it.

So this module reads a taxonomy module into everything the planner asks for,
falling back to room behaviour where a taxonomy stays silent. Rooms was the
first vertical and still supplies the defaults, which is why `rooms.py` needs no
knowledge of this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Callable

from . import products, rooms, vehicles

BY_NAME: dict[str, ModuleType] = {
    "rooms": rooms, "vehicles": vehicles, "products": products}

# Room behaviour, which is also the fallback for anything a taxonomy omits.
ROOM_ANCHORS = ("exterior", "living", "kitchen")
ROOM_HERO_ORDER = ("aerial", "exterior", "living", "kitchen", "view")
ROOM_LOW_VALUE = {"hallway": 5, "laundry": 5, "garage": 5, "bathroom": 5}
ROOM_ESTABLISHING = ("aerial", "exterior")


@dataclass(frozen=True)
class Spec:
    """Everything planner.py needs, with none of it hardcoded to one vertical."""

    name: str
    resolve: Callable[[str], object]
    required_anchors: tuple[str, ...]
    # Preference order for the thumbnail frame. Falls through to any
    # hero-eligible photo, which every taxonomy's resolved type can answer.
    hero_order: tuple[str, ...]
    # key -> how safe that photo is to drop when trimming to a runtime cap.
    # Higher is safer; 0 is never.
    low_value: dict[str, int]
    # Whether consecutive exteriors should alternate orbit direction. True for a
    # building; false for anything the viewer walks around in one circuit.
    alternate_orbit: bool
    phrases: dict[str, str] | None
    subject: str
    subject_noun: str
    preserve: str
    exterior_negative: tuple[str, ...] | None
    interior_negative: tuple[str, ...] | None
    # Keys that count as an establishing shot. Missing one is a warning, not a
    # block: the film renders, it just opens badly.
    establishing: tuple[str, ...]
    establishing_advice: str
    # Filename of the label-override sidecar, named per vertical because the
    # advice "add a rooms.json" is useless on a car.
    sidecar: str
    unit: str                 # what one photo is OF, for warning copy
    unit_plural: str


def of(which: str | ModuleType) -> Spec:
    """Build the spec for a vertical name or a taxonomy module."""
    mod = BY_NAME[which] if isinstance(which, str) else which
    name = mod.__name__.rsplit(".", 1)[-1]
    if name not in BY_NAME:
        raise KeyError(f"{name} is not a known taxonomy: {sorted(BY_NAME)}")

    def get(attr, default):
        return getattr(mod, attr, default)

    return Spec(
        name=name,
        resolve=mod.resolve,
        required_anchors=tuple(get("REQUIRED_ANCHORS", ROOM_ANCHORS)),
        hero_order=tuple(get("HERO_ORDER", ROOM_HERO_ORDER)),
        low_value=dict(get("LOW_VALUE", ROOM_LOW_VALUE)),
        alternate_orbit=bool(get("ALTERNATE_ORBIT", True)),
        phrases=get("PHRASES", None),
        subject=get("SUBJECT", "the house"),
        subject_noun=get("SUBJECT_NOUN", "property"),
        preserve=get("PRESERVE", "architecture, furniture, materials and colours"),
        exterior_negative=get("EXTERIOR_NEGATIVE", None),
        interior_negative=get("INTERIOR_NEGATIVE", None),
        establishing=tuple(get("ESTABLISHING", ROOM_ESTABLISHING)),
        establishing_advice=get(
            "ESTABLISHING_ADVICE",
            "A property video with no establishing shot of the building "
            "consistently underperforms; request one."),
        sidecar=get("SIDECAR", "rooms.json"),
        unit=get("UNIT", "room"),
        unit_plural=get("UNIT_PLURAL", "rooms"),
    )
