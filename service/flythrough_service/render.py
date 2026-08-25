"""Bridge from a paid order to the existing pipeline.

Adds no rendering logic of its own. Everything here is arranging a customer's
uploads into the shape pipeline/flythrough already expects, calling it, and
storing what comes back. If a rule about how a film is made lives here, it is
in the wrong file.
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "pipeline") not in sys.path:
    sys.path.insert(0, str(ROOT / "pipeline"))

from flythrough import products, rooms, vehicles              # noqa: E402
from flythrough.assemble import deliver                        # noqa: E402
from flythrough.compliance import build_pack, check_placement   # noqa: E402
from flythrough.viewpoint import assess, side_of                # noqa: E402

TAXONOMY = {"rooms": rooms, "vehicles": vehicles, "products": products}

# Real estate can never opt out; the others have no altered-image rule to meet.
PLACEMENT = {"rooms": "mark_end", "vehicles": "none", "products": "none"}


@dataclass(frozen=True)
class Prepared:
    slug: str
    vertical: str
    photos: list[dict]        # {path, key, position}
    warnings: tuple[str, ...]      # shown to the customer, render continues
    blocks: tuple[str, ...] = ()   # render must not start until these are fixed


def slug_for(order_id: str, brief: dict) -> str:
    """Human-recognisable, filesystem-safe, and unique per order."""
    label = (brief.get("Property address (as it appears on the listing)")
             or brief.get("VIN or stock number")
             or brief.get("Product name") or "job")
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(label))
    safe = "-".join(p for p in safe.split("-") if p)[:48] or "job"
    return f"{safe}-{order_id.split('_', 1)[1][:8]}"


def prepare(vertical: str, uploads: list) -> Prepared:
    """Classify each upload through the vertical's own taxonomy and check the
    viewpoint chain. Warnings are surfaced to the customer, never swallowed."""
    mod = TAXONOMY[vertical]
    photos, keys = [], []
    for u in uploads:
        stem = Path(u["filename"]).stem
        key = (u["room_key"] or mod.resolve(stem).key)
        photos.append({"path": u["path"], "key": key,
                       "position": u["position"], "filename": u["filename"]})
        keys.append(key)
    # assess() wants consecutive (from_label, from_side, to_label, to_side)
    # in tour order -- the transitions, not the photos.
    ordered = sorted(photos, key=lambda x: x["position"])
    sides = [side_of(p["filename"], p["key"]) for p in ordered]
    pairs = [(ordered[i]["filename"], sides[i],
              ordered[i + 1]["filename"], sides[i + 1])
             for i in range(len(ordered) - 1)]
    risks = assess(pairs)
    # A block is a shot pair no camera move can describe -- the "different
    # house" failure. It stops the render; a warn only informs.
    warnings = tuple(f"{r.from_label} -> {r.to_label}: {r.reason}" for r in risks)
    blocks = tuple(r for r in risks if r.severity == "block")
    return Prepared(slug="", vertical=vertical, photos=ordered,
                    warnings=warnings, blocks=tuple(
                        f"{r.from_label} -> {r.to_label}: {r.fix}" for r in blocks))


def output_dir(data_dir: Path, order_id: str) -> Path:
    return Path(data_dir) / "renders" / order_id


def stage_originals(data_dir: Path, order_id: str, photos: list[dict]) -> Path:
    """Copy the content-addressed blobs into a named, ordered folder.

    The blobs are sha256 filenames; the disclosure page and the pipeline both
    want '01_kitchen.jpg'. Copies, never moves or renames in place -- the
    originals store is write-once and stays that way.
    """
    out = output_dir(data_dir, order_id) / "originals"
    out.mkdir(parents=True, exist_ok=True)
    staged = []
    for i, p in enumerate(sorted(photos, key=lambda x: x["position"]), 1):
        ext = Path(p["filename"]).suffix.lower() or ".jpg"
        dest = out / f"{i:02d}_{p['key']}{ext}"
        if not dest.exists():
            shutil.copy2(p["path"], dest)
        staged.append(dest)
    return out


def placement_for(vertical: str) -> str:
    p = PLACEMENT[vertical]
    check_placement(vertical, p)      # refuses an illegal pairing, in code
    return p
