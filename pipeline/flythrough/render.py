"""Render adapters.

The planner produces a Plan; this module turns each Shot into a provider job.
Two adapters ship:

  OpenArtAdapter   Builds exact, schema-valid payloads for OpenArt's
                   image2video models. Schemas were read from OpenArt's own
                   openart_model_form_get tool, so the payloads validate against
                   the real contract rather than a guessed one.

  QueueAdapter     A generic submit/poll HTTP adapter for any provider that uses
                   the standard queue pattern (submit -> job id -> poll -> URL).
                   Endpoint, auth header and field names come from a provider
                   profile in config, because those differ per vendor and
                   hardcoding a guessed URL would be worse than configuring a
                   real one.

Nothing here spends credits implicitly. `build_jobs` is pure: it produces the
payloads and the cost, and submission is a separate, explicit call.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from .cost import DUAL_ANCHOR, quote
from .planner import Plan, Shot


@dataclass
class Job:
    """One render job: a provider payload plus the identity of the shot."""

    shot_index: int
    model: str
    mode: str
    params: dict[str, Any]
    seconds: int
    out_name: str


class Adapter(Protocol):
    """What every render backend must provide."""

    name: str

    def build(self, plan: Plan, shot: Shot) -> Job: ...


def _frame(path: str, label: str) -> dict[str, str]:
    """OpenArt frame reference. `url` must be a URL the provider can fetch,
    which for local files means uploading first -- see upload_frames()."""
    return {"type": "image", "id": Path(path).stem, "url": path, "label": label}


@dataclass
class OpenArtAdapter:
    """Payload builder for OpenArt image2video models with dual-frame anchoring."""

    model: str = "wan2-7"
    tier: str = "1080p"
    name: str = field(default="openart", init=False)

    def __post_init__(self) -> None:
        if self.model not in DUAL_ANCHOR:
            raise ValueError(
                f"{self.model} cannot anchor both frames; refusing to build jobs."
            )

    def build(self, plan: Plan, shot: Shot) -> Job:
        if self.model == "wan2-7":
            params: dict[str, Any] = {
                "prompt": shot.prompt,
                "negativePrompt": shot.negative_prompt,
                "videoCount": 1,
                "resolution": self.tier,
                "duration": shot.seconds,
                "startFrame": _frame(shot.start_frame, shot.from_room),
                "endFrame": _frame(shot.end_frame, shot.to_room),
                # Prompt expansion rewrites the prompt server-side, which
                # reintroduces exactly the invention the negative bank suppresses.
                "enablePromptExpansion": False,
            }
        elif self.model == "kling-3-omni":
            params = {
                "prompt": shot.prompt[:2500],
                "generateSound": False,   # music is added once at assembly, not per shot
                "resolution": self.tier,
                "duration": shot.seconds,
                "multiShot": False,
                "videoCount": 1,
                "startFrame": _frame(shot.start_frame, shot.from_room),
                "endFrame": _frame(shot.end_frame, shot.to_room),
            }
        else:
            raise NotImplementedError(
                f"no verified payload schema for {self.model}; add one only after "
                "reading its form schema from the provider."
            )
        return Job(
            shot_index=shot.index,
            model=self.model,
            mode="image2video",
            params=params,
            seconds=shot.seconds,
            out_name=f"shot_{shot.index:02d}_{shot.move}.mp4",
        )


@dataclass
class QueueAdapter:
    """Generic submit/poll adapter, configured from a provider profile.

    The profile supplies the pieces that genuinely differ per vendor:
        endpoint       full submit URL
        auth_header    e.g. "Authorization"
        auth_format    e.g. "Key {token}"
        field_map      our field name -> provider field name
        status_path    URL template for polling, with {id}
        result_key     dotted path to the video URL in the finished payload
    """

    profile: dict[str, Any]
    name: str = field(default="queue", init=False)

    def build(self, plan: Plan, shot: Shot) -> Job:
        fmap = self.profile.get("field_map", {})
        params = {
            fmap.get("prompt", "prompt"): shot.prompt,
            fmap.get("negative_prompt", "negative_prompt"): shot.negative_prompt,
            fmap.get("start_frame", "image_url"): shot.start_frame,
            fmap.get("end_frame", "end_image_url"): shot.end_frame,
            fmap.get("duration", "duration"): shot.seconds,
            fmap.get("resolution", "resolution"): self.profile.get("resolution", "1080p"),
        }
        params.update(self.profile.get("extra_params", {}))
        return Job(
            shot_index=shot.index,
            model=self.profile.get("model", "unknown"),
            mode="image2video",
            params=params,
            seconds=shot.seconds,
            out_name=f"shot_{shot.index:02d}_{shot.move}.mp4",
        )


def build_jobs(plan: Plan, adapter: Adapter) -> list[Job]:
    """Turn a plan into provider jobs. Pure -- spends nothing."""
    return [adapter.build(plan, s) for s in plan.shots]


def write_manifest(plan: Plan, jobs: list[Job], out: str | Path, *, model: str, tier: str) -> Path:
    """Write the reviewable job manifest: every payload plus the total cost.

    This file is the spend gate. It exists so a human can see exactly what will
    be sent and what it will cost before anything is submitted.
    """
    q = quote(seconds=plan.total_seconds, shots=len(plan.shots), model=model, tier=tier)
    doc = {
        "listing": plan.listing,
        "model": model,
        "tier": tier,
        "shot_count": len(jobs),
        "total_seconds": plan.total_seconds,
        "cost": {
            "credits_per_second": q.credits_per_second,
            "base_credits": q.base_credits,
            "expected_credits": q.expected_credits,
            "worst_case_credits": q.worst_case_credits,
            "usd_estimate_expected": round(q.expected_usd, 2),
            "usd_verified": False,
        },
        "warnings": plan.warnings,
        "jobs": [
            {
                "shot_index": j.shot_index,
                "model": j.model,
                "mode": j.mode,
                "seconds": j.seconds,
                "out_name": j.out_name,
                "params": j.params,
            }
            for j in jobs
        ],
    }
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2))
    return p


def submit_all(
    jobs: list[Job],
    submit: Callable[[Job], str],
    poll: Callable[[str], tuple[str, str | None]],
    *,
    interval: float = 6.0,
    timeout: float = 900.0,
) -> dict[int, str]:
    """Submit every job and poll until each finishes.

    `submit` returns a job id. `poll` returns (status, url_or_None) where status
    is one of PENDING / DONE / FAILED. Failures are reported per shot and do not
    abort the batch -- a 12-shot job losing one shot is a re-roll, not a restart.
    """
    ids = {j.shot_index: submit(j) for j in jobs}
    done: dict[int, str] = {}
    failed: dict[int, str] = {}
    deadline = time.monotonic() + timeout

    while ids and time.monotonic() < deadline:
        for idx, jid in list(ids.items()):
            status, url = poll(jid)
            if status == "DONE" and url:
                done[idx] = url
                ids.pop(idx)
            elif status == "FAILED":
                failed[idx] = jid
                ids.pop(idx)
        if ids:
            time.sleep(interval)

    if ids:
        raise TimeoutError(f"shots still pending after {timeout}s: {sorted(ids)}")
    if failed:
        raise RuntimeError(f"shots failed and need re-rolling: {sorted(failed)}")
    return done
