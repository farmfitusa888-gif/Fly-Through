# Auto Dealer Sales Assets

The vertical the pipeline is best suited to and the one nobody in AI video is
working properly. Taxonomy is built and tested (`pipeline/flythrough/vehicles.py`).

> **Compliance warning, read before sending anything.** Vehicle advertising is
> governed by **FTC truth-in-advertising rules and state dealer advertising
> regulations**, which vary considerably by state and are actively enforced.
> It is **not** governed by NAR Article 12 or California AB 723 — do not reuse
> the real-estate disclosure language here. Have a dealer-advertising attorney
> in each operating state review the disclosure text before the first paid job.
> Several states regulate what may appear in a vehicle ad down to the pixel.

## 1. Why dealers beat listing agents

| | Listing agent | Auto dealer |
|---|---|---|
| Photos already shot to a standard | Sometimes | **Always** — house standard, 20–40 frames |
| Units to sell | 1–3 at a time | **60–400 in stock** |
| Video already expected by buyers | Emerging | **Established format** |
| Buying decision | One person, small budget | One person, marketing budget |
| Revenue shape | Per transaction | **Recurring — stock turns constantly** |
| Relationships needed for 30 jobs/mo | ~30 | **1** |

That last row is the whole argument. Thirty listing agents is thirty
conversations, thirty invoices and thirty chances to churn. One dealer group
with 300 units is one conversation.

## 2. The offer

**Every unit on your lot gets a 20-second walkaround video, built from the photos
your team already shoots. No studio, no turntable, no second visit.**

| Tier | Price | What |
|---|---|---|
| **Walkaround ×3** | **$117** | Smallest order — $39 each, 20s, 9:16 + 16:9 + thumbnail |
| **Lot plan — 25** | **$850/mo** | 25 units/month, $34 each |
| **Lot plan — 50** | **$1,450/mo** | 50 units/month, $29 each |
| **Lot plan — 100** | **$2,600/mo** | 100 units/month, $26 each |
| **Full inventory** | **quote** | Every new unit, API/folder drop, same-day |

**$39 a vehicle is deliberate.** It is below the mental threshold where a dealer
needs approval, and it compares against $150–300 for a videographer per unit —
which is exactly why almost no dealer shoots video for anything but the halo cars.

**Three is the minimum order**, and that is deliberate too. The flat card fee is
$0.30 and the handling on a single order — intake, chasing the photo link,
delivery — is identical whether the invoice reads $39 or $249. The floor is on
order size, not a discount; discounts start where the commitment does, at Lot 25.

A 20s walkaround renders for $2.10 (35 cr/sec at 1080p, verified rate), so every
tier on this table clears 89% gross margin before labour.

## 3. Cold email — dealers

**Subject:** `video for every unit on your lot, not just the nice ones`

> Hi {name} — you're photographing every vehicle that comes through anyway.
>
> I turn those photos into a 20-second walkaround video per unit. No studio, no
> turntable, no second pass by your photographer. You send the folder, I send
> back video for every VIN the next day.
>
> $39 a unit, three-unit minimum. Or $1,450/month for 50.
>
> Want me to do five of your current inventory free so you can put them on the
> VDPs and watch what happens to time-on-page?
>
> — {you}
> {portfolio link}

**Why five and not one.** A dealer cannot evaluate a video product on one unit —
they need enough to A/B against their existing listings. Five is still only
~$10 of render to us and it produces the metric that closes the deal.

## 4. The metric that closes it

Dealers do not buy on aesthetics. They buy on **VDP engagement** — time on the
vehicle detail page, and lead form submissions per view.

Set this up on the free five:

1. Pick five units that have been sitting 30+ days.
2. Add the video to those VDPs only.
3. Compare time-on-page and lead rate against five matched units without video,
   same age and price band, over two weeks.
4. Bring them the number.

If the number is good, the lot plan sells itself. If it is not, you have learned
something real for $10 rather than guessed for months.

## 5. Objection handling

**"We already do walkaround videos."**
> Then you know they cost $150–300 a unit and your team only does it for the
> nice ones. This is $39 and it covers every VIN, including the three-year-old
> trade-in nobody wants to spend a shoot on.

**"Is it AI? Our buyers will know."**
> Yes, and it says so on the video. Every shot starts and ends on your own
> photographs — the AI only fills the camera movement between two real frames,
> so it can't invent a trim level or a wheel you don't have. That's the whole
> design. If you want a real videographer walking the lot, that's a different
> product at four times the price.

**"Who owns the video?"**
> You do, outright, on delivery. Use it on the VDP, on Marketplace, in ads,
> anywhere. No licence period, no takedown when you stop being a customer.

**"What about compliance?"**
> Straight answer: vehicle advertising rules are state by state and I'm not your
> lawyer. What I can tell you is the video never shows a feature that isn't in
> your photos, and it carries an AI-generated notice on the front. Run the
> disclosure past your compliance person — I'll adjust the wording to whatever
> they want.

*Never bluff on this one. Dealers have compliance staff and they will ask.*

## 6. Intake — what a dealer sends

Per unit, minimum 4 frames, ideally 6–8, named by facet:

`01_hero.jpg` · `02_driver-side.jpg` · `03_rear.jpg` · `04_dash.jpg`
`05_front-seats.jpg` · `06_engine.jpg` · `07_wheels.jpg` · `08_odometer.jpg`

**Required:** hero (three-quarter front), dash, front seats.
**Never used as the thumbnail:** odometer, VIN, undercarriage, wheels — buyers
need them, but they don't sell the unit.

**The rule specific to vehicles:** don't jump from the driver side straight to
the passenger side. There's no camera path across the vehicle, and the model
will invent one — `viewpoint.assess` blocks it before anything renders. Send the
front or rear as the bridge, which their standard shot list already includes.

## 7. Where the volume actually comes from

Same lesson as real estate: not from more cold emails.

- **Dealer groups, not single rooftops.** One group with six stores is six lots
  from one contract.
- **Dealership photographers and vendors.** The companies that already shoot
  inventory for dealers are the same channel play as real-estate photographers —
  they resell it, you never make the call.
- **Auction and wholesale.** Units moving between dealers need media too, and
  nobody shoots video for a wholesale unit.
