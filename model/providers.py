"""Provider economics — should we move off OpenArt?

Run: python3 model/providers.py

The order of the two questions below is the whole point, and it is the opposite
of the order most people ask them in.

  1. CAN the provider hold a start frame AND an end frame?
  2. What does it cost?

Question 1 is a gate, not a preference. This product's entire defensibility is
that every shot begins and ends on a real photograph of the property. A provider
that cannot anchor both frames produces drifting footage that misrepresents the
house -- which is a compliance problem, not just a quality problem. Such a
provider is worth zero regardless of price, so price is never even evaluated.

Prices below are labelled with provenance. Nothing here is asserted.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- our current position, VERIFIED 2026-08-20 ------------------------------
OPENART_CREDITS_PER_SEC = 35        # Wan 2.7 @1080p, verified at 5s and 10s
USD_PER_CREDIT = 0.0030             # ASSUMPTION, unverified (see 07-open-questions)
OPENART_USD_PER_SEC = OPENART_CREDITS_PER_SEC * USD_PER_CREDIT

STANDARD_JOB_SECONDS = 42           # Listing Pro
STANDARD_JOB_PRICE = 249.00


@dataclass(frozen=True)
class Provider:
    name: str
    dual_anchor: bool | None        # None = unverified, treat as blocking
    usd_per_sec: float | None
    basis: str
    note: str = ""

    @property
    def usable(self) -> bool:
        return self.dual_anchor is True

    def job_cost(self, seconds: int = STANDARD_JOB_SECONDS) -> float | None:
        return None if self.usd_per_sec is None else self.usd_per_sec * seconds


PROVIDERS = (
    Provider(
        "OpenArt / Wan 2.7 @1080p", True, OPENART_USD_PER_SEC,
        "VERIFIED rate card; USD per credit ASSUMED",
        "Current provider. startFrame + endFrame confirmed by generation.",
    ),
    Provider(
        "OpenArt / Wan 2.7 @720p", True, 25 * USD_PER_CREDIT,
        "VERIFIED rate card; USD per credit ASSUMED",
        "Cheaper tier. Rejected: saves ~$1.57/job on a $249 sale and costs "
        "delivery quality on the only asset the client judges.",
    ),
    Provider(
        "Higgsfield / Veo3 Fast @sub rate", True, 2.75 * 0.039,
        "MARKET: ~22 cr per 8s clip; ~$39/mo for ~1,000 cr",
        "PASSES THE GATE. Higgsfield ships Start & End Frames as a named "
        "feature, and Kling 3.0 there has start-and-end-frame control. A real "
        "candidate. Near parity at subscription rates.",
    ),
    Provider(
        "Higgsfield / Veo3 Fast @top-up", True, 2.75 * 0.05,
        "MARKET: ~$5 per 100 top-up cr, expiring after 90 days",
        "At the rate that ACTUALLY governs at volume, ~31% dearer than OpenArt. "
        "Credits also expire in 90 days, which is a real risk for lumpy service "
        "volume -- buy for a busy month, forfeit in a slow one.",
    ),
)


# --- self-hosting on rented GPU ---------------------------------------------
# Wan is open-weights, so renting a GPU and running it yourself is a genuine
# structural alternative rather than a swap: you pay for GPU-seconds instead of
# per-video.
#
# MARKET (2026): Vast.ai RTX 4090 roughly $0.29-0.59/hr; A100 from ~$0.29/hr;
# H100 from ~$0.90/hr.
#
# UNVERIFIED and load-bearing: how many GPU-minutes one 5s 1080p clip takes.
# This has NOT been benchmarked. Every number below is a function of it, so it is
# an input, never a claim.
# VERIFIED-BY-SEARCH 2026-08: Wan 14B needs 40-48GB VRAM at 480p (FP8) and
# 65-80GB at 720p, so this is an A100/H100 80GB job, NOT a 4090. A 5s 480p clip
# takes ~4 min on an H100 PCIe. No public 1080p benchmark exists.
#
# THE DECISIVE FACT: Wan 2.2 is the newest version with public weights. Wan 2.5+
# weights have not shipped. The model we actually render with -- Wan 2.7 at
# 1080p -- CANNOT BE SELF-HOSTED AT ALL. Self-hosting is not a cheaper way to
# get the same output; it is a downgrade to an older model at lower resolution.
#
# This matches the operator's own hands-on result on a previous project: the GPU
# required and the render time made it close to pointless.
GPU_USD_PER_HOUR = 1.47             # MARKET, H100 PCIe -- the class actually needed
MINUTES_PER_CLIP = 8.0              # MARKET-derived: ~4 min at 480p, more at 720p
CLIP_SECONDS = 5

# ASSUMPTION: cost of standing up and running self-hosted inference.
SETUP_HOURS = 20
MAINTENANCE_HOURS_PER_MONTH = 2
OPERATOR_HOURLY = 75.0


def selfhost_usd_per_sec(
    gpu_hourly: float = GPU_USD_PER_HOUR,
    minutes_per_clip: float = MINUTES_PER_CLIP,
    clip_seconds: int = CLIP_SECONDS,
) -> float:
    return (gpu_hourly / 60 * minutes_per_clip) / clip_seconds


def crossover_jobs_per_month(
    gpu_hourly: float = GPU_USD_PER_HOUR,
    minutes_per_clip: float = MINUTES_PER_CLIP,
) -> tuple[float, float]:
    """Jobs/month at which self-hosting pays, ignoring then including setup.

    Returns (to cover ongoing maintenance, to repay setup within 12 months).
    """
    saving = (OPENART_USD_PER_SEC - selfhost_usd_per_sec(gpu_hourly, minutes_per_clip)) \
        * STANDARD_JOB_SECONDS
    monthly_maint = MAINTENANCE_HOURS_PER_MONTH * OPERATOR_HOURLY
    setup = SETUP_HOURS * OPERATOR_HOURLY
    if saving <= 0:
        return (float("inf"), float("inf"))
    return (monthly_maint / saving, (monthly_maint + setup / 12) / saving)


def report() -> None:
    line = "-" * 76
    print(line)
    print("PROVIDER ECONOMICS")
    print(line)
    print("Gate 1 -- can it anchor BOTH frames? A 'no' or 'unknown' ends the")
    print("evaluation. Price is only reached by providers that pass.\n")
    print(f"{'Provider':<30}{'Anchor':>9}{'$/sec':>9}{'$/job':>9}  Basis")
    for p in PROVIDERS:
        anchor = {True: "YES", False: "NO", None: "UNKNOWN"}[p.dual_anchor]
        cost = p.job_cost()
        print(f"{p.name:<30}{anchor:>9}"
              f"{('%.4f' % p.usd_per_sec) if p.usd_per_sec else '   n/a':>9}"
              f"{('$%.2f' % cost) if cost else '  n/a':>9}  {p.basis}")
    print()
    for p in PROVIDERS:
        if p.note:
            print(f"  {p.name}: {p.note}")

    sh = selfhost_usd_per_sec()
    job = sh * STANDARD_JOB_SECONDS
    maint_be, full_be = crossover_jobs_per_month()
    print()
    print(line)
    print("SELF-HOSTING WAN ON RENTED GPU (Vast.ai class)")
    print(line)
    print(f"  GPU              ${GPU_USD_PER_HOUR:.2f}/hr        [MARKET]")
    print(f"  Minutes per clip {MINUTES_PER_CLIP:.1f}            [UNVERIFIED - benchmark first]")
    print(f"  -> ${sh:.4f}/sec vs OpenArt ${OPENART_USD_PER_SEC:.4f}/sec")
    print(f"  -> ${job:.2f}/job vs ${OPENART_USD_PER_SEC * STANDARD_JOB_SECONDS:.2f}/job")
    print(f"     saving ${OPENART_USD_PER_SEC * STANDARD_JOB_SECONDS - job:.2f} per job")
    print()
    print(f"  Break-even vs ongoing maintenance only : {maint_be:.0f} jobs/month")
    print(f"  Break-even incl. setup repaid in 12 mo : {full_be:.0f} jobs/month")
    print()
    print("  Sensitivity on the unverified input:")
    print(f"  {'min/clip':>9}{'$/job':>9}{'saving':>9}{'break-even':>13}")
    for m in (2.0, 4.0, 8.0, 16.0):
        j = selfhost_usd_per_sec(minutes_per_clip=m) * STANDARD_JOB_SECONDS
        _, be = crossover_jobs_per_month(minutes_per_clip=m)
        print(f"  {m:>9.1f}{j:>9.2f}"
              f"{OPENART_USD_PER_SEC * STANDARD_JOB_SECONDS - j:>9.2f}"
              f"{be:>13.0f}")
    print()
    print(line)
    print("VERDICT")
    print(line)
    print(f"  Render is {OPENART_USD_PER_SEC * STANDARD_JOB_SECONDS / STANDARD_JOB_PRICE:.1%} "
          f"of a ${STANDARD_JOB_PRICE:.0f} job. Cutting it to zero moves gross margin")
    print("  by about two points. It is not the constraint -- operator minutes are.")
    print()
    print("  SELF-HOSTING: CLOSED, and not on cost grounds.")
    print("  Wan 2.7 @1080p has no public weights. Self-hosting means dropping to")
    print("  Wan 2.2 @720p on an 80GB GPU at ~8 min/clip -- paying engineering")
    print(f"  time and wall-clock to get a WORSE product, to save ~${OPENART_USD_PER_SEC * STANDARD_JOB_SECONDS - job:.2f} on a $249")
    print("  sale. Reopen only if a self-serve product removes the operator from")
    print("  the loop AND Wan 2.7-class weights ship publicly.")
    print()
    print("  HIGGSFIELD: passes the capability gate -- Start & End Frames is a")
    print("  shipped feature. But at TOP-UP rates, which are what govern once")
    print("  volume exceeds any subscription tier, it is ~31% dearer than OpenArt,")
    print("  and its credits expire after 90 days.")
    print("  UNKNOWN: the credit cost of Kling 3.0 with start+end frames, which is")
    print("  the config we would actually buy. Veo 3 pricing is not a proxy for it.")
    print("  ACTION: render ONE identical shot there and measure. Do not migrate on")
    print("  a brochure -- that is how the contact-sheet question got settled.")
    print()
    print("  At 30 jobs/month a 42s tour needs ~44,100 credits. No subscription")
    print("  tier on either platform covers that, so the marginal top-up rate is")
    print("  the only rate that matters. Compare there, not on sticker price.")
    print()
    print("  Architecture is already ready: render.QueueAdapter takes endpoint,")
    print("  auth and field mapping from config, so switching provider is a")
    print("  config change, not a rewrite. Nothing is locked in by waiting.")
    print(line)


if __name__ == "__main__":
    report()
