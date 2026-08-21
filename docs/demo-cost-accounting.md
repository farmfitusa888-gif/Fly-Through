# Demo Cost Accounting — 1420 Cedar Ridge

Complete spend for the portfolio demo, reconciled against the account ledger.
Regenerate with `python3 docs/cost_report.py`.

| Phase | Item | Qty | Cr | Total |
|---|---|---:|---:|---:|
| A | Exterior still (text2image, 2K 16:9) | 1 | 40 | 40 |
| A | Foyer still (image2image, 2K 16:9) | 1 | 40 | 40 |
| A | Threshold shot (Wan 2.7, 1080p, 5s) | 1 | 175 | 175 |
| A | 4K contact sheet (batching test) | 1 | 80 | 80 |
| B | Room stills: living, kitchen, patio | 3 | 40 | 120 |
| B | Aerial still (front-framed) | 1 | 40 | 40 |
| B | Shots 2–4 (Wan 2.7, 1080p, 5s) | 3 | 175 | 525 |
| B | Shot 5, closing rise (1080p, 6s) | 1 | 210 | 210 |
| Fix | Aerial still, re-framed over the rear | 1 | 40 | 40 |
| Fix | Shot 5 re-rendered (1080p, 6s) | 1 | 210 | 210 |
| | **TOTAL** | | | **1,480** |

Ledger check: 9,690 − 8,210 = **1,480. Match.**

## Waste, itemised

| Cause | Credits |
|---|---:|
| Duplicate renders — living/kitchen/patio already held by the 4K sheet | 120 |
| Closing shot rendered against a front-framed aerial | 210 |
| Superseded front-framed aerial still | 40 |
| **Total** | **370 (25% of spend)** |

Both causes are now structurally prevented rather than left to attention:
`inventory.check()` blocks the duplicate order, `viewpoint.assess()` flags the
incompatible pairing in the plan — which is the spend gate — before any credits
are committed.

## Dollars

At **$0.0030/credit** — an ASSUMPTION, not verified; `openart.ai` was unreachable
from the build environment.

- Total **$4.44**, of which waste **$1.11** and useful spend **$3.33**
- Remaining balance 8,210 credits (~$24.63 of remaining value)

## What a real job costs

| Scenario | Credits | Cost |
|---|---:|---:|
| Clean 5-shot 26s tour, no waste, no re-rolls | 1,150 | $3.45 |
| **Production job — agent supplies the photos** | **910** | **$2.73** |

Render is therefore about **1.1% of a $249 Listing Pro sale.** Note this is the
render line only; the full cash margin of 94.7% in `business/02-unit-economics.md`
also carries payment fees and hosting.

The demo cost more than any real job will, because the property had to be
manufactured. Real jobs begin with photographs someone else already paid for.
