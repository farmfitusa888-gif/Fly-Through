# Requirement: Client Shot Guide (queued)

**Status:** specified, not yet built. Build after the pipeline/demo work completes.

## What it is

A client-facing document handed to an agent or photographer **before** they send
photos, specifying exactly what to supply: which rooms, how many, from what
angles, in what order, and what disqualifies a shot.

## Why it is load-bearing

Intake quality is the single largest determinant of output quality, and it is the
one variable we do not control. `business/04-operations.md` already requires
rejecting a bad intake before rendering — this guide is what makes that rare
rather than routine. It also protects the constraint identified in
`business/02-unit-economics.md`: every missing photo costs operator minutes, and
operator minutes are the only scarce input in this business.

## Hard design rule

**Generate it from the pipeline constants. Never hand-write it.**

The rules already live in code:

| Rule | Source of truth |
|---|---|
| Required tour anchors | `planner.REQUIRED_ANCHORS` |
| Minimum / ideal photo count | `planner._audit` |
| Recognised room labels and aliases | `rooms.HEADS`, `rooms.ALIASES` |
| Buyer-walk ordering | `rooms.TOUR_ORDER` |
| Rooms never used as a hero frame | `rooms.NON_HERO` |
| Which transitions need which coverage | `moves.MOVES`, `moves._RULES` |

A hand-written guide drifts from the validator the first time either changes, and
the failure surfaces as a client who followed the instructions and still got
warnings. One source of truth, or it will break.

## Two audiences, two versions

**A. For listing agents** — plain language, phone-shootable, no jargon.
Framed primarily as *"which of the photos you already have to send me"*, since
that is the core pitch, with a secondary path for shooting fresh.

**B. For photographer partners** — technical. Focal length, straight verticals,
consistent white balance and exposure **between adjacent rooms in tour order**.

### Two rules the guide MUST carry, both learned from real failures

**1. The aerial must be framed over the same side of the house as the ground
shot that precedes it.** Discovered in the first full demo tour: a patio still
(shot from the lawn, looking at the REAR) was paired with an aerial framed over
the FRONT. Asked to connect them in one continuous move, the model flew up and
over and landed on what looked like a different house. There is no camera path
between a ground view of the back and an overhead view of the front, so the model
invented one. Now enforced by `viewpoint.assess`, but the real fix is at capture:
tell the client which side to shoot the aerial from.

**2. Never supply photos of opposite elevations with nothing between them.**
Front directly to rear has no continuous path either. The guide should ask for a
side elevation or an aerial as the bridge.

> The most important line in version B: adjacent anchor photos must match in
> white balance and exposure. A colour pop at the seam is the failure mode most
> likely to appear on real jobs, because agents shoot rooms at different times of
> day. A photographer prevents it at capture for free; it cannot be fully fixed
> downstream, and fixing it in the render is forbidden by the never-patch-output
> rule.

## Deliverable formats

- Markdown source in `docs/`
- Printable one-page checklist (the thing that actually gets used on site)
- Hosted page for linking from outreach and the intake form

## Acceptance criteria

- [ ] Regenerating after a change to `REQUIRED_ANCHORS` updates the guide with no manual edit
- [ ] Every room name in the guide resolves through `rooms.resolve()`
- [ ] Both audience versions produced from one source
- [ ] A shoot following the guide produces a plan with **zero** warnings from `_audit()`
- [ ] Names the seam-matching rule explicitly in the photographer version
- [ ] Names the aerial-side rule and the opposite-elevation rule, both of which
      are enforced by `viewpoint.assess` and must agree with it
