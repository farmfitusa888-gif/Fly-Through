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
    master_web: Path | None = None      # what gets sent to the client
    vertical_web: Path | None = None


def _motion_profile(path: str | Path, w: int = 96, h: int = 54) -> list[float]:
    """Mean pixel change between consecutive frames, cheaply."""
    r = subprocess.run(
        [FFMPEG, "-i", str(path), "-vf", f"scale={w}:{h}", "-pix_fmt", "gray",
         "-f", "rawvideo", "-"], capture_output=True)
    b, sz = r.stdout, w * h
    fr = [b[i:i + sz] for i in range(0, len(b) - sz + 1, sz)]
    return [sum(abs(x - y) for x, y in zip(fr[i], fr[i + 1])) / sz
            for i in range(len(fr) - 1)]


def trim_stalls(
    src: str | Path,
    out: str | Path,
    *,
    threshold: float = 0.08,
    min_trim: float = 0.0,
    max_trim_fraction: float = 0.32,
    keep_min: float = 0.60,
    fps: int = 30,
) -> Path:
    """Cut the FROZEN frames off both ends of an anchored clip.

    Cuts the held frame only, NOT the deceleration ramp. The ease-in and ease-out
    either side of an anchor is natural camera movement and reads as cinematic;
    removing it makes the whole cut feel rushed, which an operator correctly
    called out after an over-aggressive first pass took 26.3s down to 15.0s. The
    gate is therefore deliberately low -- it should catch a held image, and
    nothing that is still moving.

    THE PROBLEM THIS SOLVES, measured on a delivered tour: every anchored clip
    stalls at both ends. Middle-of-clip motion averaged ~13 units of mean pixel
    change; the first six frames averaged 0.6 and the last six 0.4 -- twenty to
    thirty times less. The model decelerates into its end anchor and accelerates
    out of its start anchor, which is correct behaviour for one shot and ruinous
    when you join them, because every seam becomes a double freeze: one dead tail
    immediately followed by one dead head.

    The result reads as a slideshow rather than a moving camera, which is exactly
    what an operator reported before this was measured.

    Trimming to where motion first and last exceeds `threshold` of the clip's own
    median removes the freeze without touching the middle. `max_trim` caps how
    much may be taken from either end so a genuinely slow shot is never gutted.
    """
    src, out = Path(src), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = _motion_profile(src)
    # Smooth before gating. The raw profile carries isolated single-frame spikes
    # inside an otherwise dead tail (measured: 1.16 and 0.69 among frames
    # averaging 0.2), and an unsmoothed gate latches onto those and refuses to
    # trim anything.
    k = 5
    prof = [sum(raw[max(0, i - k // 2): i + k // 2 + 1]) /
            len(raw[max(0, i - k // 2): i + k // 2 + 1]) for i in range(len(raw))] if raw else raw
    dur = probe_duration(src)
    if not prof:
        shutil.copy2(src, out)
        return out

    # Gate on the clip's own sustained motion, not its median. A median is pulled
    # down by the very stalls being removed, which is why a median gate left two
    # clips almost untrimmed while their heads still sat 15x below their middles.
    ordered = sorted(prof)
    sustained = ordered[int(len(ordered) * 0.7)] or 0.0
    gate = sustained * threshold

    # Require SUSTAINED motion, not a single moving frame. A clip can start
    # moving, stall again for half a second, then get going -- measured on a real
    # clip with a 0.53s dead patch seventeen frames in. Trimming to the first
    # moving frame leaves that patch inside the cut, where no crossfade can reach
    # it, and it reads as a pause in the middle of the shot.
    need = max(3, int(0.15 * fps))

    def sustained_from(indices) -> int:
        run = 0
        for i in indices:
            if prof[i] > gate:
                run += 1
                if run >= need:
                    return i
            else:
                run = 0
        return indices[0] if indices else 0

    fwd = list(range(len(prof)))
    first = max(0, sustained_from(fwd) - need + 1)
    last = min(len(prof) - 1, sustained_from(list(reversed(fwd))) + need - 1)

    # The stall is systematic -- it appeared on both ends of every clip measured --
    # so a small floor is applied even when the gate does not fire. Without it a
    # clip whose first frames happen to twitch keeps its freeze and the seam still
    # reads as a held image.
    # The cap must scale with clip length. Measured on a 4.97s anchored clip,
    # motion died 1.33s before the end -- 27% of the clip was a frozen hold on the
    # anchor frame. A fixed 0.55s cap silently blocked that cut, which is why the
    # seams still read as held images after the first fix.
    cap = int(max_trim_fraction * dur * fps)
    floor = int(min_trim * fps)
    head = min(max(first, floor), cap)
    tail = min(max(len(prof) - 1 - last, floor), cap)

    # Never trim a clip below something renderable.
    if (len(prof) - head - tail) / fps < keep_min:
        spare = max(0, len(prof) - int(keep_min * fps))
        head = min(head, spare // 2)
        tail = min(tail, spare - head)

    start = head / fps
    end = max(dur - tail / fps, start + 1.0 / fps)

    _run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{start:.3f}",
          "-to", f"{end:.3f}", "-i", str(src),
          "-c:v", "libx264", "-crf", "18", "-preset", "medium",
          "-pix_fmt", "yuv420p", "-an", str(out)])
    return out


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

    # Normalise every input first: xfade and concat both require identical
    # geometry, fps and pixel format, and AI providers guarantee none of the three.
    chains: list[str] = [
        f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps={fps},format=yuv420p,setpts=PTS-STARTPTS[v{i}]"
        for i in range(len(clips))
    ]

    frame = 1.0 / fps
    if crossfade < frame:
        # HARD CUT. This is the right seam for anchored shots: shot N ends on the
        # same photograph shot N+1 begins on, so the boundary frames already
        # match and there is nothing to dissolve -- a crossfade would only soften
        # a picture that was already continuous.
        #
        # It is also a correctness fix. xfade with a sub-frame duration formats to
        # 0.000 and silently drops a clip, so anything below one frame MUST take
        # this path rather than a degenerate dissolve.
        inputs = "".join(f"[v{i}]" for i in range(len(clips)))
        chains.append(f"{inputs}concat=n={len(clips)}:v=1:a=0[out]")
        final = "out"
    else:
        # Chain the crossfades. Each xfade shortens the timeline by `crossfade`
        # seconds, so every offset is computed against the running total rather
        # than the raw clip start -- the classic xfade bug is using the latter and
        # landing every later transition in the wrong place.
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
        final = prev

    args += ["-filter_complex", ";".join(chains), "-map", f"[{final}]",
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


def web_encode(src: str | Path, out: str | Path, *, crf: int = 21) -> Path:
    """Re-encode for delivery: smaller file, instant streaming.

    A CRF-18 master runs ~12 Mbps, which is too heavy to email and over the
    upload limit on several MLS platforms. CRF 21 with faststart lands near
    8 Mbps with no visible loss and starts playing before it finishes loading,
    because the moov atom moves to the front of the file.
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _run([FFMPEG, "-y", "-loglevel", "error", "-i", str(src),
          "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
          "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(out)])
    return out


def deliver(
    clips: list[str | Path],
    outdir: str | Path,
    *,
    slug: str,
    crossfade: float = 0.2,
    fps: int = 30,
    music: str | Path | None = None,
    make_vertical: bool = True,
    make_thumb: bool = True,
    trim: bool = True,
) -> Deliverables:
    """Produce the full delivery set from rendered shot clips.

    Stall trimming is ON by default and is not an optional polish step. Anchored
    clips hold their end frame; a compilation of untrimmed clips measured 43.8%
    frozen frames and read as a slideshow rather than a moving camera. Passing
    trim=False is only correct when the clips have already been trimmed.
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if trim:
        work = outdir / "_trimmed"
        work.mkdir(exist_ok=True)
        clips = [trim_stalls(c, work / f"{i:02d}_{Path(c).stem}.mp4")
                 for i, c in enumerate(clips)]

    master = concat(clips, outdir / f"{slug}_master_16x9.mp4",
                    crossfade=crossfade, fps=fps)
    if music:
        master = add_music(master, music, outdir / f"{slug}_master_16x9_music.mp4")

    vertical = to_vertical(master, outdir / f"{slug}_vertical_9x16.mp4") if make_vertical else None
    thumb = thumbnail(master, outdir / f"{slug}_thumb.jpg") if make_thumb else None

    # Web/MLS encodes are what actually get sent; the CRF-18 masters are archive.
    master_web = web_encode(master, outdir / f"{slug}_master_web.mp4")
    vertical_web = (web_encode(vertical, outdir / f"{slug}_vertical_web.mp4")
                    if vertical else None)

    return Deliverables(
        master=master,
        vertical=vertical,
        thumbnail=thumb,
        duration=probe_duration(master),
        master_web=master_web,
        vertical_web=vertical_web,
    )
