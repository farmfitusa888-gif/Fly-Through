"""Camera move library for anchored property flythroughs.

Every shot in this product is generated between two REAL photographs: the agent's
photo A is the first frame, photo B is the last frame. The model only invents the
travel between them. That constraint is the product -- it is why the houses in the
output are the actual houses -- and this module encodes which travel reads as a
real drone/gimbal move for each kind of transition.

Prompts here are written the way a DP writes a shot: one camera instruction, one
subject, one lighting note, no adjective soup. Long flowery prompts measurably
increase drift in image-to-video models because they give the model licence to
reinvent the scene rather than travel through it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .rooms import Room

# Failure modes observed in image-to-video real-estate work, suppressed globally.
# Fixing these here means every future shot inherits the fix -- never patch a
# rendered clip, patch the bank.
BASE_NEGATIVE: tuple[str, ...] = (
    "people", "human figures", "faces", "hands",
    "text", "watermark", "logo", "caption", "subtitles",
    "impossible geometry", "melting shapes", "warping edges",
    "fisheye distortion", "lens flare", "vignette",
    "camera shake", "handheld jitter", "motion blur",
    "flickering", "strobing", "colour shift", "exposure pumping",
    "cartoon", "illustration", "painting", "3d render look",
    "oversaturated", "hdr halo",
)

# Extra suppressions for exterior work, where sky and vegetation drift most.
EXTERIOR_NEGATIVE: tuple[str, ...] = (
    "morphing walls", "warping windows", "bending door frames",
    "extra rooms appearing", "changing sky", "moving clouds warping", "trees morphing",
    "cars appearing", "cars disappearing", "roof shape changing",
    "window count changing",
)

# Extra suppressions for interiors, where the model likes to redecorate.
INTERIOR_NEGATIVE: tuple[str, ...] = (
    "morphing walls", "melting furniture", "furniture changing shape",
    "extra rooms appearing", "furniture appearing", "furniture disappearing",
    "artwork changing", "reflections inventing rooms",
    "ceiling height changing", "floor pattern shifting",
)


@dataclass(frozen=True)
class Move:
    """One named camera move with the prompt fragment that produces it."""

    key: str
    label: str
    camera: str          # the camera instruction -- the load-bearing sentence
    pacing: str          # speed note; slow reads as expensive, fast reads as cheap
    seconds: int         # default duration this move needs to land
    exterior: bool       # whether this move happens outside the envelope
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# The library. Keys are stable -- shot plans reference them by key, so renaming
# one is a breaking change to saved plans.
# ---------------------------------------------------------------------------

MOVES: dict[str, Move] = {
    "approach_push": Move(
        key="approach_push",
        label="Approach push-in",
        camera="slow forward dolly along the approach toward the front of {subject}, camera at chest height, level horizon",
        pacing="slow, steady, constant velocity",
        seconds=5,
        exterior=True,
        notes="Opening shot. Establishes address and arrival.",
        tags=("opener",),
    ),
    "aerial_reveal": Move(
        key="aerial_reveal",
        label="Aerial reveal",
        camera="camera rises and pushes forward over {subject}, tilting down to hold {subject} centred",
        pacing="slow ascent, unhurried",
        seconds=6,
        exterior=True,
        notes="Hero establishing shot. Sells lot size and setting.",
        tags=("opener", "hero"),
    ),
    "orbit_left": Move(
        key="orbit_left",
        label="Orbit left",
        camera="camera orbits {subject} counter-clockwise at a constant radius, locked on {subject}",
        pacing="slow orbit, no acceleration",
        seconds=6,
        exterior=True,
        notes="Shows two elevations in one shot. Best for corner lots.",
        tags=("hero",),
    ),
    "orbit_right": Move(
        key="orbit_right",
        label="Orbit right",
        camera="camera orbits {subject} clockwise at a constant radius, locked on {subject}",
        pacing="slow orbit, no acceleration",
        seconds=6,
        exterior=True,
        tags=("hero",),
    ),
    "threshold": Move(
        key="threshold",
        label="Threshold crossing",
        camera="camera glides forward through the opening from outside to inside, holding centre",
        pacing="slow, continuous, no stop at the door",
        seconds=5,
        exterior=False,
        notes="The single most important cut in the tour. Never rush it.",
        tags=("transition",),
    ),
    "glide_through": Move(
        key="glide_through",
        label="Interior glide",
        camera="camera floats forward at chest height through the space and onward through the far opening, level horizon",
        pacing="slow, gimbal-smooth, constant height",
        seconds=5,
        exterior=False,
        notes="Workhorse interior transition. Reads as a stabilised gimbal walk.",
        tags=("transition",),
    ),
    "reveal_pan": Move(
        key="reveal_pan",
        label="Reveal pan",
        camera="camera holds position and pans smoothly to reveal the rest of the room, level horizon",
        pacing="slow pan, ease in and ease out",
        seconds=5,
        exterior=False,
        notes="Use when two photos are the same room from different angles.",
        tags=("transition",),
    ),
    "rise_over": Move(
        key="rise_over",
        label="Rise and continue",
        camera="camera rises smoothly while continuing forward, revealing more of the space beyond",
        pacing="slow lift, constant forward speed",
        seconds=5,
        exterior=False,
        notes="Good for double-height rooms and open stairs.",
        tags=("transition",),
    ),
    "step_down": Move(
        key="step_down",
        label="Descend and continue",
        camera="camera descends smoothly while continuing forward into the next space",
        pacing="slow drop, constant forward speed",
        seconds=5,
        exterior=False,
        tags=("transition",),
    ),
    "exit_to_light": Move(
        key="exit_to_light",
        label="Exit to daylight",
        camera="camera glides forward from inside out through the opening into daylight, exposure settling smoothly",
        pacing="slow, continuous, no stop at the frame",
        seconds=5,
        exterior=True,
        notes="Interior to exterior. Call out the exposure change or it pumps.",
        tags=("transition",),
    ),
    "enter_from_light": Move(
        key="enter_from_light",
        label="Enter from daylight",
        camera="camera glides forward from outside in through the opening, exposure settling smoothly",
        pacing="slow, continuous",
        seconds=5,
        exterior=False,
        tags=("transition",),
    ),
    "ground_to_air": Move(
        key="ground_to_air",
        label="Ground to air",
        camera="camera lifts vertically and cranes upward, tilting down to keep {subject} framed",
        pacing="steady climb, no hesitation",
        seconds=6,
        exterior=True,
        notes="Bridges any exterior shot into the aerial closer.",
        tags=("transition",),
    ),
    "pull_out": Move(
        key="pull_out",
        label="Closing pull-out",
        camera="camera climbs and pulls backward away from {subject}, revealing the surroundings",
        pacing="slow, decelerating to a hold",
        seconds=6,
        exterior=True,
        notes="Closing shot. Decelerate so the end card lands on a still frame.",
        tags=("closer",),
    ),
    "detail_push": Move(
        key="detail_push",
        label="Detail push-in",
        camera="camera pushes slowly straight in on {subject}, framing tightening, no lateral drift",
        pacing="very slow, constant, decelerating to a hold",
        seconds=5,
        exterior=False,
        notes=(
            "The beat that sells an interior or a finish. Not a travel move -- "
            "the camera goes nowhere, it just closes distance on one thing. "
            "Essential for advertising rhythm; a tour that only travels reads as "
            "a walkthrough, not an ad."
        ),
        tags=("detail",),
    ),
    "detail_drift": Move(
        key="detail_drift",
        label="Detail drift",
        camera="camera drifts slowly across {subject} at a fixed distance, holding focus on the surface",
        pacing="very slow lateral drift, no acceleration",
        seconds=5,
        exterior=False,
        notes="Second detail beat. Alternate with detail_push so consecutive "
              "close-ups do not read as the same shot twice.",
        tags=("detail",),
    ),
    "lateral_track": Move(
        key="lateral_track",
        label="Lateral track",
        camera="camera tracks sideways at a constant distance, holding the subject parallel to frame",
        pacing="slow, constant velocity",
        seconds=5,
        exterior=True,
        notes="For long frontages, fences, and acreage boundaries.",
        tags=("transition",),
    ),
}

# Transition rules, evaluated in order. First predicate that matches wins.
# (from_key_or_None, to_key_or_None, move_key)
_RULES: tuple[tuple[str | None, str | None, str], ...] = (
    ("street", "exterior", "approach_push"),
    (None, "aerial", "ground_to_air"),
    ("aerial", None, "pull_out"),
    ("exterior", "entry", "threshold"),
    ("street", "entry", "threshold"),
    ("patio", "living", "enter_from_light"),
    ("yard", None, "enter_from_light"),
    ("pool", None, "enter_from_light"),
)


DETAIL_KEYS: frozenset[str] = frozenset({
    "detail", "material", "infotainment", "wheels", "odometer", "vin",
    "label", "colorway",
})


def select(a: Room, b: Room, *, index: int, total: int,
           alternate_orbit: bool = True) -> Move:
    """Pick the camera move for the transition from room a to room b.

    Deterministic: the same plan always yields the same moves, which is what makes
    a re-render reproducible and a client revision cheap.
    """
    # A close-up destination is a detail beat, not a journey. Travelling into a
    # steering wheel produces a lurch; pushing in produces an advert.
    if b.key in DETAIL_KEYS:
        return MOVES["detail_push"] if index % 2 == 0 else MOVES["detail_drift"]

    # Explicit rules first.
    for from_key, to_key, move_key in _RULES:
        if (from_key is None or from_key == a.key) and (to_key is None or to_key == b.key):
            return MOVES[move_key]

    # Same room photographed twice -> pan rather than travel.
    if a.key == b.key and a.key != "other":
        return MOVES["reveal_pan"] if a.interior else MOVES["orbit_left"]

    # Crossing the building envelope.
    if a.interior and not b.interior:
        return MOVES["exit_to_light"]
    if not a.interior and b.interior:
        return MOVES["enter_from_light"]

    # Both outside. For a building, alternating the orbit direction stops
    # consecutive exteriors reading as one long identical move. For an object
    # you walk around -- a vehicle, a product -- reversing mid-orbit looks
    # broken, because the viewer is tracking one continuous circuit. The
    # taxonomy decides which behaviour is correct via alternate_orbit.
    if not a.interior and not b.interior:
        if not alternate_orbit:
            return MOVES["orbit_left"]
        return MOVES["orbit_left"] if index % 2 == 0 else MOVES["orbit_right"]

    # Both inside. Lift on the way up the tour, settle on the way down.
    if b.key in {"primary_bed", "primary_bath"}:
        return MOVES["rise_over"]
    if b.key in {"basement", "garage", "laundry"}:
        return MOVES["step_down"]
    return MOVES["glide_through"]


def negative_prompt(move: Move, *, exterior_extra: tuple[str, ...] | None = None,
                    interior_extra: tuple[str, ...] | None = None) -> str:
    """Build the negative prompt for a move from the shared banks.

    The extras are taxonomy-supplied because a suppression that protects one
    vertical destroys another: "cars appearing, cars disappearing" keeps a
    driveway stable in a property tour and deletes the subject of a vehicle
    walkaround. Verticals that are not buildings pass their own.
    """
    bank = list(BASE_NEGATIVE)
    if move.exterior:
        bank += list(EXTERIOR_NEGATIVE if exterior_extra is None else exterior_extra)
    else:
        bank += list(INTERIOR_NEGATIVE if interior_extra is None else interior_extra)
    return ", ".join(bank)


def build_prompt(move: Move, a: Room, b: Room, *, style: str,
                 phrases: dict[str, str] | None = None,
                 subject: str = "the house",
                 subject_noun: str = "property",
                 preserve: str = "architecture, furniture, materials and colours") -> str:
    """Compose the positive prompt for one shot.

    Order matters: camera instruction first (the model weights early tokens most),
    then pacing, then the continuity clause that tells it the two frames are the
    same real property, then the look.
    """
    where = _phrase(a, b, phrases)
    return (
        f"{move.camera.format(subject=subject)}. {move.pacing}. "
        f"{where} "
        f"The first and last frames are photographs of the same real {subject_noun}; "
        f"preserve the exact {preserve} in both frames "
        "and only move the camera between them. "
        f"{style}"
    )


def _phrase(a: Room, b: Room, phrases: dict[str, str] | None = None) -> str:
    """Say where the camera is going, in the vocabulary of the vertical.

    Defaults to room language. A taxonomy that is not about rooms passes its own
    map -- otherwise a car walkaround renders with the prompt "travelling from
    the space to the space", which tells the model nothing and invites drift.
    """
    names = phrases if phrases is not None else {
        "street": "the street approach", "exterior": "the front of the house",
        "entry": "the entryway", "living": "the living room",
        "kitchen": "the kitchen", "dining": "the dining room",
        "office": "the office", "hallway": "the hallway",
        "primary_bed": "the primary bedroom", "primary_bath": "the primary bathroom",
        "bedroom": "a bedroom", "bathroom": "a bathroom",
        "laundry": "the laundry room", "basement": "the lower level",
        "garage": "the garage", "patio": "the patio",
        "pool": "the pool", "yard": "the yard", "view": "the view",
        "aerial": "the property from above", "other": "the space",
    }
    if a.key == b.key:
        return f"Moving within {names.get(a.key, 'the space')}."
    return f"Travelling from {names.get(a.key, 'the space')} to {names.get(b.key, 'the space')}."


# Look presets. These are the only place tone is decided, so a brand-wide look
# change is one edit here rather than a re-write of every prompt.
STYLES: dict[str, str] = {
    "daylight": (
        "Bright natural daylight, clean white balance, realistic architectural "
        "photography, sharp focus throughout, cinematic 24fps."
    ),
    "goldenhour": (
        "Warm golden-hour sunlight, long soft shadows, realistic architectural "
        "photography, sharp focus throughout, cinematic 24fps."
    ),
    "twilight": (
        "Dusk exterior with warm interior lights glowing, deep blue sky, realistic "
        "architectural photography, sharp focus throughout, cinematic 24fps."
    ),
    "neutral": (
        "Even neutral lighting, true-to-life colour, realistic architectural "
        "photography, sharp focus throughout, cinematic 24fps."
    ),
    # Non-building verticals. "Architectural photography" is a real instruction
    # to the model, not decoration -- it pulls toward straight verticals and
    # wide interiors, which is wrong for an object shot.
    "showroom": (
        "Clean even showroom lighting, true-to-life colour, realistic commercial "
        "automotive photography, glossy controlled reflections, sharp focus "
        "throughout, cinematic 24fps."
    ),
    "lot": (
        "Bright overcast daylight, true-to-life colour, realistic commercial "
        "automotive photography, soft even shadows, sharp focus throughout, "
        "cinematic 24fps."
    ),
    "studio": (
        "Soft studio lighting on a seamless background, true-to-life colour, "
        "realistic commercial product photography, controlled highlights, "
        "sharp focus throughout, cinematic 24fps."
    ),
}
