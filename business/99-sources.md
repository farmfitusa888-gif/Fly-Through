# Sources and Provenance

Every external figure used in this buildout, with where it came from and how much
to trust it. Retrieved **2026-08-20**.

## `[VERIFIED]` — read from a provider's own tool this session

Read via the OpenArt MCP `openart_model_cost` and `openart_model_form_get` tools.
Reproduce by re-running those tools.

| Fact | Value |
|---|---|
| Wan 2.7 image2video, 720p | 25 credits/sec (125cr @5s, 250cr @10s — linear) |
| Wan 2.7 image2video, 1080p | 35 credits/sec (175cr @5s, 350cr @10s — linear) |
| Kling 3 Omni image2video, std and pro | 175cr @5s |
| PixVerse V6 image2video, 540p / 1080p | 50cr / 150cr @5s |
| Seedance 2.0 image2video, 720p + audio | 400cr @5s |
| Models accepting start **and** end frame | Wan 2.7, Kling 3 Omni, Seedance 2.x, PixVerse V6 |
| Account plan / balance at build time | Plus, 9,690 credits |

## `[MARKET]` — secondary sources, re-check before client-facing use

### Market pricing
- Drone photography $150–$400/listing, premium to $750; $250–$500 for 5–10 photos
  plus a 30–120s video; ~$225 average for aerial stills bundled with interiors
- 2–3 minute real estate video $400–$800; basic walkthrough $300–$500; cinematic
  mid-range $700–$1,200; luxury with drone $1,500–$3,000+
- FAA-licensed drone operators $100–$350 standalone, $75–$200 as an add-on

Sources: [Fash](https://fash.com/costs/drone-photography-pricing) ·
[PhotoUp](https://www.photoup.net/learn/drone-real-estate-photography-pricing) ·
[Skyebrowse](https://www.skyebrowse.com/news/posts/drone-photography-cost) ·
[Amplifiles](https://www.amplifiles.ai/blog/real-estate-drone-photography-pricing) ·
[Reel Estate](https://tryreelestate.com/blog/real-estate-drone-video-cost) ·
[Fluxnote](https://fluxnote.io/guides/real-estate-video-pricing-for-photographers)

### Video adoption and demand
- 85% of homebuyers watch video during their search
- 73% of homeowners more likely to list with an agent who uses video (63% in 2021)
- Only ~38% of agents use video; **~9% make listing-specific videos**
- 58% of buyers expect to see video of a home they are considering

Sources: [Luxury Presence](https://www.luxurypresence.com/blogs/real-estate-video-marketing/) ·
[PhotoUp](https://www.photoup.net/learn/real-estate-video-statistics) ·
[Reel-E](https://www.reel-e.ai/blog/real-estate-marketing-statistics) ·
[Amplifiles](https://www.amplifiles.ai/blog/real-estate-social-media-statistics)

> **Do not use the widely repeated "403% more inquiries" figure in sales copy.**
> It is commonly attributed to NAR but is hard to trace to a primary publication.
> An unverifiable performance claim is an FTC risk and collapses under a client's
> own search. Use the sourceable figures above instead.

### Compliance
- NAR Code of Ethics Article 12 / Standard of Practice 12-5 — true picture; must
  disclose the status of any altered photograph
- California **AB 723** → Bus. & Prof. Code **§10140.8**; approved 2025-10-10,
  effective **2026-01-01**; conspicuous modified-image statement plus a link to
  the original unaltered image by website, URL or QR; unaltered image included
  where the ad is on a website; routine edits (lighting, sharpening, white
  balance, colour correction, angle, straightening, cropping, exposure) excluded
- MLS fines for non-disclosure commonly $500–$5,000
- New York 19 NYCRR §175.25(c)(9) — advertising must honestly and accurately
  depict the property
- Colorado AI law delayed to January 2027 under SB 189, narrowed away from staging

Sources: [NorthstarMLS](https://northstarmls.com/insights/guidelines-for-virtual-staging-and-ai-enhanced-listing-photos/) ·
[CA AB 723 bill text](https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202520260AB723) ·
[SDMLS](https://sdmls.com/ab-723-digitally-altered-images-sdmls-requirements/) ·
[PSAR](https://blog.psar.org/navigating-ab-723-new-photo-disclosure-rules) ·
[WAV Group](https://www.wavgroup.com/2025/11/19/californias-new-photo-disclosure-law-and-what-it-means-for-mlss-and-brokerages/) ·
[HousingWire](https://www.housingwire.com/articles/ai-listing-video-disclosure-test/)

> **Could not be read directly.** `openart.ai`, `docs.fal.ai`,
> `leginfo.legislature.ca.gov`, `housingwire.com` and `meltflexai.com` were all
> blocked by the build environment's egress proxy. The compliance facts above
> come from search-result summaries of those pages, not the pages themselves.
> **Read the AB 723 bill text directly before relying on it commercially.**

## `[ASSUMPTION]` — planning inputs, not measurements

| Assumption | Value | Why chosen | Replace with |
|---|---|---|---|
| USD per credit | $0.0030 | Reported $15 / 5,000-credit add-on pack | A real top-up receipt |
| Re-roll rate | 25% | Conservative for a new pipeline | Measured over 20 jobs |
| Operator minutes/job | 25 | Sum of the steps needing a human | Timed jobs |
| Target hourly | $75 | What the founder's hour must be worth | Founder's call |
| Outreach reply rate | 8% | Typical for personalised B2B cold email | Measured |
| Close rate on reply | 20% | With a free sample in hand | Measured |
| Hosting per job | $0.05 | Object storage + bandwidth for one delivery | First invoice |
| Payment fees | 2.9% + $0.30 | Published card-processing rate | — |
