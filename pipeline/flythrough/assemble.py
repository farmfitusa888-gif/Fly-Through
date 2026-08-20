"""Assembly: rendered clips -> delivered files.

One render produces three deliverables, which is where the margin in this
business actually lives:

  master   16:9 1080p  -- MLS, YouTube, the agent's website
  vertical 9:16 1080p  -- Reels, TikTok, Shorts
  thumb    single JPG  -- listing thumbnail / email hero

The vertical cut is a re-frame of footage already paid for, so its marginal cost
is CPU time, not credits. Charging for it separately is the single highest-margin
line item on the price sheet.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


class AssemblyError(RuntimeError):
    """Raised with ffmpeg's own stderr so failures are diagnosable, not opaque."""


def _run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-12:])
        raise AssemblyError(f"ffmpeg failed ({proc.returncode}):\n{tail}")


def probe_duration(path: str | Path) -> float:
    proc = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise AssemblyError(f"ffprobe failed on {path}: {proc.stderr.strip()[:200]}")
    return float(json.loads(proc.stdout)["format"]["duration"])


@dataclass
class Deliverables:
    master: Path
    vertical: Path | None
    thumbnail: Path | None
    duration: float


def concat(
    clips: list[str | Path],
    out: str | Path,
    *,
    crossfade: float = 0.4,
    width: int = 1920,
    height: int = 1080,
    fps: int = 24,
) -> Path:
    """Join clips into one master with crossfades between them.

    Crossfades matter here: a hard cut between two AI-generated shots exposes any
    residual drift at the seam, while a short dissolve reads as an intentional
    edit. 0.4s is long enough to hide a seam and short enough not to feel slow.
    """
    clips = [Path(c) for c in clips]
    if not clips:
        raise ValueError("no clips to assemble")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if len(clips) == 1:
        _run([FFMPEG, "-y", "-loglevel", "error", "-i", str(clips[0]),
              "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                     f"crop={width}:{height},fps={fps}",
              "-c:v", "libx264", "-crf", "18", "-preset", "medium",
              "-pix_fmt", "yuv420p", "-an", str(out)])
        return out

    durations = [probe_duration(c) for c in clips]

    args: list[str] = [FFMPEG, "-y", "-loglevel", "error"]
    for c in clips:
        args += ["-i", str(c)]

    # Normalise every input first: xfade requires identical geometry, fps and
    # pixel format, and AI providers do not guarantee any of the three.
    chains: list[str] = []
    for i in range(len(clips)):
        chains.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps},format=yuv420p,setpts=PTS-STARTPTS[v{i}]"
        )

    # Chain the crossfades. Each xfade shortens the timeline by `crossfade`
    # seconds, so every offset must be computed against the running total, not
    # the raw clip start -- getting this wrong is the classic xfade bug where
    # later transitions land in the wrong place.
    prev = "v0"
    running = durations[0]
    for i in range(1, len(clips)):
        fade = min(crossfade, durations[i] / 2, running / 2)
        offset = max(running - fade, 0.0)
        label = f"x{i}"
        chains.append(
            f"[{prev}][v{i}]xfade=transition=fade:duration={fade:.3f}:"
            f"offset={offset:.3f}[{label}]"
        )
        running = running + durations[i] - fade
        prev = label

    args += ["-filter_complex", ";".join(chains), "-map", f"[{prev}]",
             "-c:v", "libx264", "-crf", "18", "-preset", "medium",
             "-pix_fmt", "yuv420p", "-an", str(out)]
    _run(args)
    return out


def to_vertical(master: str | Path, out: str | Path, *, width: int = 1080, height: int = 1920) -> Path:
    """Re-frame the 16:9 master to 9:16 by centre-cropping the widescreen frame.

    Centre crop, not letterbox: a letterboxed listing video reads as recycled
    landscape footage and gets scrolled past. Cropping keeps the frame full-bleed.
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _run([FFMPEG, "-y", "-loglevel", "error", "-i", str(master),
          "-vf", f"scale=-2:{height},crop={width}:{height}:(iw-{width})/2:0",
          "-c:v", "libx264", "-crf", "18", "-preset", "medium",
          "-pix_fmt", "yuv420p", "-an", str(out)])
    return out


def thumbnail(master: str | Path, out: str | Path, *, at: float = 1.0) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _run([FFMPEG, "-y", "-loglevel", "error", "-ss", str(at), "-i", str(master),
          "-frames:v", "1", "-q:v", "2", str(out)])
    return out


def add_music(master: str | Path, music: str | Path, out: str | Path, *, fade_out: float = 2.0) -> Path:
    """Lay a music bed under the master, trimmed and faded to the video length."""
    out = Path(out)
    dur = probe_duration(master)
    _run([FFMPEG, "-y", "-loglevel", "error", "-i", str(master), "-i", str(music),
          "-filter_complex",
          f"[1:a]atrim=0:{dur:.3f},afade=t=out:st={max(dur - fade_out, 0):.3f}:"
          f"d={fade_out},volume=0.25[a]",
          "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
          "-shortest", str(out)])
    return out


def deliver(
    clips: list[str | Path],
    outdir: str | Path,
    *,
    slug: str,
    crossfade: float = 0.4,
    music: str | Path | None = None,
    make_vertical: bool = True,
    make_thumb: bool = True,
) -> Deliverables:
    """Produce the full delivery set from rendered shot clips."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    master = concat(clips, outdir / f"{slug}_master_16x9.mp4", crossfade=crossfade)
    if music:
        master = add_music(master, music, outdir / f"{slug}_master_16x9_music.mp4")

    vertical = to_vertical(master, outdir / f"{slug}_vertical_9x16.mp4") if make_vertical else None
    thumb = thumbnail(master, outdir / f"{slug}_thumb.jpg") if make_thumb else None

    return Deliverables(
        master=master,
        vertical=vertical,
        thumbnail=thumb,
        duration=probe_duration(master),
    )
