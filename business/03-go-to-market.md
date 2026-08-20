# Go-To-Market

## 1. The offer that opens every door

> "Send me the photos from your last listing. I'll make you a 40-second
> drone-style video of it, free, and you'll have it tomorrow. If you like it,
> it's $249 a listing going forward. If you don't, keep it anyway."

This works because it inverts the burden of proof. The agent risks nothing and
spends no time — the photos already exist and uploading them takes a minute.
Our cost to serve it is **$5.51** in render `[VERIFIED rate, ASSUMPTION credit price]`
plus ~25 minutes.

**The free-sample offer is the entire top of funnel.** At a 94.7% gross margin,
one conversion pays for **45 free samples**. There is no cheaper qualified lead in
this business and no reason to run paid acquisition until this is saturated.

Two hard rules on it:

- **Only sample listings that are currently active.** A video of a sold listing is
  a curiosity; a video of a live one is a tool they will use today, and using it
  is what converts.
- **Never sample more than one listing free per agent.** The second free one
  teaches them the price is zero.

## 2. Channels, ranked by revenue per hour

### Tier 1 — do these first

**1. Direct outreach to agents with active listings and no video.**
The qualification is visible from the listing page: photos present, video absent.
That is a pre-qualified prospect list, refreshed daily by the market itself, and
it costs nothing to build. Target the mid-market: enough listings to care, not
enough budget for a film crew.

**2. Real estate photographers as a channel partner.** The highest-leverage move
in this plan. A photographer already shoots 10–30 listings a month and already
owns the photos. They resell FlyThrough as their own video product at $349,
paying us $199. They get a video line on their invoice with no new equipment,
no pilot licence, and no extra site visit; we get 10–30 listings a month from one
relationship instead of thirty conversations.

> **One photographer partner is worth roughly 30 cold agents.** Prioritise
> accordingly. If this session's plan gets one thing right, make it this.

**3. Referral from the free sample.** Ask at the moment of delivery, which is the
only moment the agent is impressed: *"Who else in your office is still posting
listings with just photos?"* One question, asked every time.

### Tier 2 — after 10 paying clients

**4. Compliance-led content.** This is the differentiated play and nobody else in
the AI-video space can run it credibly. *"California's AB 723 took effect January
1st. If you're posting AI-enhanced listing images without a link to the originals,
here's what the rule actually says."* Educational, genuinely useful, and it
positions us as the compliant vendor without a single sales claim. Repurpose one
research pass into a post, a short video, an email, and a one-page PDF for
brokerage offices.

**5. Brokerage lunch-and-learns.** One room, 20–40 agents, and the compliance
angle is a legitimate reason for the managing broker to book you. Bring the
one-pager and three sample videos on a phone.

### Tier 3 — deliberately deferred

Paid ads, SEO, a marketplace listing. All are slower to first dollar than the
above, and none should start before the free-sample funnel is saturated.

## 3. The 30-day launch sequence

Written so it is executable cold, in order.

| Days | Action | Output |
|---|---|---|
| 1–2 | Render 3 portfolio samples end-to-end | 3 videos + 3 disclosure packs |
| 3 | Publish the landing page with all 3 embedded | Live URL |
| 4–5 | Build a 100-agent list: active listing, photos, no video | Spreadsheet with listing URL |
| 6–15 | 20 outreach/day offering the free sample | ~200 touches, expect ~16 replies `[ASSUMPTION 8%]` |
| 8–20 | Deliver every free sample within 24h | Samples out, ask for the referral on each |
| 12–25 | Convert samples to paid; pitch retainer on every close | First revenue |
| 20–30 | Approach 10 local real estate photographers with the partner offer | 1–2 partners |
| 30 | Review actuals against `model/unit_economics.py`; adjust price or channel | Decision |

## 4. The honest channel critique — read this before believing the plan

`model/unit_economics.py` computes what each revenue target actually requires at
$249, assuming an 8% reply rate and a 20% close on replies `[both ASSUMPTION]`:

| Target/mo | Jobs | Conversations | Outreach | **Outreach/working day** | Operator hrs |
|---|---|---|---|---|---|
| $2,000 | 8 | 40 | 502 | **24** | 3.3 |
| $5,000 | 20 | 100 | 1,255 | **60** | 8.4 |
| $10,000 | 40 | 201 | 2,510 | **120** | 16.7 |
| $20,000 | 80 | 402 | 5,020 | **239** | 33.5 |

**Read the bolded column, not the first one.**

- **$2,000/mo is comfortably achievable solo.** 24 personalised touches a day is a
  real morning's work, and 3.3 hours of fulfilment is nothing.
- **$5,000/mo is the honest ceiling for one person doing cold outreach.** 60
  touches a day, every working day, without the quality collapsing.
- **$10,000/mo via cold outreach alone is not real.** 120 personalised touches a
  day is not a thing one person sustains. Anyone who tells you otherwise is
  selling you outreach software.

So the plan does not scale by sending more email. It scales by **changing the
channel mix**:

1. **Photographer partnerships** replace 30 conversations with 1. Three active
   partners at 10 listings/month each is 30 jobs — $7,470/mo — from three
   relationships instead of 750 cold touches.
2. **Retainers** remove re-acquisition entirely. Ten retainers is $8,990/mo of
   recurring revenue with zero monthly outreach.
3. **Referrals** compound the free-sample funnel at zero marginal cost.

> **The correct $10k/month plan is 8 retainers plus 2 photographer partners —
> not 2,510 emails.** Every hour spent on partner and retainer conversations is
> worth roughly thirty spent on cold outreach. Structure the week accordingly.

## 5. What to measure from job one

Track these from the first sample. Without them the model above stays assumption
and never becomes fact.

| Metric | Why | Replaces which assumption |
|---|---|---|
| Reply rate on outreach | The top of the whole funnel | 8% |
| Free sample → paid conversion | The core business question | 20% |
| Minutes per job, measured | The only scarce input | 25 min |
| Re-roll rate per job | Drives operator time, not cost | 25% |
| Retainer attach rate | Determines whether this scales | — |
| Actual credits per delivered job | Confirms or kills the $0.0030 estimate | $0.0030/credit |

Ten completed jobs is enough to replace every assumption in this plan with a
measurement. Do that before spending a dollar on ads.
