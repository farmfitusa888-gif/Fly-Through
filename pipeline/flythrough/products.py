"""Product taxonomy — the e-commerce / product-motion vertical.

Third taxonomy against the same contract as rooms.py and vehicles.py. The
planner still cannot tell which vertical it was handed.

WHY THIS AND NOT "AI UGC"

The obvious adjacent product is AI-generated UGC ads: a synthetic person
recommending something. That business is illegal, not merely risky.

  FTC Rule on Consumer Reviews and Testimonials, effective 2024-10-21, bans
  fake or AI-generated reviews and testimonials that misrepresent the
  reviewer's identity or experience. Civil penalties reach $53,088 per
  violation (2026). AI-generated testimonials are prohibited REGARDLESS OF
  DISCLOSURE -- a label does not cure it.

  The 2025 Endorsement Guides update requires synthetic personas be identified
  as non-human, and holds the brand liable for AI endorsements exactly as for
  human ones.

  New York's synthetic performer law, effective 2026-06-09, requires
  conspicuous disclosure of an AI performer in an ad: $1,000 first violation,
  $5,000 each thereafter.

So this module deliberately has NO person in it. What it sells is motion around
a real product, built from the client's real product photography, with no
testimonial, no endorsement, and no synthetic human anywhere in the frame. That
is legal, it is resellable, and it reuses the anchoring mechanism unchanged --
the client's photo A and photo B bound every shot, so the product in the ad is
provably the product being sold.

Compliance basis here is FTC truth-in-advertising -- the ad must not
misrepresent the product's appearance, size, colour or function. It is NOT
NAR/AB 723 (real estate) and NOT dealer advertising rules (vehicles). Do not
copy compliance.py into this vertical.
"""

from __future__ import annotations

from dataclasses import dataclass

# Order a product video actually works in: establish, orbit the form, show
# detail and scale, then the shot that closes -- the product in use context.
TOUR_ORDER: tuple[str, ...] = (
    "hero",          # three-quarter beauty shot, the establishing frame
    "front",
    "side",
    "back",
    "top",
    "detail",        # texture, stitching, finish
    "material",
    "open",          # lid off, unfolded, unzipped
    "interior",
    "scale",         # in-hand or beside a known object
    "in_use",
    "packaging",
    "accessories",
    "colorway",      # alternate finishes
    "size_chart",    # informational, never a hero
    "label",         # ingredients / spec panel, never a hero
)

_RANK: dict[str, int] = {k: i for i, k in enumerate(TOUR_ORDER)}

ALIASES: dict[str, str] = {
    "threequarter": "hero", "beauty": "hero", "main": "hero", "primary": "hero",
    "face": "front", "obverse": "front",
    "profile": "side", "leftside": "side", "rightside": "side",
    "rear": "back", "reverse": "back", "behind": "back",
    "overhead": "top", "flatlay": "top", "topdown": "top", "birdseye": "top",
    "closeup": "detail", "macro": "detail", "texture": "detail",
    "stitching": "detail", "finish": "detail", "hardware": "detail",
    "fabric": "material", "leather": "material", "swatch": "material",
    "opened": "open", "unfolded": "open", "unzipped": "open", "lidoff": "open",
    "inside": "interior", "lining": "interior", "compartment": "interior",
    "inhand": "scale", "held": "scale", "sizecomparison": "scale",
    "lifestyle": "in_use", "context": "in_use", "styled": "in_use",
    "onmodel": "in_use", "worn": "in_use",
    "box": "packaging", "unboxing": "packaging", "carton": "packaging",
    "included": "accessories", "whatsinthebox": "accessories", "kit": "accessories",
    "colour": "colorway", "color": "colorway", "variant": "colorway",
    "finishes": "colorway",
    # Canonical keys containing an underscore can never be matched by a token,
    # so every one of them needs a joined-form alias. size_chart, in_use and
    # colorway are the three that do.
    "sizing": "size_chart", "measurements": "size_chart", "dimensions": "size_chart",
    "sizechart": "size_chart", "chart": "size_chart",
    "inuse": "in_use", "using": "in_use",
    "colourway": "colorway",
    "ingredients": "label", "spec": "label", "specs": "label",
    "nutrition": "label", "care": "label",
}

