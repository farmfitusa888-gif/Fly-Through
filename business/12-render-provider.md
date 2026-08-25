# Which renderer, and when to change

**Decision: render on the existing OpenArt account, by hand, until volume makes
that the bottleneck. Do not buy a second provider before then.**

Recorded 25 August 2026. This is the answer to a question that had been sitting
open since the provider adapter was built, and it turns out not to need the
adapter at all yet.

## The question that forced it

The service can queue a render, poll it and deliver the result. What it cannot
do is call OpenArt: **OpenArt has no public REST API.** It is reachable through
MCP tooling, which is a thing an operator sitting at a session has and a
FastAPI process running in a bucket does not.

The obvious reading is that taking money requires signing up with a provider
that does have an API — fal.ai, most likely — which means a new vendor, a new
key, a new bill and a rate we have not verified against a real invoice.

That reading is wrong, and it was wrong in an expensive direction.

## What is actually required

Nothing about the product requires the render to be *automatic*. It requires
the render to *happen*. Every frame this project has shipped so far was
rendered through exactly the tooling the operator already has, on an account
that is already paid for.

So `service/flythrough_service/manual.py` builds a render sheet: the plan, the
prompts, the anchor pairs in cut order, the credit cost and the dollar cost,
before anything is spent. The operator works it, uploads the clips, and the
same `deliver()` the automatic path uses assembles the film. A hand-worked
order and a machine-worked one produce an identical file — that is enforced by
running the same `build_plan` on both paths, not by discipline.

Proven on a real order: `veh-ad-premium`, four photographs in through the shoot
page, brief saved, paid through a signed Stripe webhook, render sheet worked,
clips uploaded, film and vertical cut and both delivered with the customer
mailed. No new vendor, no new key, no new spend.

## What this buys

- **Revenue does not wait on an integration.** The store can open on the
  existing account.
- **The provider rate stays verified.** $0.1050/sec is confirmed against a real
  credit purchase ($15 for 5,000 credits, confirmed by the account holder). A
  fal rate would be a number off a pricing page until the first invoice.
- **No second bill for capacity nobody is using.** At current volume the render
  on a $249 film is $1.68. Automating it saves operator minutes, not money.

## What it costs

Operator time per order, and a ceiling on throughput. That ceiling is the
trigger, not a hunch about scale.

## When to switch

Switch when **any one** of these is true:

1. Orders per week exceed what the operator can work without the render sheet
   becoming the reason a delivery is late. Measure it: the gap between `paid_at`
   and `delivered_at` in the orders table is the whole metric.
2. A lot plan sells. `lot-25` and up are 250+ seconds of render in one order;
   those are the SKUs where hand-working stops being reasonable first.
3. OpenArt's rate moves against us, or the account's availability becomes a
   single point of failure worth insuring against.

Nothing else counts. In particular, "it would be more elegant" does not count.

## What is already built for that day

The switch is a config change, not a project:

- `pipeline/flythrough/providers/` — payloads validated against the provider's
  own recorded schema, so a wrong field is caught before it is submitted rather
  than after it is billed.
- `pipeline/flythrough/providers/fal-queue.example.json` — the fal queue API,
  written from their documented submit/status/result endpoints.
- `plan_runner.render_order()` — refuses to run without a provider, so the
  automatic path cannot half-exist.
- `model/provider_switch.py` — answers what a rate change does to every price in
  the catalogue. Nothing in it goes below cost until **$1.30/sec, twelve times
  the current rate**, and `lot-100` is the first to feel it.

That last number is why this decision is safe to defer. There is no provider
rate on the market that breaks the pricing, so choosing later costs nothing
that choosing now would have saved.
