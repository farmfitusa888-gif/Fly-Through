# Open Questions

Things that are genuinely unknown. Recorded rather than guessed, with what it
would take to close each one.

## Blocking — must be answered before scaling spend

**1. Does the anchored approach actually look good on real agent photos?**
The pipeline is verified end-to-end on synthetic inputs. It has **not** been
proven on real listing photography with inconsistent white balance, mixed times
of day, and varying lens distortion. The specific worry is a visible colour or
exposure pop at the seam between two anchor photos.
*To close:* render 3 tours from real listing photo sets and review at full screen.
*If it fails:* normalise white balance across anchor pairs before submission — an
upstream fix, not a grade on the output.

**2. What does an OpenArt credit actually cost?** — NARROWED, still not confirmed.
`openart.ai` is blocked from the build environment, so this cannot be read
directly. Two market figures bracket it: a subscription at ~12,000 credits for
~$14.50/mo ($0.00121/cr) and add-on packs at $15/5,000 ($0.0030/cr).

`model/credit_price.py` computes the blended rate at real volumes. At 30 jobs a
month you need ~44,100 credits — far beyond any subscription tier — so the
blended rate lands near **$0.0027/cr** and the marginal rate is **$0.0030/cr**.

`cost.py` uses the marginal rate deliberately: it is the higher of the two, so
every margin figure in this buildout is conservative rather than optimistic.
*To close:* divide one real top-up receipt — dollars paid ÷ credits received.

**3. Will agents pay $249, and does the free sample convert at 20%?**
Entirely unvalidated. It is the central business question.
*To close:* 20 free samples, count conversions.

## Important — answer inside 60 days

**4. What is the real re-roll rate on live jobs?** 25% is a planning assumption.
It drives operator time, which is the binding constraint.

**5. Is 25 minutes per job real?** Everything in the labour model rests on it.

**6. Does the compliance angle actually sell, or merely reassure?** It may close
deals, or it may be something clients nod at and ignore. Track whether it appears
in the reason given at close.

**7. Will a photographer partner accept $199/$349 economics?** The margin is
attractive, but it makes them a reseller of someone else's work, which some will
refuse on principle.

## Worth knowing — no deadline

**8. Which style converts better — daylight or golden hour?** Cheap to A/B once
there is volume.

**9. Does the vertical cut drive more agent posting than the 16:9 master?**
Determines whether $49 is the right price or far too low.

**10. Is there a second beachhead that is easier than residential?** Land and
acreage is the standing hypothesis: real drones are logistically hardest there,
so our relative advantage should be largest.

## Deliberately not pursued

- **True 3D / Gaussian splatting.** Better product, far longer path to revenue.
  Revisit at Phase 3+.
- **Interior virtual staging.** Lucrative and adjacent, but it would destroy the
  "we never alter the originals" position that the entire compliance wedge rests
  on. Declining it is a strategic choice, not an oversight.
