# Operations Playbook

The whole job, in the order it happens. Written so someone other than the founder
can run it — because the constraint identified in `01-offer-and-pricing.md` is
operator minutes, and a process only a founder can execute cannot be delegated.

## The 25-minute job

| # | Step | Time | Automated? |
|---|---|---|---|
| 1 | Intake: receive photos + address | 2m | Form |
| 2 | Photo audit: count, anchors, labels | 3m | `flythrough plan` warns |
| 3 | Build and review the shot plan | 4m | `flythrough plan` |
| 4 | Generate the job manifest, check the cost | 1m | `flythrough manifest` |
| 5 | Submit renders | 1m | provider |
| 6 | *(wait — not operator time)* | — | — |
| 7 | Spot-check each clip for drift | 6m | manual, the real work |
| 8 | Assemble master, vertical, thumbnail | 2m | `flythrough assemble` |
| 9 | Generate disclosure pack, publish originals page | 2m | `compliance.build_pack` |
| 10 | Deliver with captions + the referral ask | 4m | template |

**Step 7 is the entire operating cost of this business.** Every automation dollar
belongs there and nowhere else. Steps 2, 3, 4, 8 and 9 are already code.

## Intake — what we require before a job starts

Non-negotiable, because a bad shoot in produces a bad tour out and no amount of
prompt work fixes it:

- **Minimum 6 photos, ideally 8–14.** Below 4 the pipeline emits a warning and
  the result is a clip, not a tour.
- **Must include an exterior or aerial shot.** A property video with no
  establishing shot of the building underperforms; the pipeline warns when it is
  missing. Ask for it rather than rendering without it.
- **Must include living room and kitchen.** These are the two rooms that sell the
  house and the two the tour is built around.
- **Landscape orientation, highest resolution available, unedited originals.**
- **Room labels** via filename or a `rooms.json` sidecar. The parser handles the
  labels agents actually use (`09_master-bath`, `IMG_4471 front elevation`), but
  an explicit label from the person who stood in the room always wins.

If an intake fails these checks, **say so before rendering**. A five-minute email
asking for two more photos is cheaper than a re-render and far cheaper than a
refund.

## Quality gate — what gets a clip rejected at step 7

Check each clip at full screen, not in a thumbnail grid. Reject and re-roll on:

- **Architecture drift** — window count, roof line, or door position changes
  between the anchors
- **Furniture morphing** — objects melting, sliding, or appearing mid-shot
- **Impossible geometry** — a room that could not exist, a corridor to nowhere
- **A person or reflection of a person** appearing anywhere
- **Text artefacts** — invented signage, house numbers, or watermarks
- **Exposure pumping** on interior↔exterior transitions
- **A seam pop** at the join, where the two anchor photos differ in white balance

The last one is the failure mode most likely to appear on real agent photos,
because agents supply images shot at different times of day. If it recurs, the
fix is upstream — normalise white balance across anchors before submitting —
**not** a colour grade on the finished clip.

> **Never fix a rendered clip.** If output is wrong, the plan or the prompt bank
> is wrong. Fix it there and re-render, so every future job inherits the fix.

## Delivery

Every delivery contains, without exception:

1. `{slug}_master_16x9.mp4` — disclosure card burned onto the head
2. `{slug}_vertical_9x16.mp4` — Pro and above
3. `{slug}_thumb.jpg`
4. `{slug}_originals_qr.png`
5. A live originals page URL carrying the agent's unaltered photos
6. `{slug}_disclosure.json` — MLS remarks text and social caption, ready to paste

Plus, in the delivery email: how to paste the MLS remark, and the referral ask.

## Failure handling

| Failure | Response |
|---|---|
| One shot fails to render | Re-roll that shot only. A 12-shot job losing one is a re-roll, not a restart — `submit_all` is built for this. |
| Whole batch fails | Check provider status before resubmitting. Never resubmit blind; that spends twice. |
| Client rejects the tour | One free re-plan with different shot order. If the photos are the problem, say so plainly and offer the refund. |
| Late delivery | Refund in full, unprompted, and deliver anyway. The refund costs $249; the reputation costs the market. |

## What to automate next, in order

Ranked by minutes saved per dollar spent, given that operator time is the binding
constraint:

1. **Automated first-pass drift detection** — compare the final rendered frame
   against the end-anchor photo and flag clips whose difference exceeds a
   threshold. Turns step 7 from watching 8 clips into reviewing 1–2 flagged ones.
   Biggest single win available. Perceptual hash or SSIM is sufficient.
2. **Intake form that runs `flythrough plan` on upload** and returns the warnings
   to the client before they pay. Kills bad jobs before they cost anything.
3. **Originals page auto-publish** to object storage on delivery.
4. **Self-serve checkout** — only after 30+ manual jobs have proven the workflow.