# A product ad that omits these does not sell.
REQUIRED_ANCHORS = ("hero", "detail", "scale")

# Informational frames buyers need but that must never be the thumbnail.
NON_HERO: frozenset[str] = frozenset({"size_chart", "label", "packaging"})

# "Inside" the product, for deciding whether a move crosses its shell.
INTERIOR: frozenset[str] = frozenset({"interior", "open", "label"})

# Which face the camera is on -- feeds viewpoint.assess unchanged.
SIDE: dict[str, str] = {
    "hero": "front", "front": "front", "back": "rear",
    "top": "above", "side": "left",
}

# Facets whose photographs commonly contain a real person. These are ACCEPTED as
# source material but must be flagged at intake, because generating motion
# between two frames containing a real human does two bad things at once:
#
#   1. It animates an identifiable person's likeness. Without a signed release
#      covering synthesised motion, that is a right-of-publicity problem, and a
#      model release for stills does not automatically cover it.
#   2. It fights our own negative-prompt bank, which suppresses people in every
#      generated frame. The model is told to remove what the anchors insist on,
#      and the result degrades.
#
# House rule: use the client's on-model stills as reference, never as anchors.
# Anchor on the product-only frames and the tour still works.
PERSON_RISK: frozenset[str] = frozenset({"in_use", "scale"})

PHRASES: dict[str, str] = {
    "hero": "the three-quarter view of the product",
    "front": "the front of the product", "side": "the side of the product",
    "back": "the back of the product", "top": "the product from above",
    "detail": "a close detail of the product",
    "material": "the surface material", "open": "the product opened",
    "interior": "the inside of the product",
    "scale": "the product held for scale", "in_use": "the product in use",
    "packaging": "the packaging", "accessories": "the included accessories",
    "colorway": "an alternate finish", "size_chart": "the size chart",
    "label": "the label", "other": "the product",
}

# One continuous circuit around the object -- never reverse mid-orbit.
ALTERNATE_ORBIT = False

# The prompt has to say what the subject IS. Left unset it fell back to room
# language and a product film asked the model to preserve "architecture".
SUBJECT = "the product"
SUBJECT_NOUN = "product"
PRESERVE = "shape, proportions, materials, finish, colour, logos and text"

HERO_ORDER: tuple[str, ...] = ("hero", "front", "side", "in_use", "detail")

LOW_VALUE: dict[str, int] = {
    "size_chart": 5, "label": 5, "packaging": 4, "colorway": 4, "accessories": 4,
}

ESTABLISHING: tuple[str, ...] = ("hero", "front", "side", "back")
ESTABLISHING_ADVICE = (
    "A product film with no full view of the object opens on a detail of "
    "something the viewer has not seen yet; request a hero shot.")

SIDECAR = "facets.json"
UNIT, UNIT_PLURAL = "view", "views"

UNKNOWN = "other"


@dataclass(frozen=True)
class Facet:
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


def resolve(label: str) -> Facet:
    """Map a client's filename to a canonical product facet.

    Same resolution rule as the other taxonomies: longest multi-token phrase
    first, then the RIGHTMOST recognised token, because the head noun is what
    the frame actually is. Unresolvable labels return UNKNOWN, never None.
    """
    toks = _tokens(label)
    joined = "".join(toks)
    if joined in _RANK:
        return _facet(joined)
    if joined in ALIASES:
        return _facet(ALIASES[joined])

    best, best_len = None, 0
    for phrase, cand in ALIASES.items():
        if len(phrase) >= 5 and phrase in joined and len(phrase) > best_len:
            best, best_len = cand, len(phrase)
    if best:
        return _facet(best)

    head = None
    for tok in toks:
        cand = tok if tok in _RANK else ALIASES.get(tok)
        if cand is not None:
            head = cand
    if head:
        return _facet(head)

    return Facet(UNKNOWN, len(TOUR_ORDER), False)


def _facet(key: str) -> Facet:
    return Facet(key=key, rank=_RANK[key], interior=key in INTERIOR)
