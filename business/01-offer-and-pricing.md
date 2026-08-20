# Offer and Pricing

All margin figures are computed by `model/unit_economics.py`. Re-run it after
changing any input; do not hand-edit numbers into this file.

```
python3 model/unit_economics.py
```

## 1. The price sheet

| Tier | Price | Runtime | Deliverables | Revisions |
|---|---|---|---|---|
| **Single Listing** | **$149** | 30s | 16:9 master, thumbnail, disclosure pack | 1 |
| **Listing Pro** ← default | **$249** | 42s | + 9:16 vertical cut, MLS + social captions | 2 |
| **Signature** | **$399** | 60s | + twilight pass, priority 12h turnaround | 3 |
| **Retainer** | **$899/mo** | 5 listings | Listing Pro on all five, 24h SLA | 2 each |

Retainer works out to **$179.80/listing — 28% off Listing Pro.**

### Why these numbers

- **$249 anchors below the cheapest human walkthrough video ($300–$500
  `[MARKET]`)** while sitting above the drone-stills add-on ($75–$200), so we are
  never the cheapest thing on the page — being cheapest invites the "is it any
  good?" objection we cannot answer without a portfolio.
- **$149 exists to be a trial, not a profit centre.** It removes the "I'll try one
  and see" objection at a price an agent expenses without thinking. It
  deliberately omits the vertical cut, which is the single most-wanted upsell.
- **$399 exists to make $249 look moderate.** Classic three-tier anchoring. It
  also genuinely serves luxury listings, where the alternative is a $1,500–$3,000
  film crew `[MARKET]`.
- **The retainer is the whole business.** One retainer client is worth 3.6
  Listing Pro sales a month at zero repeat acquisition cost. Every sales
  conversation should end pointing at it.

## 2. Margins (computed, not asserted)

At a `[VERIFIED]` render rate of **35 credits/second** for Wan 2.7 at 1080p, an
`[ASSUMPTION]` credit price of **$0.0030**, and a 25% re-roll allowance:

| Tier | Price | Render | Fees | Cash gross profit | Margin | Effective $/hr |
|---|---|---|---|---|---|---|
| Single Listing | $149.00 | $3.94 | $4.62 | **$140.39** | 94.2% | $336.94 |
| Listing Pro | $249.00 | $5.51 | $7.52 | **$235.91** | 94.7% | $566.20 |
| Signature | $399.00 | $7.88 | $11.87 | **$379.20** | 95.0% | $910.09 |
| Retainer ×5 | $899.00 | $27.56 | $26.37 | **$844.82** | 94.0% | $405.51 |

### What this table actually tells you

**Render cost is irrelevant to the business.** Credits would have to cost **43×
more** to erase Listing Pro's gross profit. The correct conclusion is *not*
"great margins" — it is:

> **Operator minutes are the only scarce input. Automate review, not render.**

A Listing Pro job can absorb **189 minutes** before it stops clearing $75/hr —
7.5× the 25-minute budget. So the right instinct at every fork is to **spend
credits to save minutes**: render two variants of a risky shot in parallel rather
than inspect one carefully and re-roll it serially. Two extra shots cost $0.70 and
save ten minutes of an operator's attention. Take that trade every time.

This also means **cheaper models are a trap.** Dropping to 720p saves $1.57 a job
and costs delivery quality on the one asset the client judges us by.

### Sensitivity — the credit price is unverified

`openart.ai` was unreachable from the build environment, so $0.0030/credit is
derived from a reported add-on pack and is **not confirmed**. If it is wrong:

| Case | $/credit | Render | Cash GP | Margin |
|---|---|---|---|---|
| as modelled | 0.0030 | $5.51 | $235.91 | 94.7% |
| 2× | 0.0060 | $11.03 | $230.40 | 92.5% |
| 3× | 0.0090 | $16.54 | $224.89 | 90.3% |
| 5× | 0.0150 | $27.57 | $213.86 | 85.9% |

**The business survives a 5× pricing error.** This is a genuinely robust model,
and it is robust for a structural reason: the cost of the good is a rounding error
against the price of the good. That is the definition of a service worth selling.

## 3. What is included, precisely

Scope written to be enforceable, because vague scope is how service businesses
lose their margin one favour at a time.

**Every tier includes:**
- One master video at 1920×1080, H.264, 24fps
- A still thumbnail pulled from the master
- The full disclosure pack: burned-in opening card, QR code, MLS remarks text,
  social caption text, and a hosted originals page
- Delivery inside 24 hours of receiving usable photos (12h on Signature)

**Not included at any tier, ever:**
- Voiceover, agent branding, or an end card (add-on, §4)
- Music licensing — we supply a licensed bed or the agent supplies theirs
- Editing the *source photos* — we do not retouch, stage, or colour-correct
  supplied images. See §5, this is a compliance boundary and not a service limit.
- More than the stated revision count
- Re-shoots. If the photos can't carry a tour, we say so before rendering.

**Revisions** mean re-rendering specific shots or changing shot order. They do
not mean a different set of photos — that is a new job.

## 4. Add-ons (the real margin, priced separately)

| Add-on | Price | Marginal cost | Why it prices here |
|---|---|---|---|
| 9:16 vertical cut | **$49** | ~$0 (CPU only) | Re-frame of footage already rendered. Pure margin. Free on Pro and above as the reason to upgrade. |
| Extra 15s of runtime | **$59** | ~$1.84 | 525 credits at 1080p. |
| Twilight / golden-hour pass | **$79** | one re-render | Style change only; the plan is reused. |
| Branded intro + end card | **$39** | ~$0 | Built once per agent, reused on every future job — margin rises with the relationship. |
| Rush (same-day) | **+50%** | ~$0 | Prices the operator's calendar, not compute. |
| Extra revision | **$45** | ~$0.70 | Deters scope creep more than it earns. |

**The vertical cut is the single best line on this sheet.** One render, two
deliverables, and the vertical is the one agents actually post. Give it away on
Pro to drive the upgrade from $149; sell it at $49 to Single Listing buyers.

## 5. Two things we refuse to sell

Stated in the price sheet on purpose. Refusals build more trust than features.

1. **We do not retouch, stage, or alter the source photographs.** Not because we
   can't — because the moment we alter the stills, the "originals" page stops
   containing originals and the entire AB 723 disclosure position collapses. The
   photos an agent gives us are the photos on the disclosure page. This is
   load-bearing.
2. **We do not sell video that hides what it is.** Every master ships with the
   disclosure card burned in. An agent who asks us to remove it is asking us to
   help them violate NAR Article 12, and the answer is no — offered with the
   reason, which is usually enough to convert the objection into the sale.

## 6. Payment terms

- Card up front, in full, before render. No invoicing, no net-30, no exceptions
  at these price points — collections would cost more than the job earns.
- Retainer bills monthly in advance, cancel any time with the current month
  honoured.
- Refund policy: **full refund if we fail to deliver on time or the tour is
  unusable.** No refund for taste disagreements after revisions are exhausted.
  Say this before taking money, not after.
