"""Asset inventory — the mandatory check before any paid generation.

Written after a real, measurable failure: a 4K contact sheet containing
living / kitchen / primary bedroom / patio was generated, and then three of those
same four rooms were generated AGAIN as separate stills. 120 credits burned for
nothing, because nothing in the system knew what already existed.

That is a design defect, not a lapse of attention. Attention does not scale to an
operator running thirty jobs a month. So the fix is a gate: ask the inventory what
exists, and generate only the difference.

Two layers, deliberately:

  LocalRegistry   Authoritative. Written by us at generation time, so it records
                  exactly what was ordered and what it cost.
  provider scan   Safety net. Classifies whatever the provider already holds,
                  including assets made outside the pipeline (a web-UI render, an
                  earlier session). Heuristic, because it reads intent back out of
                  a stored prompt — it can only ever add caution, never remove it.

Rule: a room present in EITHER layer is never re-ordered without an explicit
override, and the override has to be a deliberate act.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .rooms import HEADS, resolve

# How much of a stored prompt to read when inferring its subject. Our prompts put
# the subject in the opening clause ("... photograph of the living room of ...");
# reading the whole prompt would pick up every room it merely mentions.
SUBJECT_WINDOW = 120

SHEET_MARKERS = ("contact sheet", "grid of", "x2 grid", "2x2", "4x2", "quadrant")


@dataclass
class Asset:
    """One image already paid for."""

    asset_id: str
    url: str
    room: str
    width: int = 0
    height: int = 0
    model: str = ""
    is_sheet: bool = False
    sheet_rooms: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def rooms(self) -> set[str]:
        """Every room this asset can supply — a sheet supplies several."""
        return set(self.sheet_rooms) if self.is_sheet else {self.room}


def _looks_like_sheet(prompt: str) -> bool:
    p = prompt.lower()
    return any(m in p for m in SHEET_MARKERS)


# Quadrant / panel markers a contact-sheet prompt uses to name its cells.
PANEL_MARKERS = (
    "top left", "top right", "bottom left", "bottom right",
    "top centre", "top center", "bottom centre", "bottom center",
    "upper left", "upper right", "lower left", "lower right",
    "panel", "quadrant", "cell", "tile",
)


def _panel_segments(text: str) -> list[str]:
    """Split a sheet prompt into one segment per named cell.

    Only text that follows an explicit cell marker describes a cell. Everything
    before the first marker is shared styling and must not be mined for rooms.
    """
    low = text.lower()
    hits: list[int] = []
    for marker in PANEL_MARKERS:
        start = 0
        while (i := low.find(marker, start)) != -1:
            hits.append(i)
            start = i + 1
    if not hits:
        return []
    hits.sort()
    return [text[a:b] for a, b in zip(hits, hits[1:] + [len(text)])]


def _rooms_in(text: str) -> list[str]:
    """Rooms a contact sheet actually contains, one per named cell.

    Conservative by design. A false negative costs a duplicate render; a FALSE
    POSITIVE suppresses a room that is genuinely needed and ships a tour with a
    hole in it. The second failure is far worse, so this only reports rooms named
    inside an explicit cell marker, and never mines the shared styling preamble.
    """
    seen: list[str] = []
    for seg in _panel_segments(text):
        # Strip the marker itself so "top left" cannot contribute a head noun.
        body = seg
        for marker in PANEL_MARKERS:
            if body.lower().startswith(marker):
                body = body[len(marker):]
                break
        key = resolve(body[:60]).key
        if key != "other" and key not in seen:
            seen.append(key)
    return seen


def classify(record: dict) -> Asset:
    """Turn one provider history record into an Asset.

    Subject is inferred from the opening clause of the stored prompt. This is a
    heuristic and is documented as one — it exists to catch duplicates the local
    registry missed, never to authorise a generation.
    """
    prompt = record.get("prompt", "") or ""
    meta = record.get("metadata", {}) or {}
    sheet = _looks_like_sheet(prompt)

    return Asset(
        asset_id=record.get("id", ""),
        url=record.get("url", ""),
        room=resolve(prompt[:SUBJECT_WINDOW]).key if not sheet else "sheet",
        width=int(meta.get("width", 0) or 0),
        height=int(meta.get("height", 0) or 0),
        model=record.get("model", ""),
        is_sheet=sheet,
        sheet_rooms=_rooms_in(prompt) if sheet else [],
        note="contact sheet" if sheet else "",
    )


class LocalRegistry:
    """The authoritative record of what this project has already paid for."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.assets: list[Asset] = []
        if self.path.is_file():
            self.assets = [Asset(**a) for a in json.loads(self.path.read_text())]

    def add(self, asset: Asset) -> None:
        if any(a.asset_id == asset.asset_id for a in self.assets):
            return
        self.assets.append(asset)
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([asdict(a) for a in self.assets], indent=2))

    @property
    def rooms(self) -> set[str]:
        out: set[str] = set()
        for a in self.assets:
            out |= a.rooms
        return out


@dataclass
class Verdict:
    """What to generate, what already exists, and what would have been wasted."""

    wanted: list[str]
    have: dict[str, str]        # room -> asset id already covering it
    missing: list[str]
    credits_saved: int

    @property
    def is_clean(self) -> bool:
        return not self.have

    def describe(self, unit_credits: int = 40) -> str:
        lines = [f"Requested {len(self.wanted)} room(s): {', '.join(self.wanted)}"]
        if self.have:
            lines.append(f"  ALREADY HELD ({len(self.have)}) -- do not re-order:")
            for room, aid in self.have.items():
                lines.append(f"    {room:<14} covered by {aid}")
            lines.append(f"  Avoided waste: {self.credits_saved} credits")
        lines.append(
            f"  TO GENERATE ({len(self.missing)}): "
            + (", ".join(self.missing) if self.missing else "nothing")
        )
        return "\n".join(lines)


def check(
    wanted: list[str],
    *,
    registry: LocalRegistry | None = None,
    provider_records: list[dict] | None = None,
    unit_credits: int = 40,
) -> Verdict:
    """THE GATE. Call this before every paid image generation.

    Returns only the rooms genuinely absent from both layers. A room already held
    by a contact sheet counts as held — slicing it is free, re-rendering it is not.
    """
    held: dict[str, str] = {}

    if registry is not None:
        for a in registry.assets:
            for r in a.rooms:
                held.setdefault(r, a.asset_id)

    for rec in provider_records or []:
        a = classify(rec)
        for r in a.rooms:
            held.setdefault(r, a.asset_id)

    wanted_keys = [resolve(w).key for w in wanted]
    have = {r: held[r] for r in wanted_keys if r in held}
    missing = [r for r in wanted_keys if r not in held]

    return Verdict(
        wanted=wanted_keys,
        have=have,
        missing=missing,
        credits_saved=len(have) * unit_credits,
    )
