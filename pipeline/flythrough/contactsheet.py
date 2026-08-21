"""Contact-sheet generation: N stills for the price of fewer renders.

Image models on OpenArt bill per OUTPUT, not per job -- verified 2026-08-20:
Nano Banana Pro at imageCount=4 quotes quantity=4, totalCredits=160, i.e. 4 x 40.
So asking for four images in one call saves nothing.

But resolution is billed in tiers, and the tiers are cheaper per pixel as they
go up. Verified for Nano Banana Pro at 16:9:

    2K  ->  2752 x 1536  =  40 credits
    4K  ->  5504 x 3072  =  80 credits          (exactly 2x the 2K pixel grid)

A 4K render laid out as a 2x2 contact sheet slices into FOUR tiles of
2752 x 1536 -- pixel-identical to a dedicated 2K render -- for 80 credits
instead of 160. Half price, no resolution loss.

This only helps where WE generate the stills: demo reels, portfolio pieces,
style tests. In the live business the agent supplies the photographs, so source
imagery costs nothing and this module is irrelevant to unit economics. It is a
production-cost tool, not a margin tool.

It does NOT work for video. Video is billed per second of output at a flat rate
(Wan 2.7: 25 cr/s at 720p, 35 cr/s at 1080p, linear and verified at 5s and 10s),
so a long render sliced into shots costs exactly what the separate shots cost.
Kling's multiShot is a continuity feature at the same 35 cr/s, not a discount.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

# Verified 2026-08-20 via openart_model_cost, Nano Banana Pro, 16:9.
TIER_PIXELS: dict[str, tuple[int, int]] = {
    "1K": (1376, 768),      # inferred as half of 2K; confirm before relying on it
    "2K": (2752, 1536),     # VERIFIED by generation
    "4K": (5504, 3072),     # VERIFIED by generation
}
TIER_CREDITS: dict[str, int] = {"1K": 40, "2K": 40, "4K": 80}   # VERIFIED for 2K/4K


@dataclass(frozen=True)
class SheetPlan:
    """A contact-sheet layout with its verified economics."""

    tier: str
    rows: int
    cols: int
    tile_w: int
    tile_h: int
    sheet_credits: int
    separate_credits: int

    @property
    def tiles(self) -> int:
        return self.rows * self.cols

    @property
    def saving(self) -> int:
        return self.separate_credits - self.sheet_credits

    @property
    def saving_pct(self) -> float:
        return self.saving / self.separate_credits if self.separate_credits else 0.0

    def describe(self) -> str:
        verdict = "WORTH IT" if self.saving > 0 else "NO SAVING -- render separately"
        return (
            f"{self.rows}x{self.cols} sheet at {self.tier} -> {self.tiles} tiles "
            f"of {self.tile_w}x{self.tile_h}\n"
            f"  sheet     {self.sheet_credits:>4} cr\n"
            f"  separate  {self.separate_credits:>4} cr "
            f"({self.tiles} x {TIER_CREDITS.get(tile_tier(self.tile_w, self.tile_h), 0)} cr)\n"
            f"  saving    {self.saving:>4} cr ({self.saving_pct:.0%})  {verdict}"
        )


def tile_tier(w: int, h: int) -> str:
    """Which paid tier a tile of this size is equivalent to."""
    for tier, (tw, th) in TIER_PIXELS.items():
        if (w, h) == (tw, th):
            return tier
    # Nearest tier by width, so an odd layout still prices honestly.
    return min(TIER_PIXELS, key=lambda t: abs(TIER_PIXELS[t][0] - w))


def plan_sheet(tier: str = "4K", rows: int = 2, cols: int = 2) -> SheetPlan:
    """Price a contact-sheet layout against rendering the tiles separately."""
    if tier not in TIER_PIXELS:
        raise KeyError(f"unknown tier {tier!r}; verified tiers: {sorted(TIER_PIXELS)}")
    sw, sh = TIER_PIXELS[tier]
    if sw % cols or sh % rows:
        raise ValueError(
            f"{tier} ({sw}x{sh}) does not divide evenly into {rows}x{cols}; "
            "an uneven slice crops content and is never worth the saving."
        )
    tw, th = sw // cols, sh // rows
    return SheetPlan(
        tier=tier, rows=rows, cols=cols, tile_w=tw, tile_h=th,
        sheet_credits=TIER_CREDITS[tier],
        separate_credits=rows * cols * TIER_CREDITS[tile_tier(tw, th)],
    )


def probe_size(path: str | Path) -> tuple[int, int]:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip().split(",")
    return int(out[0]), int(out[1])


def slice_sheet(
    sheet: str | Path,
    outdir: str | Path,
    *,
    rows: int = 2,
    cols: int = 2,
    names: list[str] | None = None,
) -> list[Path]:
    """Cut a contact sheet into its tiles.

    Tiles are written in reading order (left to right, top to bottom). `names`
    supplies room labels so the tiles land already named for the planner, which
    resolves rooms from filenames -- skipping a manual rename step that would
    otherwise eat the saving in operator time.
    """
    sheet = Path(sheet)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    w, h = probe_size(sheet)
    if w % cols or h % rows:
        raise ValueError(
            f"sheet is {w}x{h}, which does not divide evenly into {rows}x{cols}"
        )
    tw, th = w // cols, h // rows

    if names is not None and len(names) != rows * cols:
        raise ValueError(f"got {len(names)} names for {rows * cols} tiles")

    out: list[Path] = []
    for r in range(rows):
        for c in range(cols):
            i = r * cols + c
            stem = f"{i + 1:02d}_{names[i]}" if names else f"tile_{i + 1:02d}"
            dest = outdir / f"{stem}.png"
            subprocess.run(
                [FFMPEG, "-y", "-loglevel", "error", "-i", str(sheet),
                 "-vf", f"crop={tw}:{th}:{c * tw}:{r * th}", str(dest)],
                check=True, capture_output=True, text=True,
            )
            out.append(dest)
    return out
