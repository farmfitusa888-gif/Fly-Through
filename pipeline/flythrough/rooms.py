"""Room taxonomy and buyer-walk ordering.

The tour order is not arbitrary. It mirrors the sequence a listing agent walks a
buyer through in person, which is also the sequence that tests best in real-estate
video: establish the property from outside, cross the threshold, deliver the two
rooms that sell the house (living + kitchen), then private space, then outdoor,
then pull out to context. Photos that do not map to a known room are appended in
input order before the outro so nothing the agent uploaded is silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass

# Canonical room keys in tour order. Lower rank plays earlier.
TOUR_ORDER: tuple[str, ...] = (
    "street",       # approach / neighbourhood context
    "exterior",     # front elevation, the establishing hero shot
    "entry",        # foyer, front door, threshold crossing
    "living",       # great room / family room -- primary selling shot
    "kitchen",      # second primary selling shot
    "dining",
    "office",
    "hallway",      # connective tissue, never a hero shot
    "primary_bed",
    "primary_bath",
    "bedroom",
    "bathroom",
    "laundry",
    "basement",
    "garage",
    "patio",        # deck / porch / lanai
    "pool",
    "yard",
    "view",         # the money view: water, mountain, skyline
    "aerial",       # drone pull-out, the closing shot
)

_RANK: dict[str, int] = {key: i for i, key in enumerate(TOUR_ORDER)}

# Free-text -> canonical key. Agents label folders and filenames inconsistently;
# this is the normalisation layer so the planner never sees raw human labels.
ALIASES: dict[str, str] = {
    "front": "exterior", "facade": "exterior", "elevation": "exterior",
    "curb": "exterior", "frontage": "exterior", "house": "exterior",
    "road": "street", "approach": "street", "driveway": "street",
    "neighborhood": "street", "neighbourhood": "street",
    "foyer": "entry", "porch": "entry", "door": "entry", "mudroom": "entry",
    "great": "living", "greatroom": "living", "family": "living",
    "livingroom": "living", "lounge": "living", "den": "living",
    "sitting": "living",
    "kitchenette": "kitchen", "pantry": "kitchen", "breakfast": "kitchen",
    "diningroom": "dining", "diner": "dining",
    "study": "office", "library": "office", "workspace": "office",
    "corridor": "hallway", "stairs": "hallway", "staircase": "hallway",
    "landing": "hallway",
    "master": "primary_bed", "masterbed": "primary_bed",
    "masterbedroom": "primary_bed", "primary": "primary_bed",
    "primarybedroom": "primary_bed", "suite": "primary_bed",
    "masterbath": "primary_bath", "ensuite": "primary_bath",
    "primarybath": "primary_bath",
    "bed": "bedroom", "guest": "bedroom", "guestroom": "bedroom",
    "nursery": "bedroom",
    "bath": "bathroom", "powder": "bathroom", "washroom": "bathroom",
    "ensuite2": "bathroom",
    "utility": "laundry", "mud": "laundry",
    "cellar": "basement", "rec": "basement", "recroom": "basement",
    "carport": "garage", "shop": "garage", "workshop": "garage",
    "deck": "patio", "balcony": "patio", "terrace": "patio",
    "lanai": "patio", "veranda": "patio",
    "spa": "pool", "hottub": "pool", "poolside": "pool",
    "lawn": "yard", "garden": "yard", "backyard": "yard",
    "acreage": "yard", "lot": "yard", "grounds": "yard",
    "vista": "view", "waterfront": "view", "lake": "view",
    "ocean": "view", "mountain": "view", "skyline": "view",
    "drone": "aerial", "overhead": "aerial", "birdseye": "aerial",
    "topdown": "aerial", "sky": "aerial",
}

# Rooms that must never be used as the single hero/thumbnail frame.
NON_HERO: frozenset[str] = frozenset({"hallway", "laundry", "garage", "bathroom"})

# Interior rooms -- used to decide whether a transition crosses the building
# envelope, which changes the camera move that reads as natural.
INTERIOR: frozenset[str] = frozenset({
    "entry", "living", "kitchen", "dining", "office", "hallway",
    "primary_bed", "primary_bath", "bedroom", "bathroom",
    "laundry", "basement", "garage",
})

UNKNOWN = "other"


@dataclass(frozen=True)
class Room:
    """A resolved room label with its position in the tour."""

    key: str
    rank: int
    interior: bool

    @property
    def is_known(self) -> bool:
        return self.key != UNKNOWN

    @property
    def hero_eligible(self) -> bool:
        return self.is_known and self.key not in NON_HERO


# Qualifier tokens that upgrade a head noun to its "primary" variant.
QUALIFIERS: frozenset[str] = frozenset({
    "master", "primary", "main", "owners", "owner", "ensuite", "suite",
})

# Head nouns: the last one of these in a label is what the room actually IS.
# "guest bath" is a bath; "backyard pool" is a pool; "pool house" is a house.
HEADS: dict[str, str] = {
    "bath": "bathroom", "bathroom": "bathroom", "washroom": "bathroom",
    "powder": "bathroom", "shower": "bathroom", "wc": "bathroom",
    "bed": "bedroom", "bedroom": "bedroom", "nursery": "bedroom",
    "kitchen": "kitchen", "kitchenette": "kitchen", "pantry": "kitchen",
    "living": "living", "livingroom": "living", "lounge": "living",
    "den": "living", "family": "living", "great": "living",
    "greatroom": "living", "sitting": "living", "parlor": "living",
    "dining": "dining", "diningroom": "dining", "breakfast": "dining",
    "office": "office", "study": "office", "library": "office",
    "hallway": "hallway", "hall": "hallway", "corridor": "hallway",
    "stairs": "hallway", "staircase": "hallway", "landing": "hallway",
    "entry": "entry", "foyer": "entry", "entryway": "entry",
    "mudroom": "entry", "vestibule": "entry",
    "laundry": "laundry", "utility": "laundry",
    "basement": "basement", "cellar": "basement",
    "garage": "garage", "carport": "garage", "workshop": "garage",
    "shop": "garage",
    "patio": "patio", "deck": "patio", "balcony": "patio",
    "terrace": "patio", "lanai": "patio", "veranda": "patio",
    "porch": "patio",
    "pool": "pool", "spa": "pool", "hottub": "pool", "jacuzzi": "pool",
    "yard": "yard", "lawn": "yard", "garden": "yard", "grounds": "yard",
    "acreage": "yard", "lot": "yard", "backyard": "yard", "field": "yard",
    "view": "view", "vista": "view", "waterfront": "view", "lake": "view",
    "ocean": "view", "mountain": "view", "skyline": "view", "beach": "view",
    "aerial": "aerial", "drone": "aerial", "overhead": "aerial",
    "birdseye": "aerial", "topdown": "aerial", "sky": "aerial",
    "exterior": "exterior", "front": "exterior", "facade": "exterior",
    "elevation": "exterior", "curb": "exterior", "frontage": "exterior",
    "house": "exterior", "home": "exterior", "rear": "exterior",
    "street": "street", "road": "street", "approach": "street",
    "driveway": "street", "neighborhood": "street", "neighbourhood": "street",
}

# What a qualifier upgrades a head to, when such a room exists.
UPGRADE: dict[str, str] = {"bedroom": "primary_bed", "bathroom": "primary_bath"}


def _tokens(label: str) -> list[str]:
    """Split a human label into lowercase alphabetic tokens.

    Handles the real shapes agents produce: '01_Master-Bedroom.jpg',
    'kitchen (2).png', 'IMG_4471 front elevation.jpeg'.
    """
    out: list[str] = []
    current: list[str] = []
    for ch in label.lower():
        if ch.isalpha():
            current.append(ch)
        else:
            if current:
                out.append("".join(current))
            current = []
    if current:
        out.append("".join(current))
    return out


def resolve(label: str) -> Room:
    """Map any human label to a canonical Room.

    Resolution order: exact canonical key, then exact alias, then a token scan
    that prefers the earliest-ranked match so 'primary bedroom' resolves to
    primary_bed rather than bedroom. Unresolvable labels become UNKNOWN and are
    kept, never discarded.
    """
    # Strip separators AND digits: agents prefix filenames "09_master-bath".
    toks = _tokens(label)
    joined = "".join(toks)

    # 1. Exact canonical key or exact alias on the whole normalised label.
    if joined in _RANK:
        return _room(joined)
    if joined in ALIASES:
        return _room(ALIASES[joined])

    # 2. Head-noun parse. The rightmost recognised head noun is what the room
    #    IS; qualifiers anywhere before it can upgrade it. This is why
    #    "guest bath" is a bathroom and "master bath" is a primary_bath, even
    #    though both contain a token that maps elsewhere on its own.
    head_key: str | None = None
    head_pos = -1
    for i, tok in enumerate(toks):
        cand = HEADS.get(tok)
        if cand is not None:
            head_key, head_pos = cand, i

    if head_key is not None:
        qualified = any(t in QUALIFIERS for t in toks[:head_pos]) or (
            # A trailing qualifier still qualifies: "bath, primary".
            any(t in QUALIFIERS for t in toks[head_pos + 1:])
        )
        if qualified and head_key in UPGRADE:
            return _room(UPGRADE[head_key])
        if not qualified and head_key in UPGRADE:
            return _room(head_key)
        return _room(head_key)

    # 3. A bare qualifier with no head noun ("master", "primary") means the
    #    primary suite, which is how agents actually use the word alone.
    if any(t in QUALIFIERS for t in toks):
        return _room("primary_bed")

    # 4. Last resort: any alias phrase contained in the joined label.
    best: str | None = None
    best_len = 0
    for phrase, cand in ALIASES.items():
        if len(phrase) >= 4 and phrase in joined and len(phrase) > best_len:
            best, best_len = cand, len(phrase)

    return _room(best) if best else Room(UNKNOWN, len(TOUR_ORDER), False)


def _room(key: str) -> Room:
    return Room(key=key, rank=_RANK[key], interior=key in INTERIOR)
