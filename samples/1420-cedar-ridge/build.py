#!/usr/bin/env python3
"""Assemble the 1420 Cedar Ridge demo tour from rendered OpenArt assets.

Run from the repo root, on a machine that can reach cdn.openart.ai:

    python3 samples/1420-cedar-ridge/build.py

Produces, in samples/1420-cedar-ridge/delivery/:
    1420-cedar-ridge_master_16x9.mp4     disclosure card + 5 shots, crossfaded
    1420-cedar-ridge_vertical_9x16.mp4   centre-cropped for Reels/TikTok
    1420-cedar-ridge_thumb.jpg
    1420-cedar-ridge_originals_qr.png
    originals.html                       the AB 723 unaltered-originals page
    1420-cedar-ridge_disclosure.json     MLS + social caption text

This exists as a script rather than a manual step because the build environment
that generated the assets could not reach the CDN. Everything it does is the
pipeline's own code -- it adds no logic of its own.
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

from flythrough.assemble import concat, deliver, probe_duration      # noqa: E402
from flythrough.compliance import build_pack                          # noqa: E402

ORIGINALS_URL = "https://flythrough.co/o/1420-cedar-ridge"


class FetchBlocked(RuntimeError):
    """Raised with an actionable message rather than a raw traceback."""


def fetch(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  cached  {dest.name}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  get     {dest.name}")
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise FetchBlocked(
            f"could not fetch {dest.name}\n"
            f"    {type(exc).__name__}: {exc}\n\n"
            "  This machine cannot reach cdn.openart.ai. That is usually a\n"
            "  corporate proxy or egress policy, not a problem with this script.\n"
            "  Run it from a machine with ordinary internet access, or download\n"
            "  the assets manually from your OpenArt history and place them as:\n"
            "    samples/1420-cedar-ridge/delivery/originals/NN_<room>.png\n"
            "    samples/1420-cedar-ridge/work/shot_NN_<move>.mp4\n"
            "  Already-present files are reused, so a partial download resumes."
        ) from None
    return dest


def main() -> int:
    if shutil.which("ffmpeg") is None:
        print("ffmpeg is not on PATH. Install it and re-run.", file=sys.stderr)
        return 2
    spec = json.loads((HERE / "assets.json").read_text())
    work = HERE / "work"
    out = HERE / "delivery"

    print("Fetching source stills (these become the disclosure originals)")
    stills = [
        fetch(s["url"], out / "originals" / f"{i + 1:02d}_{s['room']}.png")
        for i, s in enumerate(spec["stills"])
    ]

    print("Fetching rendered shots")
    clips = [
        fetch(s["url"], work / f"shot_{s['index']:02d}_{s['move']}.mp4")
        for s in sorted(spec["shots"], key=lambda s: s["index"])
    ]

    print("Building disclosure pack")
    pack = build_pack(
        spec["listing"],
        [{"path": str(p), "room_key": s["room"]}
         for p, s in zip(stills, spec["stills"])],
        out, url=ORIGINALS_URL, slug=spec["slug"],
    )

    # The disclosure card leads the master so it survives any re-post.
    # Hard cut between shots: every shot ends on the photograph the next one
    # begins on, so the boundary frames already match and a dissolve would only
    # soften a picture that was already continuous. 30fps matches the source
    # renders exactly, avoiding the judder a 30->24 conversion introduces.
    print("Assembling master (disclosure card + 5 shots, seamless hard cuts)")
    card_join = concat([pack.card, clips[0]], work / "intro.mp4",
                       crossfade=0.5, fps=30)          # card DOES need a dissolve
    d = deliver([card_join, *clips[1:]], out, slug=spec["slug"],
                crossfade=0.0, fps=30)

    print()
    print(f"  master   {d.master.name}   {d.duration:.1f}s")
    print(f"  vertical {d.vertical.name}")
    print(f"  thumb    {d.thumbnail.name}")
    print(f"  qr       {pack.qr.name}")
    print(f"  page     {pack.page.name}")
    print()
    print("  MLS remark to paste:")
    print(f"    {pack.caption}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FetchBlocked as exc:
        print(f"\n  BLOCKED: {exc}\n", file=sys.stderr)
        raise SystemExit(1)
