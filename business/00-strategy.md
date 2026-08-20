# FlyThrough — Strategy

> **Sourcing note.** Every external figure below is labelled with its provenance.
> `[VERIFIED]` was read from a provider's own tool this session. `[MARKET]` comes
> from secondary industry sources listed in `business/99-sources.md` and should be
> re-checked before it goes into a client-facing claim. `[ASSUMPTION]` is a
> planning input chosen for a stated reason, not a measurement. Nothing here is
> asserted without one of those three tags.

---

## 1. The one-sentence business

**FlyThrough turns a listing agent's existing photos into a cinematic drone-style
property video, delivered in under 24 hours, for a fraction of what a film crew
costs — with the AI disclosure the law now requires built into every delivery.**

## 2. The thesis

Three facts define the opportunity, and they point the same direction.

| Fact | Source |
|---|---|
| 85% of homebuyers watch video during their search | `[MARKET]` |
| 73% of homeowners are more likely to list with an agent who uses video | `[MARKET]` |
| **Only ~9% of agents produce listing-specific video** | `[MARKET]` |

Demand is near-universal. Supply is under one in ten. That gap is not caused by
agents failing to see the value — the 73% figure shows they see it. It is caused
by production economics: a walkthrough video runs **$300–$500**, a cinematic one
**$700–$1,200**, and a drone package **$150–$500**, each requiring a scheduled
shoot, a weather window, a licensed pilot for the aerial work, and a 3–7 day
turnaround `[MARKET]`.

At those prices video is a luxury reserved for listings that can carry it. Most
listings can't. **So most listings get photos and nothing else.**

FlyThrough attacks the cost and the calendar at once. The agent already paid a
photographer. Those photos already exist. We turn what they already own into the
video they never commissioned — no second visit, no pilot, no weather.

## 3. The mechanism, and why it is defensible

Naive AI listing video takes one photo and lets a model hallucinate a flight
around it. The output drifts: windows multiply, furniture melts, the back of the
house is invented. It is unusable and, worse, it misrepresents the property.

**FlyThrough anchors both ends of every shot.**

```
 photo A (real)  ──── AI generates only the travel ────  photo B (real)
   kitchen                                                  dining
```

Each shot is submitted with the agent's photo A as the **start frame** and photo
B as the **end frame**. The model is never asked what the house looks like — it is
told, twice, and asked only how the camera gets from one to the other. Drift is
bounded by construction: the clip cannot end anywhere except on a real photograph
of the real property.

This is a real technical constraint, not positioning:

- Only some video models accept both a start and an end frame. Wan 2.7 and
  Kling 3 Omni do `[VERIFIED]`. The pipeline **refuses to build a job** for a
  model that cannot hold both anchors (`cost.py: DUAL_ANCHOR`).
- Server-side prompt expansion is disabled, because rewriting the prompt
  reintroduces exactly the invention the negative-prompt bank suppresses.
- Camera moves are selected by transition type, not by vibe — crossing the front
  door gets a threshold push, interior-to-exterior gets an exposure-settling
  glide.

**The competitive moat is not the model.** Anyone can call the same API. The moat
is the accumulated production system: the room taxonomy, the tour ordering, the
move library, the negative-prompt bank tuned on observed failure modes, and — most
durably — the compliance layer in §5.

## 4. Beachhead: residential listing agents

**Who, specifically:** individual agents and 2–8 person teams doing 12–40
transactions a year, in markets where the median price is high enough that
marketing spend is normal but not high enough for a $1,500 film crew.

Why them first:

- **Existing budget line.** Listing media is already a line item. We are not
  creating a new spend category, we are undercutting one.
- **Photos already exist**, so our input cost is zero and their friction is a
  file upload.
- **Self-serving buyer.** An agent buys marketing to win the *next* listing, not
  just to sell this one. That makes the video a recruiting asset, which raises
  willingness to pay above what the single transaction justifies.
- **Fast decision.** One person decides. No procurement, no committee.

**Explicitly deferred** (all bigger, all slower): brokerages and enterprise,
new-construction developers, property management, hospitality. Revisit once 30+
individual agents have paid, per `business/06-roadmap.md`.

