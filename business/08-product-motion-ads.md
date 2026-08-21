# Product Motion Ads — the second productized offer

> **This is deliberately NOT "AI UGC ads."** See §1. The obvious version of that
> business is illegal, and the penalties are per-violation.

## 1. What we will not sell, and why

The standard AI-UGC offer is a synthetic person recommending a product. That is
prohibited, not merely risky:

- **FTC Rule on Consumer Reviews and Testimonials**, effective **2024-10-21** —
  bans fake or AI-generated reviews and testimonials that misrepresent the
  reviewer's identity or experience. **Civil penalties up to $53,088 per
  violation** (2026). **AI-generated testimonials are prohibited regardless of
  disclosure** — a label does not cure it. `[MARKET]`
- **FTC Endorsement Guides, 2025 update** — synthetic personas that function as
  influencers must be clearly identified as non-human, and the brand is liable
  for AI endorsements exactly as for human ones. `[MARKET]`
- **New York synthetic performer law**, effective **2026-06-09** — conspicuous
  disclosure required whenever an ad includes an AI-generated performer.
  $1,000 first violation, $5,000 each thereafter. `[MARKET]`

"Per violation" on an ad campaign is per ad, not per client. One campaign can
generate a lot of violations.

**So the answer is not to disclose harder. It is to sell a product that has no
person in it.**

## 2. The offer

**Real product photos in. Cinematic vertical product video out. No person, no
testimonial, no claim — so nothing to disclose and nothing to defend.**

Same anchored mechanism as FlyThrough: the client's photo A is the first frame,
photo B is the last, and the model generates only the camera move between them.
The product in the ad is provably the product being sold, because both ends of
every shot are the client's own photograph.

| Tier | Price | Runtime | Deliverables |
|---|---|---|---|
| **Single Product** | **$179** | 15s | 9:16 master, thumbnail |
| **Product Pro** ← default | **$279** | 25s | + 1:1 and 16:9 cuts, 3 hook variants |
| **Catalogue** | **$1,490/mo** | 10 products | Product Pro on all ten, 48h SLA |

Catalogue works out to **$149/product — 47% off Product Pro.**

**Add-ons:** extra 10s **$69** · alternate colourway pass **$59** ·
platform re-cuts (TikTok/Reels/Shorts safe areas) **$39** · rush **+50%**

## 3. Why this scores 6/6 on resellability

The test that decided this over the service menu:

| Requirement | Product Motion Ads |
|---|---|
| Fixed price | $179 / $279 / $1,490 |
| Fixed deliverable | 15s or 25s vertical, named formats |
| Fixed turnaround | 48 hours |
| A margin they can state | Reseller sells $399, pays $279 — **$120, 30%** |
| A one-sentence pitch | *"Send your product photos, get a scroll-stopping vertical ad back in two days."* |
| A buyer they already know | Every product photographer and every DTC brand they already shoot for |

Product photographers are the same channel as real-estate photographers, and the
same argument works: no new equipment, no shoot, resold under their own name.

## 4. Intake rules

Same shape as the FlyThrough shot guide, generated from `products.py`.

**Required:** hero (three-quarter), a detail/texture frame, and a scale frame.
**Ideal:** 6–10 frames. **Minimum:** 4.

**The rule that is specific to this vertical:** if a supplied photo contains a
**real person** — an on-model or in-hand shot — we use it as a reference, never
as an anchor. Generating motion between two frames containing an identifiable
human animates their likeness, which a stills model release does not
automatically cover, and it fights our own negative-prompt bank, which suppresses
people in every generated frame. `products.PERSON_RISK` flags the facets where
this usually applies.

Anchor on the product-only frames. The tour still works.

## 5. Compliance basis — different from every other vertical

| Vertical | Governing rules |
|---|---|
| Real estate | NAR Code of Ethics Art. 12; CA AB 723 / B&P §10140.8 |
| Vehicles | FTC truth-in-advertising; state dealer advertising rules |
| **Products** | **FTC truth-in-advertising; FTC Reviews & Testimonials Rule** |

`compliance.py` encodes real-estate law. **Do not reuse it here.** The product
obligation is narrower but real: the ad must not misrepresent the product's
appearance, colour, size, material or function. Anchoring helps enormously —
both ends of every shot are the client's own photograph — but the generated
travel must not invent a feature the product lacks.

**Quality gate addition for this vertical:** reject any clip where the generated
motion changes the product's proportions, adds hardware, alters a colour, or
implies a function not present in the anchors.

> Not legal advice. Have an advertising attorney review the offer before the
> first paid campaign, particularly if a client operates in New York or the EU.

## 6. What this shares with FlyThrough

Everything except the taxonomy and the compliance basis. `products.py` is 160
lines of data against the same contract as `rooms.py` and `vehicles.py`; the
planner, viewpoint checker, cost model, render adapters, assembler, inventory
gate and contact-sheet lever are all reused untouched.

That is the whole argument for productizing rather than adding services: the
second product cost a taxonomy file, not a business.
