"""One paid order -> one delivered film.

The pieces have existed since the beginning -- build_plan, build_jobs,
submit_all, deliver, build_pack -- but only ever wired together by hand in a
sample script. This is that wiring, once, so the service and a human running it
from a terminal take exactly the same path. A second implementation of "how a
film gets made" is how the demo and the product drift apart.

Provider calls live behind `submit` and `poll` callables. The pipeline does not
import a vendor SDK and never has.
"""

from __future__ import annotations

import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .assemble import concat, deliver
from .compliance import build_pack, check_placement
from .planner import build_plan
from .render import OpenArtAdapter, build_jobs, submit_all


# The style each vertical is cut in unless a brief overrides it.
DEFAULT_STYLE = {"rooms": "goldenhour", "vehicles": "lot", "products": "studio"}


@dataclass(frozen=True)
class Rendered:
    files: list[tuple[str, Path]]
    warnings: tuple[str, ...]
    seconds: float


def fetch(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return dest


def render_order(
    *,
    vertical: str,
    slug: str,
    originals: Path,
    out_dir: Path,
    brief: dict,
    placement: str,
    submit: Callable | None = None,
    poll: Callable | None = None,
    adapter=None,
    style: str | None = None,
    max_seconds: int | None = None,
    originals_url: str = "",
    tempo: str = "tour",
) -> list[tuple[str, Path]]:
    """Render and deliver one order. Returns [(kind, path)].

    `submit` and `poll` are the provider. They are required: there is no
    built-in fallback that quietly produces something, because a renderer that
    silently degrades is how a customer receives a slideshow and an invoice.
    """
    if submit is None or poll is None:
        raise RuntimeError(
            "render_order needs a provider: pass submit= and poll=. "
            "See pipeline/flythrough/render.py OpenArtAdapter.")
    check_placement(vertical, placement)      # refuses rooms + "none"

    originals, out_dir = Path(originals), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "work"
    work.mkdir(exist_ok=True)

    listing = (brief.get("Property address (as it appears on the listing)")
               or brief.get("VIN or stock number")
               or brief.get("Product name") or slug)

    chosen = style or _style_from_brief(brief) or DEFAULT_STYLE[vertical]
    plan = build_plan(originals, listing=listing, style=chosen,
                      max_seconds=max_seconds, vertical=vertical, tempo=tempo)

    jobs = build_jobs(plan, adapter or OpenArtAdapter())
    urls = submit_all(jobs, submit=submit, poll=poll)

    clips = [fetch(urls[i], work / f"shot_{i:02d}.mp4")
             for i in sorted(urls)]
    if not clips:
        raise RuntimeError("provider returned no clips")

    files: list[tuple[str, Path]] = []
    first = clips

    if placement == "lead_card":
        pack = build_pack(listing, _photo_specs(originals), out_dir,
                          url=originals_url, slug=slug)
        first = [concat([pack.card, clips[0]], work / "intro.mp4",
                        crossfade=0.5, fps=30), *clips[1:]]
        files.append(("disclosure", pack.page))

    d = deliver(first, out_dir, slug=slug, crossfade=0.0, fps=30)

    if placement == "mark_end":
        pack = build_pack(listing, _photo_specs(originals), out_dir,
                          url=originals_url, slug=slug)
        files.append(("disclosure", pack.page))

    files.append(("master", Path(d.master_web or d.master)))
    if d.vertical:
        files.append(("vertical", Path(d.vertical_web or d.vertical)))
    if d.thumbnail:
        files.append(("thumb", Path(d.thumbnail)))
    return files


def _style_from_brief(brief: dict) -> str | None:
    raw = str(brief.get("Daylight, golden hour or twilight", "")).lower()
    for key, style in (("twilight", "twilight"), ("golden", "goldenhour"),
                       ("daylight", "daylight")):
        if key in raw:
            return style
    return None


def _photo_specs(originals: Path) -> list[dict]:
    return [{"path": p.name, "room_key": p.stem.split("_", 1)[-1]}
            for p in sorted(originals.iterdir()) if p.is_file()]
