# 90-Day Roadmap

Sequenced by revenue per hour. Every phase has an exit test — a number, not a
feeling — and the next phase does not begin until it passes.

## Phase 1 — Days 1–30: Prove someone pays

**Goal: first paid dollar. Not a product, not a brand — a dollar.**

- [ ] Render 3 portfolio samples end-to-end through the real pipeline
- [ ] Publish the landing page with all 3 embedded and a working enquiry form
- [ ] Build a 100-agent prospect list (active listing, has photos, no video)
- [ ] Run the free-sample offer at 20 touches/day
- [ ] Deliver every sample within 24h; ask for a referral on each
- [ ] Convert to paid; pitch the retainer on every close
- [ ] Get the disclosure text reviewed by a real estate attorney

**Exit test: 3 paying clients and 1 retainer.**
Fail → the problem is the offer or the beachhead, not the product. Re-read
`00-strategy.md` §7 before building anything else.

## Phase 2 — Days 31–60: Make it repeatable

**Goal: replace every assumption in the model with a measurement.**

- [ ] Run 10+ paid jobs, timing each step
- [ ] Record actual credits per job → confirm or kill the $0.0030/credit estimate
- [ ] Record actual re-roll rate → replace the 25% assumption
- [ ] Record reply and close rates → replace the 8% / 20% assumptions
- [ ] Re-run `model/unit_economics.py` with real inputs; re-price if needed
- [ ] Approach 10 photographers with the partner offer
- [ ] Build automated drift detection (the single biggest time win)

**Exit test: $2,500/mo revenue, ≤25 min operator time per job, 1 photographer
partner signed.**

## Phase 3 — Days 61–90: Make it scale without you

**Goal: revenue that does not consume proportional hours.**

- [ ] 3 photographer partners active
- [ ] 5+ retainers
- [ ] Intake form runs `flythrough plan` on upload and surfaces warnings pre-payment
- [ ] Originals page auto-publishes on delivery
- [ ] Write the operator SOP so a contractor can run step 7
- [ ] Publish the first compliance-led content piece

**Exit test: $5,000/mo with <20 operator hours, and one full job run
start-to-finish by someone who is not the founder.**

## Beyond 90 days — only after Phase 3 passes

Ranked by expected value, and deliberately **not started early**:

1. **Product Motion Ads** — the second productized offer, specified in
   `business/08-product-motion-ads.md`. Taxonomy built and tested
   (`pipeline/flythrough/products.py`). Deliberately NOT "AI UGC ads": the FTC
   Reviews & Testimonials Rule bans AI-generated testimonials outright at up to
   $53,088 per violation, regardless of disclosure. Selling motion around a real
   product, with no person in frame, has none of that exposure and reuses the
   entire pipeline.

2. **Self-serve product.** Upload, pay, receive. Justified only once the manual
   workflow is provably stable — building it earlier means automating a process
   still being discovered. This is the "productize later" half of the strategy.
3. **White-label for brokerages.** Their branding, our pipeline, per-seat pricing.
   The natural evolution of the photographer partnership.
4. **Auto dealers — the strongest adjacent vertical, ahead of everything else.**
   Taxonomy already built (`pipeline/flythrough/vehicles.py`, tested). Dealers
   beat listing agents on every axis that matters:
   - They already photograph every unit systematically, 20–40 frames to a house
     standard, so the intake problem is solved before we arrive.
   - The walkaround video is an established format buyers expect — we undercut a
     cost rather than create a category.
   - One dealer group with 300 units in stock is worth ~30 individual agents,
     and it is **one** relationship instead of thirty.
   - Stock turns over continuously, so it is recurring by nature rather than
     per-transaction.

   **The compliance basis is different and must not be copied.** Vehicle
   advertising falls under FTC truth-in-advertising rules and state dealer
   advertising regulations, which vary considerably. `compliance.py` encodes
   NAR Article 12 and California AB 723 — real-estate law. Do not reuse it here
   without a lawyer in the operating state.

5. **Then**: land and acreage (real drones are hardest there, so our relative
   advantage is largest), venues and short-term rentals, then products and
   e-commerce — biggest market, but lowest ticket and most competition, so last.
6. **True 3D**, via Gaussian splatting from a walkaround video. A different and
   much stronger product — arbitrary camera paths, an interactive viewer, no
   drift at all. Revisit only when GPU cost and customer capture effort both
   justify it. **Do not start here**; the current mechanism reaches revenue
   months sooner.

## The standing rule

> If a week's plan contains no revenue work, the plan is wrong.

Building product before Phase 1's exit test passes is the most likely way this
fails. The pipeline is already good enough to sell. Go sell it.
