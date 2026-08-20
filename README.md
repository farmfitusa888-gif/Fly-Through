# FlyThrough

**Cinematic drone-style property videos, generated from listing photos an agent
already owns — with the AI disclosure the law now requires built into every
delivery.**

---

## The idea in one diagram

```
 photo A (real)  ────  AI generates only the camera travel  ────  photo B (real)
   kitchen                                                            dining
```

Naive AI listing video feeds a model one photo and lets it hallucinate a flight.
Windows multiply, furniture melts, the back of the house is invented.

FlyThrough submits **both** ends of every shot: the agent's photo A as the start
frame and photo B as the end frame. The model is never asked what the house looks
like — it is told, twice, and asked only how the camera gets between them. Drift
is bounded by construction, because the clip cannot end anywhere except on a real
photograph of the real property.

## Repository map

| Path | What it is |
|---|---|
| `business/` | The full buildout — strategy, pricing, GTM, ops, compliance, roadmap |
| `business/99-sources.md` | Every external figure with its provenance and how far to trust it |
| `model/unit_economics.py` | Runnable financial model. Regenerates every number quoted in `business/` |
| `pipeline/flythrough/` | The production system |
| `sales/outreach.md` | Cold email, partner pitch, objection handling, delivery templates |
| `web/` | Landing page |
| `samples/` | Rendered example tours |

**Start here:** `business/00-strategy.md`, then run `python3 model/unit_economics.py`.

## The pipeline

```
photos ──> plan ──> manifest ──> render ──> assemble ──> disclose ──> deliver
           free      free         PAID       free         free
```

| Module | Responsibility |
|---|---|
| `rooms.py` | Head-noun label parser. The rightmost noun is the room (`guest bath` → bathroom); `master`/`primary` qualifiers upgrade it. Orders photos into a buyer's-walk sequence. |
| `moves.py` | Camera move library keyed on transition type, plus the negative-prompt banks that suppress observed drift failure modes. |
| `planner.py` | Photos → costed shot plan. Runtime caps drop **photos, not transitions**, so a trimmed tour can never jump-cut. |
| `cost.py` | Rate card read from the provider's own pricing tool. Refuses models that cannot hold two anchor frames. |
| `render.py` | Schema-valid provider payloads and a reviewable spend-gate manifest. |
| `assemble.py` | ffmpeg delivery: 16:9 master, 9:16 vertical, thumbnail, music bed. |
| `compliance.py` | Disclosure card, QR, captions, and the hosted originals page. |

### No command can spend money as a side effect

`plan`, `manifest` and `assemble` are all free. `manifest` writes every payload
and the total cost to a file for review; submission is a separate, explicit step.

## Usage

```bash
pip install -r pipeline/requirements.txt      # + ffmpeg on PATH

# 1. Photos -> shot plan + cost quote (free)
PYTHONPATH=pipeline python3 -m flythrough.cli plan ./photos \
    --listing "1420 Cedar Ridge Rd" --style goldenhour --max-seconds 45

# 2. Shot plan -> provider payloads. Review this before spending. (free)
PYTHONPATH=pipeline python3 -m flythrough.cli manifest plans/1420-cedar-ridge.plan.json \
    --photos ./photos

# 3. Rendered clips -> delivered files (free, local ffmpeg)
PYTHONPATH=pipeline python3 -m flythrough.cli assemble ./clips \
    --listing "1420 Cedar Ridge Rd" --music bed.m4a
```

Photos are labelled by filename (`04_great-room.jpg`, `IMG_4471 front
elevation.jpg`) or by a `rooms.json` sidecar mapping filename → room, which wins
when present.

## Compliance is a pipeline stage, not a checklist

An AI-generated video that reads as drone footage is a disclosure problem **even
when every source photo is genuine**. The images are real; the flight is not.

- **NAR Code of Ethics Article 12 / SOP 12-5** — must present a true picture and
  disclose the status of any altered photograph. Binds every REALTOR® nationally.
- **California AB 723** → Bus. & Prof. Code **§10140.8**, effective 2026-01-01 —
  a broker, salesperson, **or a person acting on their behalf** must include a
  conspicuous modified-image statement **and a link to the original unaltered
  image** by URL or QR.

That second clause puts the video vendor inside the statute. So every job
generates a burned-in disclosure card, a QR code, MLS and social caption text, and
a hosted page carrying the agent's unaltered originals. The card is burned into
the master because captions do not survive re-posting.

**We never alter the source photographs.** Not a service limitation — a structural
one. The moment a supplied still is edited, the originals page stops containing
originals and the entire disclosure position collapses.

> Not legal advice. Rules vary by MLS and state and they move. Have a real estate
> attorney review the disclosure text in each operating state.
> See `business/05-compliance.md`.

## Tests

```bash
cd pipeline && python3 -m pytest tests/ -q
```

40 tests covering label resolution against real-world filename shapes, tour
continuity under every runtime cap, cost agreement with the verified rate card,
provider payload schema conformance, mixed-geometry assembly, and disclosure
completeness.

## Honesty about what is and isn't proven

- Costs marked `[VERIFIED]` were read from the provider's own pricing tool.
- The USD-per-credit figure is **an unverified estimate**; the provider's pricing
  page was unreachable from the build environment. The model survives a 5× error.
- Conversion, reply, re-roll and operator-time figures are **assumptions**, marked
  as such, listed in `business/99-sources.md` with what would replace them.
- Output quality on **real** agent photography with mixed white balance is the
  main open technical question. See `business/07-open-questions.md`.
