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
        return resolve(self.room_key)


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


def load_photos(folder: str | Path) -> list[Photo]:
    """Read a photo folder into resolved Photo records.

    The room label comes from the filename. If an agent supplies a sidecar
    `rooms.json` mapping filename -> room, that wins, because an explicit label
    from the person who was standing in the room beats any inference.
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise NotADirectoryError(f"photo folder not found: {folder}")

    override: dict[str, str] = {}
    sidecar = folder / "rooms.json"
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
        room = resolve(label)
        photos.append(
            Photo(
                path=str(f),
                label=label,
                room_key=room.key,
                rank=room.rank,
                interior=room.interior,
                order_hint=_order_hint(f.stem),
                side=side_of(label, room.key),
            )
        )
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


def _audit(photos: list[Photo]) -> list[str]:
    """Flag what will make the finished video weak, before spending on it."""
    warnings: list[str] = []
    present = {p.room_key for p in photos}

    missing = [a for a in REQUIRED_ANCHORS if a not in present]
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
            f"{len(unknown)} photo(s) had no recognisable room label "
            f"({', '.join(unknown[:3])}{'...' if len(unknown) > 3 else ''}). "
            "They are kept in input order; add a rooms.json to place them precisely."
        )
    if "aerial" not in present and "exterior" not in present:
        warnings.append(
            "No exterior or aerial photo. A property video with no establishing "
            "shot of the building consistently underperforms; request one."
        )
    return warnings


def _pick_hero(photos: list[Photo]) -> str | None:
    """Choose the thumbnail frame: the earliest hero-eligible exterior, else any."""
    for want in ("aerial", "exterior", "living", "kitchen", "view"):
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
) -> Plan:
    """Build a complete shot plan from a photo folder.

    max_seconds caps total runtime by dropping the lowest-value transitions
    (hallways and duplicate rooms first), never by truncating the tour, so the
    opener and closer always survive a budget cap.
    """
    if style not in mv.STYLES:
        raise ValueError(f"unknown style {style!r}; choose from {sorted(mv.STYLES)}")

    photos = order_photos(load_photos(folder))
    plan = Plan(
        listing=listing,
        style=style,
        resolution=resolution,
        aspect=aspect,
        photos=photos,
        warnings=_audit(photos),
        hero_frame=_pick_hero(photos),
    )

    if max_seconds is not None:
        photos = _trim(photos, max_seconds)
        plan.photos = photos
    pairs = list(zip(photos, photos[1:]))

    style_text = mv.STYLES[style]
    for i, (a, b) in enumerate(pairs):
        move = mv.select(a.room, b.room, index=i, total=len(pairs))
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
                prompt=mv.build_prompt(move, a.room, b.room, style=style_text),
                negative_prompt=mv.negative_prompt(move),
            )
        )
    return plan


def _runtime(photos: list[Photo]) -> int:
    """Total seconds a photo chain will render to."""
    return sum(
        mv.select(a.room, b.room, index=i, total=len(photos) - 1).seconds
        for i, (a, b) in enumerate(zip(photos, photos[1:]))
    )


def _drop_value(photos: list[Photo], i: int) -> int:
    """How safe photo i is to remove. 0 means never remove.

    Removing a photo re-links its neighbours, so the tour stays continuous --
    this is the whole reason trimming operates on photos and not on transitions.
    The first and last photos are the opener and closer and are never removed,
    and neither is any photo whose room is a required tour anchor when it is the
    only one of its kind.
    """
    if i == 0 or i == len(photos) - 1:
        return 0
    p = photos[i]
    if p.room_key in REQUIRED_ANCHORS:
        same = sum(1 for q in photos if q.room_key == p.room_key)
        if same == 1:
            return 0
        return 1
    if p.room_key in {"hallway", "laundry", "garage", "bathroom"}:
        return 5
    if p.room_key == "other":
        return 4
    # A duplicate of a room we already show elsewhere in the tour.
    if sum(1 for q in photos if q.room_key == p.room_key) > 1:
        return 3
    if p.interior:
        return 2
    return 1


def _trim(photos: list[Photo], max_seconds: int) -> list[Photo]:
    """Reduce the photo chain until it renders within max_seconds.

    Returns a contiguous chain -- every consecutive pair is still a real
    transition, so the finished video never jump-cuts between unrelated rooms.
    """
    kept = list(photos)
    while len(kept) > 2 and _runtime(kept) > max_seconds:
        ranked = [(_drop_value(kept, i), i) for i in range(len(kept))]
        value, idx = max(ranked)
        if value == 0:
            break                                   # nothing left safe to cut
        kept.pop(idx)
    for i, p in enumerate(kept):
        p.index = i
    return kept
