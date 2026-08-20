# Compliance and Risk

> **Not legal advice.** This documents published rules as read on 2026-08-20 and
> the product decisions taken in response. Rules vary by MLS and by state and they
> change. **A licensed real estate attorney must review the disclosure language in
> each state before it ships.** Re-check board rules quarterly. Where this
> document and a board's rules disagree, the board wins.

## 1. The core exposure, stated plainly

An AI-generated video that looks like drone footage is a **disclosure problem even
when every source photograph is genuine.**

> The images are real. The flight is not.

A buyer watching a smooth aerial approach reasonably believes a camera flew that
path. None did. That gap between what the viewer infers and what happened is the
exposure — and it exists independently of whether the house is depicted
accurately.

This is why disclosure is a build requirement in this business and not a
nice-to-have.

## 2. Rules that apply

### NAR Code of Ethics — Article 12, Standard of Practice 12-5
REALTORS® must present a true picture in advertising and **must disclose the
status of any altered photograph**. Binds every REALTOR® nationally, in every
state, independent of MLS rules. `[MARKET]`

### California AB 723 → Business & Professions Code §10140.8
Approved 2025-10-10. **Effective 2026-01-01.** `[MARKET]`

Requires that a real estate broker, salesperson, **or a person acting on their
behalf**, who includes a digitally altered image in an advertisement or
promotional material for the sale of real property:

- include a **conspicuous statement** that the image has been modified, **and**
- provide **a link to the original, unaltered image** by website, URL, or QR code

Where the advertisement is on a website, the unaltered image itself must be
included.

**Excluded** — and this exclusion matters: lighting, sharpening, white balance,
colour correction, angle, straightening, cropping, and exposure adjustments are
*not* digitally altered images, because they do not change the representation of
the property.

### MLS enforcement
Non-disclosure of virtual staging commonly draws fines of **$500–$5,000**,
varying by board. `[MARKET]`

### Other jurisdictions to track
- **New York** — 19 NYCRR §175.25(c)(9): advertising must honestly and accurately
  depict the property. `[MARKET]`
- **Colorado** — AI law delayed to January 2027 under SB 189 and narrowed away
  from staging photos. `[MARKET]`

## 3. Two conclusions most competitors have missed

**1. "A person acting on their behalf" puts the vendor inside the statute.**
A shop selling AI flythroughs into California is a regulated party. This is not
purely the agent's risk to manage, and a vendor who tells an agent otherwise is
wrong in a way that is expensive for both of them.

**2. AB 723 requires a hosted artefact, not a sentence.**
"Link to the original unaltered image" means something has to exist at a URL. Most
competitors ship a video and a disclaimer. Neither satisfies the link
requirement. **We ship the page.**

## 4. How the product discharges each requirement

| Requirement | Artefact | Where it lives |
|---|---|---|
| Conspicuous modified-image statement | Burned-in opening card, 2.5s, full frame | `compliance.make_card` |
| Statement survives re-posting | Card is **in the video**, not the caption | burned into the master |
| Link to the original | QR code + printed URL on the card | `compliance.make_qr` |
| Originals available on a website | Hosted originals page with every unaltered photo | `compliance.make_page` |
| MLS remarks disclosure | Pre-written caption text | `compliance.CAPTION` |
| Social disclosure | Short-form caption | `compliance.CAPTION_SHORT` |
| Audit trail | Per-job JSON recording basis and URL | `{slug}_disclosure.json` |

It is generated for **every** job. An agent cannot forget it, and we cannot skip
it under deadline pressure, because it is a pipeline stage rather than a habit.

## 5. The rule that protects the whole position

**We never alter the source photographs.** No retouching, no staging, no colour
correction, no sky replacement.

The reason is structural, not aesthetic. The originals page must contain
*originals*. The moment we edit a supplied still, the page stops being an
unaltered-image archive and the AB 723 position collapses — for us and for the
client. It also keeps us squarely inside the statute's exclusion for routine
adjustments, since we make none at all.

Sky replacement and virtual staging are lucrative adjacent services. **We do not
sell them**, and the reason we don't is itself a sales argument.

## 6. Other risk

| Risk | Mitigation |
|---|---|
| **Misrepresenting a property** — a generated transition implies a room adjacency that doesn't exist | Anchored shots bound this, but review for it at the quality gate. Never generate a transition between two rooms that do not actually connect; reorder the plan instead. |
| **FTC deceptive advertising** on our own marketing | No fabricated testimonials, no invented performance claims. Every market statistic we publish carries its source, or we don't publish it. |
| **Unverifiable industry statistics** | The widely repeated "403% more inquiries" figure is frequently attributed to NAR but is hard to trace to a primary publication. **Do not put it in sales copy.** Use the sourceable ones — 85% of buyers watch video, 73% of sellers prefer agents who use it. A claim that collapses under a client's Google search costs more than it wins. |
| **Model provider changes pricing or removes a model** | Rate card is data, not code (`cost.py: RATE_CARD`). Adapter layer means swapping providers is a config change. Re-verify pricing before each quote. |
| **Client uses our video after the listing sells** | Licence grants use for marketing that property and the agent's own promotion. Put it in the terms. |
| **Music licensing** | Only licensed beds. Never library-scraped audio — a copyright strike on an agent's account ends the relationship. |
| **Fair housing** | Our negative prompt bank suppresses people entirely from generated footage. This is a deliberate choice: generated humans in listing media invite fair-housing exposure over who is depicted. Never generate people. |

## 7. Before operating in a new state

1. Read that state's real estate advertising regulations.
2. Read the operating MLS's photo and video rules.
3. Have a licensed attorney in that state review the disclosure text.
4. Record the result in this file with the date.

**Currently reviewed by an attorney: none.** This must happen before the first
paid California delivery.