## 5. The compliance wedge — the most defensible part of the business

This is where a serious operator separates from the flood of AI-video hustlers.

An AI-generated video that reads as drone footage is a **disclosure problem even
when every source photograph is genuine**. The images are real. The flight is not.

Verified rules:

- **NAR Code of Ethics, Article 12 and Standard of Practice 12-5** — REALTORS®
  must present a true picture and must disclose the status of any altered
  photograph. Binds every REALTOR®, in every state. `[MARKET]`
- **California AB 723**, adding **Business & Professions Code §10140.8**, signed
  2025-10-10, **effective 2026-01-01** — a broker, salesperson, **or a person
  acting on their behalf** who puts a digitally altered image in an advertisement
  must include a conspicuous statement that it was modified **and** provide a link
  to the original unaltered image by website, URL, or QR code. Where the ad is on
  a website, the unaltered image must be included. `[MARKET]`
- MLS penalties for non-disclosure commonly run **$500–$5,000**. `[MARKET]`

Two consequences most competitors have not absorbed:

1. **"A person acting on their behalf" puts the vendor inside the statute.** A
   video shop selling AI flythroughs in California is a regulated party, not a
   neutral supplier. Selling undisclosed AI video is not merely the agent's risk.
2. **AB 723 requires a link to the original.** That is a *hosted artefact*. Every
   FlyThrough delivery ships a disclosure page carrying the agent's own unaltered
   photos, reachable by URL and QR.

So compliance is not a disclaimer we attach. It is generated by the pipeline for
every job, and it is the strongest thing we sell:

> Every competitor's video creates a compliance liability for the agent.
> Ours arrives with the liability already discharged.

That reframes the entire sales conversation from *"cheaper video"* — a race to the
bottom anyone can enter — to *"the only AI listing video that doesn't put your
licence at risk."* Price competition does not touch that.

**Where our authority ends:** we are not lawyers. The disclosure text is built
from published rules, and a real estate attorney must review it in each operating
state before it ships. Board rules vary and move; re-check quarterly. This is
stated in every delivery and in `business/05-compliance.md`.

## 6. Competitive landscape

| Competitor type | Their price `[MARKET]` | Their advantage | Where they lose |
|---|---|---|---|
| Local photo/video shop | $300–$1,200/listing | Real footage, local trust | Slow, weather-bound, priced out of most listings |
| Licensed drone operator | $150–$500/listing | True aerial, FAA-credentialed | Exterior only, needs a scheduled flight |
| Photo-bundled aerial add-on | $75–$200 add-on | Cheapest real aerial | Stills-led; video is an afterthought |
| DIY phone + CapCut | ~$0 | Free | Time the agent doesn't have; looks amateur |
| Generic AI video tools | subscription | Cheap, instant | Single-anchor drift, **no disclosure layer**, agent carries all risk |

**Our position:** priced beneath every human-crew option, above free DIY, and
alone in the market on compliance. We do not claim to replace true aerial
cinematography — we say so plainly in the sales script, because a claim that
collapses on first inspection costs more than it wins.

## 7. What would have to be true for this to fail

Stated up front, because a plan that only lists reasons to win is a pitch, not a
plan.

1. **Agents don't care about disclosure until someone is fined.** Plausible. The
   mitigation is that the compliance layer costs us nothing per job — it is
   generated automatically — so if it fails as a wedge we still win on price and
   speed, and we are positioned the day enforcement starts.
2. **Model output isn't good enough on real, uneven agent photos.** This is the
   genuine technical risk and it is **unresolved until real samples are rendered**
   (see `business/07-open-questions.md`). Mixed lighting and inconsistent
   white balance between two anchor photos may produce a visible pop at the seam.
3. **A platform bundles this for free.** If a major listing platform ships
   one-click AI video, the standalone service compresses hard. Mitigation: the
   retainer relationship and the compliance artefact, neither of which a bundled
   feature is likely to provide.
4. **Outreach doesn't scale.** See the honest channel critique in
   `business/03-go-to-market.md` §4 — cold outreach alone cannot carry $10k/mo.
