#!/usr/bin/env python3
"""Assemble the two vehicle ads from the rendered OpenArt beats.

    python3 samples/cars/build.py            # both films
    python3 samples/cars/build.py ferrari    # one

Clips are located in this order, and the first hit wins:

  1. samples/cars/raw/          -- already ingested
  2. samples/inbox/             -- wherever the OpenArt zip was unpacked
  3. cdn.openart.ai             -- only from a machine whose egress allows it

Files keep whatever name OpenArt gave them. Every downloaded beat begins with
the numeric OpenArt id, and the manifest keys on that id, so an unsorted folder
of fifteen identically-shaped MP4s still lands in cut order. That matters more
than it sounds: the beats are all ~2s of the same car, and a human ordering them
by eye will get it wrong.

No disclosure card. Vehicle advertising has no altered-image rule to satisfy --
see business/07-compliance.md -- and compliance.check_placement enforces that
"none" stays unavailable to real estate.
"""

from __future__ import annotations

import json
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "pipeline"))

from flythrough.assemble import deliver, probe_duration       # noqa: E402
from flythrough.compliance import check_placement              # noqa: E402

MANIFEST = json.loads((HERE / "manifest.json").read_text())
SEARCH = (HERE / "raw", ROOT / "samples" / "inbox")


def find_local(beat: dict) -> Path | None:
    """Match on the OpenArt id prefix, not the full filename -- browsers and
    unzip tools both like to append ' (1)' and OpenArt's own names are long
    enough that people rename them."""
    stem = beat["id"] + "-"
    for folder in SEARCH:
        if not folder.is_dir():
            continue
        exact = folder / beat["file"]
        if exact.is_file():
            return exact
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.name.startswith(stem):
                return p
    return None


def locate(beat: dict, work: Path) -> Path:
    dest = work / f"beat_{beat['n']:02d}_{beat['id']}.mp4"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    local = find_local(beat)
    work.mkdir(parents=True, exist_ok=True)
    if local is not None:
        shutil.copy2(local, dest)
        print(f"  local   {beat['n']:>2}  {local.name}")
        return dest
    print(f"  fetch   {beat['n']:>2}  {beat['id']}")
    try:
        with urllib.request.urlopen(beat["url"], timeout=90) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise SystemExit(
            f"\n  MISSING beat {beat['n']} ({beat['id']}: "
            f"{beat['from']} -> {beat['to']})\n"
            f"    not found locally, and the CDN is unreachable here\n"
            f"    {type(exc).__name__}: {exc}\n\n"
            "  Unzip the OpenArt download and drop the MP4s into either\n"
            f"    {SEARCH[0]}\n    {SEARCH[1]}\n"
            "  Names do not matter as long as the OpenArt id prefix survives.\n"
        ) from None
    return dest


def build_one(slug: str) -> None:
    film = MANIFEST["films"][slug]
    check_placement("vehicles", film["disclosure"])   # refuses a bad pairing
    work, out = HERE / "work" / slug, HERE / "delivery"
    print(f"\n{film['title']}  --  {film['brief']}")
    clips = [locate(b, work) for b in film["beats"]]

    planned = sum(b["seconds"] for b in film["beats"])
    actual = sum(probe_duration(c) for c in clips)
    print(f"  {len(clips)} beats, {actual:.1f}s raw (planned {planned:.1f}s)")

    # Hard cuts. Every beat ends on the photograph the next one opens on, so the
    # boundary already matches -- a dissolve would only blur a frame pair that
    # was continuous to begin with. Ad and hype tempo want the cut audible.
    d = deliver(clips, out, slug=slug, crossfade=0.0, fps=30)
    print(f"  master   {d.master.name}   {d.duration:.1f}s")
    print(f"  vertical {d.vertical.name}")
    print(f"  thumb    {d.thumbnail.name}")


def main(argv: list[str]) -> int:
    if shutil.which("ffmpeg") is None:
        print("ffmpeg is not on PATH.", file=sys.stderr)
        return 2
    wanted = argv[1:] or list(MANIFEST["films"])
    for slug in wanted:
        if slug not in MANIFEST["films"]:
            print(f"unknown film {slug!r}; have "
                  f"{', '.join(MANIFEST['films'])}", file=sys.stderr)
            return 2
    for slug in wanted:
        build_one(slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
