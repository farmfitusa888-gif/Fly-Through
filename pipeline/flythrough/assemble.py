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


# A frame this close to its predecessor is held, not moving. Calibrated, not
# guessed: see the note inside trim_stalls.
STILL: float = 0.05


def trim_stalls(
    src: str | Path,
    out: str | Path,
    *,
    threshold: float = 0.04,
    min_run: float = 0.20,
    keep_min: float = 0.60,
    fps: int = 30,
) -> Path:
    """Remove ONLY the frozen run touching each edge. Nothing else.

    This is deliberately surgical, and three earlier attempts were not.

    An anchored clip settles onto its end frame and holds it. Measured across a
    real five-shot tour, those holds are SMALL -- 0.27s to 0.70s at an edge, about
    2.1s of genuine freeze across 26.3s of footage. Earlier versions of this
    function gated on "where does sustained motion begin" and cut 1.3-1.8s per
    clip, five times more than the actual freeze. That shortens every SHOT, which
    is why the result read as sped up even though playback rate never changed.
    An operator caught it immediately and was right.

    So: find the contiguous near-static run that touches the first frame, and the
    one that touches the last frame, and cut exactly those. A freeze in the middle
    of a shot is left alone -- it is part of the take, and cutting it would jump.

    Note also that a crossfade over a frozen tail EXTENDS the freeze rather than
    hiding it: blending two near-identical frames produces more near-identical
    frames. Frozen edges must be cut, not dissolved through.
    """
    src, out = Path(src), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = _motion_profile(src)
    dur = probe_duration(src)
    if not raw:
        shutil.copy2(src, out)
        return out

    # Walk the RAW profile, not a smoothed one. Smoothing was tried both ways and
    # both failed in opposite directions: a mean let a single spike inside a dead
    # tail lift the edge sample above the gate so no freeze was found at all, and
    # a median flattened the deceleration RAMP as well, so the walk ran straight
    # past the freeze and ate the easing. The ramp is the thing that must survive.
    #
    # Instead, tolerate spikes explicitly: a frozen run continues through up to
    # `spike_tolerance` consecutive above-gate frames, and only ends when the
    # footage is genuinely moving again.
    # Despike, do not smooth. Both smoothing attempts failed in opposite
    # directions -- a mean hid the freeze, a median ate the ramp. What is actually
    # needed is narrower: replace a lone above-gate frame that sits BETWEEN two
    # below-gate frames. That removes the measured spikes inside dead tails
    # (1.16 and 0.69 among frames averaging 0.17) and touches nothing else,
    # because a real deceleration ramp has CONSECUTIVE moving frames and so is
    # never despiked.
    prof = list(raw)

    # The gate is relative to how hard THIS clip moves, so grainy or noisy
    # footage -- where even a held frame measures something -- still resolves.
    # But relative alone breaks on a high-dynamic-range beat: a 2s hype cut that
    # spikes to 47 in the middle puts its 70th percentile at ~20, and 4% of that
    # is 0.82 -- above the 0.10-0.35 that ordinary DECELERATING footage reads.
    # Four Ferrari beats with no frozen frame at all lost 1.8s between them that
    # way, which is exactly the "you sped the whole thing up" failure again.
    #
    # So cap it. Measured against a synthesised freeze (last frame cloned for
    # 0.5s) on this same footage, genuinely held frames read 0.0015-0.012, while
    # the slowest real movement anywhere in these clips reads 0.100. STILL is set
    # between those two populations, an order of magnitude clear of both.
    # min() keeps whichever gate is stricter, so a low-motion clip still gets the
    # tighter relative one and nothing above STILL is ever called frozen.
    sustained = sorted(prof)[int(len(prof) * 0.7)] or 0.0
    gate = min(sustained * threshold, STILL)
    need = max(4, int(min_run * fps))

    for i in range(1, len(prof) - 1):
        if prof[i] >= gate and prof[i - 1] < gate and prof[i + 1] < gate:
            prof[i] = min(prof[i - 1], prof[i + 1])
    # The endpoints need despiking too, and this is not an edge case -- the very
    # last frame of a measured clip WAS the spike (1.16 against a dead tail
    # averaging 0.17), so the tail walk stopped at zero and trimmed nothing.
    if len(prof) > 1:
        if prof[0] >= gate and prof[1] < gate:
            prof[0] = prof[1]
        if prof[-1] >= gate and prof[-2] < gate:
            prof[-1] = prof[-2]

    def frozen_run(seq: list[float]) -> int:
        """Length of the unbroken frozen run at the START of seq."""
        n = 0
        for v in seq:
            if v >= gate:
                break
            n += 1
        return n

    head = frozen_run(prof)
    if head < need:
        head = 0

    tail = frozen_run(list(reversed(prof)))
    if tail < need:
        tail = 0

    if head == 0 and tail == 0:
        shutil.copy2(src, out)
        return out

    if (len(prof) - head - tail) / fps < keep_min:
        spare = max(0, len(prof) - int(keep_min * fps))
        head = min(head, spare // 2)
        tail = min(tail, spare - head)

    start = head / fps
    finish = max(dur - tail / fps, start + 1.0 / fps)
    _run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{start:.3f}",
          "-to", f"{finish:.3f}", "-i", str(src),
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
