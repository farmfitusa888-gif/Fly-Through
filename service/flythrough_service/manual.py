"""Operator-rendered fulfilment.

The provider question turned out to have a simpler answer than a second
provider. OpenArt has no REST API, so the SERVER cannot call it -- but the
operator can, through the same MCP tools that produced every frame this project
has shipped so far. Nothing about the product requires the render to be
automatic; it requires the render to happen.

So an order can be worked by hand end to end, on the account that already
exists, with no integration, no new vendor and no second bill. This module
produces what an operator needs to do that: the plan, the exact prompts, the
anchor pairs in order, and the cost before anything is spent.

Automatic rendering stays worth having later, for volume. It is not a
prerequisite for taking money, and treating it as one would have held the
business behind an integration it does not yet need.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "pipeline") not in sys.path:
    sys.path.insert(0, str(ROOT / "pipeline"))

from flythrough import providers                       # noqa: E402
from flythrough.cost import USD_PER_CREDIT, quote, rate  # noqa: E402
from flythrough.planner import build_plan              # noqa: E402

from . import orders, render                            # noqa: E402


@dataclass(frozen=True)
class Brief:
    """Everything needed to render one order by hand, and nothing else."""
    order_id: str
    listing: str
    style: str
    shots: list[dict]
    warnings: tuple[str, ...]
    blocks: tuple[str, ...]
    total_seconds: int
    credits: int
    usd: float
    originals_dir: Path
    model: str = "wan2-7"
    tier: str = "1080p"
    # Field name the provider gives the shot length, and the range it accepts.
    # Read from the recorded schema so the sheet cannot drift from the form the
    # operator is actually typing into.
    duration_field: str = "duration"
    duration_min: int = 0
    duration_max: int = 0


def _settings(profile: dict, seconds: int, tier: str) -> list[dict]:
    """The fields the operator has to set by hand, and what they default to.

    This is the whole point of putting the sheet in front of the render rather
    than after it. wan2-7 defaults `duration` to 5 and `resolution` to 720p.
    Both are wrong for a 6-second 1080p shot, neither is flagged by the
    provider, and the operator finds out when the clips come back short and the
    delivery gate refuses them -- after the credits are gone.
    """
    if not profile:
        return []
    fields = profile.get("fields", {})
    want = {"duration": seconds, "resolution": tier,
            "enablePromptExpansion": False, "videoCount": 1}
    out = []
    for key, value in want.items():
        spec = fields.get(key)
        if spec is None:
            continue
        default = spec.get("default")
        out.append({"field": key, "value": value, "default": default,
                    "differs": default is not None and default != value})
    return out


class NotReady(Exception):
    pass


def build(db, data_dir: Path, order_id: str, *, model: str = "wan2-7",
          tier: str = "1080p") -> Brief:
    """Plan an order without rendering it.

    Deliberately runs the SAME build_plan the automatic path uses. If the
    operator's shot list and the queue's shot list could differ, the manual
    route would be a second product with its own bugs.
    """
    o = orders.get(db, order_id)
    if o is None:
        raise NotReady("no such order")
    if o["status"] not in ("paid", "rendering", "delivered"):
        raise NotReady(f"order is {o['status']}, not paid")

    with db.tx() as c:
        ups = [dict(r) for r in c.execute(
            "SELECT * FROM uploads WHERE order_id = ? ORDER BY position",
            (order_id,)).fetchall()]
    if not ups:
        raise NotReady("no photographs on this order")

    brief_answers = json.loads(o["brief"] or "{}")
    prep = render.prepare(o["vertical"], ups)
    originals = render.stage_originals(data_dir, order_id, prep.photos)

    listing = (brief_answers.get("Property address (as it appears on the listing)")
               or brief_answers.get("VIN or stock number")
               or brief_answers.get("Product name") or order_id)
    style = _style(o["vertical"], brief_answers)

    plan = build_plan(originals, listing=listing, style=style)
    q = quote(seconds=plan.total_seconds, shots=len(plan.shots),
              model=model, tier=tier)

    try:
        profile = providers.load(model, "image2video")
    except FileNotFoundError:
        # A model we have not recorded a schema for still gets a sheet. It just
        # cannot tell the operator which fields the provider will default wrong.
        profile = {}
    cps = rate(model, tier)

    shots = [{
        "n": s.index + 1,
        "from": s.from_room, "to": s.to_room,
        "move": s.move_label,
        "seconds": s.seconds,
        "credits": cps * s.seconds,
        "usd": cps * s.seconds * USD_PER_CREDIT,
        "settings": _settings(profile, s.seconds, tier),
        "start_frame": Path(s.start_frame).name,
        "end_frame": Path(s.end_frame).name,
        "prompt": s.prompt,
        "negative_prompt": s.negative_prompt,
    } for s in plan.shots]

    dur = (profile.get("fields", {}) or {}).get("duration", {})
    return Brief(
        order_id=order_id, listing=listing, style=style, shots=shots,
        warnings=tuple(plan.warnings) + prep.warnings, blocks=prep.blocks,
        total_seconds=plan.total_seconds,
        credits=q.expected_credits, usd=q.expected_usd,
        originals_dir=originals, model=model, tier=tier,
        duration_min=int(dur.get("minimum", 0)),
        duration_max=int(dur.get("maximum", 0)))


def _style(vertical: str, answers: dict) -> str:
    raw = str(answers.get("Daylight, golden hour or twilight", "")).lower()
    for key, style in (("twilight", "twilight"), ("golden", "goldenhour"),
                       ("daylight", "daylight")):
        if key in raw:
            return style
    return {"rooms": "goldenhour", "vehicles": "lot",
            "products": "studio"}[vertical]


def as_text(brief: Brief) -> str:
    """The render sheet, plain enough to work from on a second screen."""
    out = [
        f"ORDER {brief.order_id}",
        f"{brief.listing}   style: {brief.style}",
        f"{len(brief.shots)} shots / {brief.total_seconds}s",
        f"~{brief.credits} credits  (~${brief.usd:.2f})",
        f"model {brief.model} @ {brief.tier}",
        "",
        "SET THE LENGTH ON EVERY SHOT. " + ", ".join(
            f"#{s['n']}={s['seconds']}s" for s in brief.shots)
        + f"  ->  {brief.total_seconds}s in total.",
        f"The provider's {brief.duration_field} field defaults to 5 and will not"
        " tell you it is wrong.",
        "A delivery that comes back under 75% of the runtime above is refused,",
        "so a shot rendered at the default is credits spent for nothing.",
        "",
        f"Originals staged at: {brief.originals_dir}",
        "Upload those to OpenArt first -- the frame URLs must be the",
        "customer's own files, not anything re-rendered.",
        "",
    ]
    if brief.blocks:
        out += ["DO NOT RENDER -- the shot set cannot be filmed:"]
        out += [f"  ! {b}" for b in brief.blocks] + [""]
    if brief.warnings:
        out += ["Warnings:"] + [f"  - {w}" for w in brief.warnings] + [""]
    for s in brief.shots:
        out += [
            f"--- shot {s['n']}  {s['from']} -> {s['to']}  ({s['move']})",
            f"  >> {brief.duration_field} = {s['seconds']}"
            + (f"   (accepts {brief.duration_min}-{brief.duration_max}"
               if brief.duration_max else "")
            + f", {s['credits']} credits, ${s['usd']:.2f})",
        ]
        for f in s["settings"]:
            if f["field"] == brief.duration_field:
                continue
            out.append(f"  >> {f['field']} = {f['value']}"
                       + (f"   (the form defaults to {f['default']})"
                          if f["differs"] else ""))
        out += [
            f"startFrame : {s['start_frame']}",
            f"endFrame   : {s['end_frame']}",
            f"prompt     : {s['prompt']}",
            f"negative   : {s['negative_prompt']}",
            "",
        ]
    out += [
        "When every clip is back, upload them on the same page.",
        "Name them so the shot number is recoverable -- shot_01.mp4 and so on.",
    ]
    return "\n".join(out)
