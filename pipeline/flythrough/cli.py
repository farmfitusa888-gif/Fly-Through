"""Command line interface.

Three verbs, matching the three things that actually happen in a job:

    plan      photos -> shot plan + cost quote      (free)
    manifest  shot plan -> provider payloads        (free, this is the spend gate)
    assemble  rendered clips -> delivered files     (free, local ffmpeg)

Rendering itself is deliberately NOT a verb here. Submitting paid jobs is done
explicitly against a configured provider, so no command in this tool can spend
money as a side effect of being run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .assemble import deliver
from .cost import USD_PER_CREDIT_VERIFIED, quote
from .planner import build_plan
from .render import OpenArtAdapter, build_jobs, write_manifest


def _slug(text: str) -> str:
    out = [c.lower() if c.isalnum() else "-" for c in text]
    return "-".join("".join(out).split("-")).strip("-") or "listing"


def cmd_plan(a: argparse.Namespace) -> int:
    plan = build_plan(
        a.photos, listing=a.listing, style=a.style,
        resolution=a.tier, max_seconds=a.max_seconds,
    )
    out = Path(a.out or f"plans/{_slug(a.listing)}.plan.json")
    plan.write(out)

    q = quote(seconds=plan.total_seconds, shots=len(plan.shots), model=a.model, tier=a.tier)
    print(f"\n{a.listing}")
    print(f"  {len(plan.photos)} photos -> {len(plan.shots)} shots, {plan.total_seconds}s runtime")
    print(f"  style {a.style} | {a.model} @ {a.tier}")
    print()
    for s in plan.shots:
        print(f"   {s.index:2}  {s.from_room:>12} -> {s.to_room:<12} {s.move_label:<22} {s.seconds}s")
    print()
    print(q.describe())
    if plan.warnings:
        print("\n  WARNINGS")
        for w in plan.warnings:
            print(f"   ! {w}")
    if not USD_PER_CREDIT_VERIFIED:
        print("\n  Note: USD figures are estimated from an unverified credit price.")
    print(f"\n  plan written: {out}")
    return 0


def cmd_manifest(a: argparse.Namespace) -> int:
    plan_doc = json.loads(Path(a.plan).read_text())
    plan = build_plan(
        a.photos, listing=plan_doc["listing"], style=plan_doc["style"],
        resolution=plan_doc["resolution"], max_seconds=a.max_seconds,
    )
    adapter = OpenArtAdapter(model=a.model, tier=a.tier)
    jobs = build_jobs(plan, adapter)
    out = Path(a.out or f"manifests/{_slug(plan.listing)}.jobs.json")
    write_manifest(plan, jobs, out, model=a.model, tier=a.tier)
    doc = json.loads(out.read_text())
    print(f"{len(jobs)} jobs -> {out}")
    print(f"  expected {doc['cost']['expected_credits']} credits "
          f"(~${doc['cost']['usd_estimate_expected']:.2f} est.)")
    print("  Nothing has been submitted. Review this file before spending.")
    return 0


def cmd_assemble(a: argparse.Namespace) -> int:
    clips = sorted(Path(a.clips).glob("*.mp4"))
    if not clips:
        print(f"no .mp4 clips found in {a.clips}", file=sys.stderr)
        return 1
    d = deliver(clips, a.out, slug=_slug(a.listing), crossfade=a.crossfade,
                music=a.music, make_vertical=not a.no_vertical)
    print(f"  master   {d.master}  ({d.duration:.1f}s)")
    if d.vertical:
        print(f"  vertical {d.vertical}")
    if d.thumbnail:
        print(f"  thumb    {d.thumbnail}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser("flythrough", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("plan", help="photos -> shot plan + cost quote")
    pl.add_argument("photos")
    pl.add_argument("--listing", required=True)
    pl.add_argument("--style", default="daylight")
    pl.add_argument("--model", default="wan2-7")
    pl.add_argument("--tier", default="1080p")
    pl.add_argument("--max-seconds", type=int, dest="max_seconds")
    pl.add_argument("--out")
    pl.set_defaults(fn=cmd_plan)

    mf = sub.add_parser("manifest", help="shot plan -> provider payloads (spend gate)")
    mf.add_argument("plan")
    mf.add_argument("--photos", required=True)
    mf.add_argument("--model", default="wan2-7")
    mf.add_argument("--tier", default="1080p")
    mf.add_argument("--max-seconds", type=int, dest="max_seconds")
    mf.add_argument("--out")
    mf.set_defaults(fn=cmd_manifest)

    asm = sub.add_parser("assemble", help="rendered clips -> delivered files")
    asm.add_argument("clips")
    asm.add_argument("--listing", required=True)
    asm.add_argument("--out", default="delivery")
    asm.add_argument("--crossfade", type=float, default=0.4)
    asm.add_argument("--music")
    asm.add_argument("--no-vertical", action="store_true")
    asm.set_defaults(fn=cmd_assemble)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
