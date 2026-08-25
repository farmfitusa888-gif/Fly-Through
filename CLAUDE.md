# FlyThrough

Anchored AI video: every shot begins and ends on a real photograph the client
supplied, and the model generates only the camera travel between them. That
constraint is the product, the moat and the compliance position — it is never
traded away for a nicer-looking shot.

## Working preferences

- **Ask questions with the AskUserQuestion picker, always.** Never write options
  out as prose in the reply; the operator wants to click, and wants to be able
  to change an answer afterwards.
- **Never spend credits without explicit approval**, and never propose spending
  as a way around a transfer or tooling problem.
- **Always check the project image inventory before generating**, and never
  generate a duplicate of something already rendered.
- **Batch renders** — multiple images per render where the model bills per
  render rather than per output.
- **Customise every ad to the product.** A template cut is a walkaround, not an
  advert, and the two are priced and sold differently on purpose.
- Close each reply with a ranked Top 3 of recommendations.

## Layout

    pipeline/     the renderer: taxonomies, planner, moves, assemble, compliance
    model/        priced offers and the sellable catalogue. The ONLY source of a number.
    site/         the static marketing site + disclosure pages. `python3 site/build_all.py`
    service/      the V2 self-serve product (FastAPI). See service/README.md
    samples/      real rendered work
    business/     strategy, unit economics, compliance, store setup
    docs/         generated client shot guides
    sales/        outreach copy

## Rules the code enforces

- **No price is typed into a page.** Every number comes from `model/` through
  `model/export_pricing.py`; a test fails the build if a `$` figure appears in
  the landing template.
- **No disclosure page ships without its originals.** `/o/<slug>/` is the
  artefact Bus. & Prof. Code §10140.8 requires a link to. Missing originals
  means the page is not published and any stale copy is deleted.
- **Real estate cannot opt out of disclosure.** `compliance.check_placement`
  refuses `none` for the `rooms` vertical.
- **No AI-generated testimonials, ever.** The FTC Reviews & Testimonials Rule
  bans them regardless of disclosure.
- **We never retouch a client's photograph.** The moment we do, the originals
  page stops containing originals.

## Commands

    python3 -m pytest pipeline/tests service/tests -q    # everything
    python3 site/build_all.py                            # build + link-check the site
    python3 model/catalog.py                             # what is sellable
    python3 samples/cars/build.py status                 # which clips are present
