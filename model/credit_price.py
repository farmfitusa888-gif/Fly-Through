#!/usr/bin/env python3
"""Best available derivation of the OpenArt credit price.

    python3 model/credit_price.py

openart.ai is blocked from the build environment, so this cannot be read from the
billing page. Both inputs below are MARKET figures. One top-up receipt settles it
exactly: dollars paid / credits received. Update SUB_* and PACK_* and re-run.
"""

SUB_CREDITS, SUB_USD = 12_000, 14.50      # MARKET: ~12k cr/mo, ~$14.50/mo annual
PACK_CREDITS, PACK_USD = 5_000, 15.00     # MARKET: add-on pack
JOB_CREDITS = 1470                        # VERIFIED: 42s x 35 cr/s at 1080p


def blended(jobs_per_month: int) -> dict:
    need = jobs_per_month * JOB_CREDITS
    top_needed = max(0, need - SUB_CREDITS)
    packs = -(-top_needed // PACK_CREDITS)          # packs are indivisible
    total = SUB_USD + packs * PACK_USD
    return {"jobs": jobs_per_month, "credits": need, "packs": packs,
            "usd": total, "per_credit": total / need, "per_job": total / jobs_per_month}


def report() -> None:
    print(f"  subscription rate  ${SUB_USD/SUB_CREDITS:.5f}/cr")
    print(f"  top-up rate        ${PACK_USD/PACK_CREDITS:.5f}/cr")
    print()
    print(f"{'Jobs/mo':>8}{'Credits':>10}{'Total$':>9}{'$/credit':>10}{'$/job':>8}")
    for j in (5, 10, 20, 30, 50):
        b = blended(j)
        print(f"{b['jobs']:>8}{b['credits']:>10,}{b['usd']:>9.2f}"
              f"{b['per_credit']:>10.5f}{b['per_job']:>8.2f}")
    print()
    print("  cost.py uses $0.0030/cr -- the MARGINAL rate. Every credit past the")
    print("  subscription allowance costs exactly that, and at any real volume you")
    print("  are buying top-ups. Blended is lower (~$0.0027 at 30 jobs/mo), so the")
    print("  model is deliberately conservative rather than optimistic.")


if __name__ == "__main__":
    report()
