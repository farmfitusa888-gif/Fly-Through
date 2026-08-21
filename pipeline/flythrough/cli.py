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
from .compliance import CAPTION, make_card, make_qr
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
    """Assemble downloaded clips into the delivery set.

    This is the primary path, not a fallback. Provider CDNs are frequently
    unreachable behind corporate egress policies, so the reliable workflow is to
    download the rendered clips from the provider's own UI, drop them in a
    folder, and run this. Nothing here touches the network.
    """
    clips = sorted(Path(a.clips).glob("*.mp4"))
    if not clips:
        print(f"no .mp4 clips found in {a.clips}", file=sys.stderr)
        print("  Download the rendered shots from your provider and put them here,",
              file=sys.stderr)
        print("  named so they sort into tour order (part_1.mp4, part_2.mp4, ...).",
              file=sys.stderr)
        return 1

    slug = _slug(a.listing)
    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)

    # The disclosure card leads the master, because a caption does not survive
    # a re-post but a burned-in frame does.
    sequence: list[Path] = []
    if a.disclosure_url:
        sequence.append(make_card(a.disclosure_url, outdir / "_card.mp4",
                                  seconds=2.5, fps=a.fps))
        make_qr(a.disclosure_url, outdir / f"{slug}_originals_qr.png")
    sequence += clips

    d = deliver(sequence, outdir, slug=slug, crossfade=a.crossfade, fps=a.fps,
                music=a.music, make_vertical=not a.no_vertical, trim=not a.no_trim)
    (outdir / "_card.mp4").unlink(missing_ok=True)

    print(f"  master    {d.master.name}  ({d.duration:.1f}s)  [archive, CRF 18]")
    if d.master_web:
        print(f"  master    {d.master_web.name}  [SEND THIS -- web/MLS]")
    if d.vertical_web:
        print(f"  vertical  {d.vertical_web.name}  [SEND THIS -- Reels/TikTok]")
    if d.thumbnail:
        print(f"  thumb     {d.thumbnail.name}")
    if a.disclosure_url:
        print(f"  qr        {slug}_originals_qr.png")
        print()
        print("  MLS remark to paste:")
        print(f"    {CAPTION.format(url=a.disclosure_url)}")
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
    asm.add_argument("--crossfade", type=float, default=0.2,
                     help="0.2s suits anchored shots; 0 gives true hard cuts")
    asm.add_argument("--fps", type=int, default=30,
                     help="match the source renders to avoid judder")
    asm.add_argument("--disclosure-url", dest="disclosure_url",
                     help="URL of the unaltered-originals page; adds the burned-in "
                          "card, the QR and the MLS caption")
    asm.add_argument("--music")
    asm.add_argument("--no-vertical", action="store_true")
    asm.add_argument("--no-trim", action="store_true",
                     help="skip stall trimming. Only correct if the clips were "
                          "already trimmed -- untrimmed anchored clips compile to "
                          "roughly 40%% frozen frames and read as a slideshow.")
    asm.set_defaults(fn=cmd_assemble)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
