"""Shot planner: turns a folder of listing photos into a rendered-shot plan.

The plan is the contract between the creative decisions and the render spend.
It is emitted as JSON before a single credit is spent, so the cost of a job is
known and reviewable up front -- that is deliberate, not incidental.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import moves as mv
from . import taxonomy as tx
from .rooms import Room, resolve
from .viewpoint import assess, side_of

IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff"})

# Anchors the tour must include to read as a complete property tour.
REQUIRED_ANCHORS = ("exterior", "living", "kitchen")


@dataclass
class Photo:
    """One source photograph with its resolved room and camera side."""

    path: str
    label: str
    room_key: str
    rank: int
    interior: bool
    order_hint: int          # leading number in the filename, if the agent used one
    index: int = 0
    side: str = "unknown"    # which face of the building the camera was on

    @property
    def room(self) -> Room:
        # Set by load_photos from the vertical's own taxonomy. It is an
        # undeclared attribute deliberately: dataclasses.asdict only walks
        # declared fields, so the resolved object never lands in the JSON.
        # The fallback keeps Photos built by hand (tests, the CLI) working.
        return getattr(self, "_resolved", None) or resolve(self.room_key)


@dataclass
class Shot:
    """One generated clip between two real photographs."""

    index: int
    move: str
    move_label: str
    seconds: int
    start_frame: str
    end_frame: str
    from_room: str
    to_room: str
    prompt: str
    negative_prompt: str


@dataclass
class Plan:
    """A complete, costed, renderable flythrough plan."""

    listing: str
    style: str
    resolution: str
    aspect: str
    shots: list[Shot] = field(default_factory=list)
    photos: list[Photo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    hero_frame: str | None = None

    @property
    def total_seconds(self) -> int:
        return sum(s.seconds for s in self.shots)

    def to_dict(self) -> dict:
        return {
            "listing": self.listing,
            "style": self.style,
            "resolution": self.resolution,
            "aspect": self.aspect,
            "total_seconds": self.total_seconds,
            "shot_count": len(self.shots),
            "hero_frame": self.hero_frame,
            "warnings": self.warnings,
            "photos": [asdict(p) for p in self.photos],
            "shots": [asdict(s) for s in self.shots],
        }

    def write(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2))
        return p


_LEADING_NUM = re.compile(r"^\s*(\d{1,3})\b")


def _order_hint(stem: str) -> int:
    """Agents commonly prefix filenames 01_, 02_ to force MLS order. Respect it."""
    m = _LEADING_NUM.match(stem)
    return int(m.group(1)) if m else 10_000


def load_photos(folder: str | Path, spec: tx.Spec | None = None) -> list[Photo]:
    """Read a photo folder into resolved Photo records.

    The label comes from the filename. If a sidecar mapping filename -> label
    is present, that wins, because an explicit label from the person who was
    standing there beats any inference. The sidecar is named per vertical --
    rooms.json, parts.json, facets.json -- so the advice printed in a warning
    is advice the reader can act on.
    """
    spec = spec or tx.of("rooms")
    folder = Path(folder)
    if not folder.is_dir():
        raise NotADirectoryError(f"photo folder not found: {folder}")

    override: dict[str, str] = {}
    sidecar = folder / spec.sidecar
    if sidecar.is_file():
        override = json.loads(sidecar.read_text())

    files = sorted(
        (f for f in folder.iterdir() if f.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda f: f.name.lower(),
    )
    if not files:
        raise ValueError(f"no images found in {folder}")

    photos: list[Photo] = []
    for f in files:
        label = override.get(f.name, f.stem)
        room = spec.resolve(label)
        photo = Photo(
            path=str(f),
            label=label,
            room_key=room.key,
            rank=room.rank,
            interior=room.interior,
            order_hint=_order_hint(f.stem),
            side=side_of(label, room.key),
        )
        photo._resolved = room
        photos.append(photo)
    return photos


def order_photos(photos: list[Photo]) -> list[Photo]:
    """Sort into buyer-walk order.

    If the agent numbered every file, that is an explicit running order and we
    honour it wholesale. Otherwise we sort by tour rank, breaking ties with any
    partial numbering and then filename, so the result is stable.
    """
    numbered = [p for p in photos if p.order_hint < 10_000]
    if len(numbered) == len(photos):
        ordered = sorted(photos, key=lambda p: (p.order_hint, p.path))
    else:
        ordered = sorted(photos, key=lambda p: (p.rank, p.order_hint, p.path))
    for i, p in enumerate(ordered):
        p.index = i
    return ordered


def _audit(photos: list[Photo], spec: tx.Spec | None = None) -> list[str]:
    """Flag what will make the finished video weak, before spending on it."""
    spec = spec or tx.of("rooms")
    warnings: list[str] = []
    present = {p.room_key for p in photos}

    missing = [a for a in spec.required_anchors if a not in present]
    if missing:
        warnings.append(
            "Missing tour anchor(s): " + ", ".join(missing)
            + ". The tour will still render but reads as incomplete to a buyer."
        )
    if len(photos) < 4:
        warnings.append(
            f"Only {len(photos)} photo(s). Below 4 the result is a clip, not a tour; "
            "8-14 is the range that produces a usable listing video."
        )
    for r in assess([
        (a.label, a.side, b.label, b.side) for a, b in zip(photos, photos[1:])
    ]):
        tag = "BLOCKS" if r.severity == "block" else "Risk"
        warnings.append(
            f"{tag} at shot {r.index} ({r.from_label} -> {r.to_label}): "
            f"{r.reason} FIX: {r.fix}"
        )

    unknown = [p.label for p in photos if p.room_key == "other"]
    if unknown:
        warnings.append(
            f"{len(unknown)} photo(s) had no recognisable {spec.unit} label "
            f"({', '.join(unknown[:3])}{'...' if len(unknown) > 3 else ''}). "
            f"They are kept in input order; add a {spec.sidecar} to place them "
            "precisely."
        )
    if not (set(spec.establishing) & present):
        warnings.append(
            f"No establishing shot ({', '.join(spec.establishing)}). "
            + spec.establishing_advice
        )
    return warnings


def _pick_hero(photos: list[Photo], spec: tx.Spec | None = None) -> str | None:
    """Choose the thumbnail frame: the earliest hero-eligible exterior, else any."""
    spec = spec or tx.of("rooms")
    for want in spec.hero_order:
        for p in photos:
            if p.room_key == want:
                return p.path
    for p in photos:
        if p.room.hero_eligible:
            return p.path
    return photos[0].path if photos else None


def build_plan(
    folder: str | Path,
    *,
    listing: str,
    style: str = "daylight",
    resolution: str = "1080p",
    aspect: str = "16:9",
    max_seconds: int | None = None,
    vertical: str = "rooms",
) -> Plan:
    """Build a complete shot plan from a photo folder.

    `vertical` selects the taxonomy: what the labels mean, what the prompt calls
    the subject, which suppressions the negative bank carries, and whether
    consecutive exteriors alternate orbit direction. It used to be absent, which
    meant every vertical planned as a house -- a vehicle order rendered with
    "camera orbits the house" and a negative bank that suppressed cars.

    max_seconds caps total runtime by dropping the lowest-value transitions
    (hallways and duplicate rooms first), never by truncating the tour, so the
    opener and closer always survive a budget cap.
    """
    if style not in mv.STYLES:
        raise ValueError(f"unknown style {style!r}; choose from {sorted(mv.STYLES)}")
    spec = tx.of(vertical)

    photos = order_photos(load_photos(folder, spec))
    plan = Plan(
        listing=listing,
        style=style,
        resolution=resolution,
        aspect=aspect,
        photos=photos,
        warnings=_audit(photos, spec),
        hero_frame=_pick_hero(photos, spec),
    )

    if max_seconds is not None:
        photos = _trim(photos, max_seconds, spec)
        plan.photos = photos
    pairs = list(zip(photos, photos[1:]))

    style_text = mv.STYLES[style]
    for i, (a, b) in enumerate(pairs):
        move = mv.select(a.room, b.room, index=i, total=len(pairs),
                         alternate_orbit=spec.alternate_orbit)
        plan.shots.append(
            Shot(
                index=i,
                move=move.key,
                move_label=move.label,
                seconds=move.seconds,
                start_frame=a.path,
                end_frame=b.path,
                from_room=a.room_key,
                to_room=b.room_key,
                prompt=mv.build_prompt(
                    move, a.room, b.room, style=style_text,
                    phrases=spec.phrases, subject=spec.subject,
                    subject_noun=spec.subject_noun, preserve=spec.preserve),
                negative_prompt=mv.negative_prompt(
                    move, exterior_extra=spec.exterior_negative,
                    interior_extra=spec.interior_negative),
            )
        )
    return plan


def _runtime(photos: list[Photo], spec: tx.Spec | None = None) -> int:
    """Total seconds a photo chain will render to."""
    spec = spec or tx.of("rooms")
    return sum(
        mv.select(a.room, b.room, index=i, total=len(photos) - 1,
                  alternate_orbit=spec.alternate_orbit).seconds
        for i, (a, b) in enumerate(zip(photos, photos[1:]))
    )


def _drop_value(photos: list[Photo], i: int, spec: tx.Spec | None = None) -> int:
    """How safe photo i is to remove. 0 means never remove.

    Removing a photo re-links its neighbours, so the tour stays continuous --
    this is the whole reason trimming operates on photos and not on transitions.
    The first and last photos are the opener and closer and are never removed,
    and neither is any photo whose room is a required tour anchor when it is the
    only one of its kind.
    """
    spec = spec or tx.of("rooms")
    if i == 0 or i == len(photos) - 1:
        return 0
    p = photos[i]
    if p.room_key in spec.required_anchors:
        same = sum(1 for q in photos if q.room_key == p.room_key)
        if same == 1:
            return 0
        return 1
    if p.room_key in spec.low_value:
        return spec.low_value[p.room_key]
    if p.room_key == "other":
        return 4
    # A duplicate of a room we already show elsewhere in the tour.
    if sum(1 for q in photos if q.room_key == p.room_key) > 1:
        return 3
    if p.interior:
        return 2
    return 1


def _trim(photos: list[Photo], max_seconds: int,
          spec: tx.Spec | None = None) -> list[Photo]:
    """Reduce the photo chain until it renders within max_seconds.

    Returns a contiguous chain -- every consecutive pair is still a real
    transition, so the finished video never jump-cuts between unrelated rooms.
    """
    spec = spec or tx.of("rooms")
    kept = list(photos)
    while len(kept) > 2 and _runtime(kept, spec) > max_seconds:
        ranked = [(_drop_value(kept, i, spec), i) for i in range(len(kept))]
        value, idx = max(ranked)
        if value == 0:
            break                                   # nothing left safe to cut
        kept.pop(idx)
    for i, p in enumerate(kept):
        p.index = i
    return kept
