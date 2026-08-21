# Selling online

Everything in the catalogue can be bought without a conversation. This is how
that works, what it costs, and what has to be true before the first button goes
live.

## Why Payment Links and not a shopping cart

The site is static. It is one HTML file plus a few pages in a bucket, with no
server, no database and no session. That is not a limitation to be worked
around — it is the reason the site costs nothing to run, cannot be breached,
and cannot go down while a customer is trying to pay.

Stripe Payment Links preserve that. Each one is a public URL. There is no API
key in the page, nothing to leak, and no PCI surface: the customer leaves for
Stripe's own checkout and comes back. A cart would mean a backend, a backend
means secrets, secrets mean a thing that can be stolen — for a catalogue of
thirteen fixed-price SKUs that never change mid-session.

If the catalogue ever grows a configurator (pick your runtime, pick your
aspect, pick five vehicles), that logic goes in Stripe's own checkout, not into
a server we have to keep alive.

## The flow

```
landing page  ──Buy──▶  Stripe checkout  ──success──▶  /start?sku=<id>
                                                            │
                                              customer fills 4 fields
                                                            │
                                                  pre-filled email
                                                            ▼
                                                    photos land in inbox
```

The success page is the intake form, not a receipt. A checkout that ends on
"thanks for your order" is a job that cannot start: we still need photos and
four facts, and the one moment the customer is guaranteed to be paying
attention is the second after they pay. Chasing that by email afterwards is
where a 24-hour turnaround quietly becomes four days.

## Setting it up

For each SKU in `model/catalog.py`:

1. **Stripe → Product catalogue → Add product.** Name it exactly as the SKU's
   `name`. Price from the same place. Set recurring/monthly for the four
   recurring SKUs (`re-retainer`, `lot-25`, `lot-50`, `lot-100`) and one-time
   for the rest.
2. **Create a Payment Link** for that product.
3. **After payment → Redirect to your website**, set to
   `https://iflythroughit.com/start?sku=<the sku id>`.
   The `?sku=` is what makes the intake page ask vehicle questions instead of
   property ones. Get it wrong and the customer is asked for a VIN for their
   listing.
4. **Collect the customer's email** — on by default, leave it on. It is the
   reply address when the photos do not arrive.
5. Paste the link into `site/config.json` under `payments.links`, then
   `python3 site/build_all.py`.

A SKU with an empty link renders an **Order by email** button instead of a Buy
button. That is deliberate: a dead button on a price is worse than no price at
all, and a button that 404s after someone has decided to spend money is worse
than both. Launch with three links live rather than thirteen broken ones.

## What the buttons cost

Stripe takes 2.9% + $0.30 on a domestic card. That is already in every margin
number in `model/catalog.py`, and it is why the flat fee matters more than it
looks: on a $39 walkaround it is most of the fee, which is exactly why the lot
plans bill **once for the month** rather than once per vehicle. Fifty
walkarounds sold individually pay the flat fee fifty times.

Lowest margin in the catalogue is `lot-100` at 89.0%. Nothing sells below cost.

## Before the first button goes live

- [ ] Both domains pointing at the bucket, HTTPS on
- [ ] `contact_email` in `site/config.json` is a mailbox someone actually reads
- [ ] Terms and refund policy written and linked from checkout — Stripe asks for
      a URL and this is not the moment to improvise one
- [ ] A test purchase in Stripe **test mode**, all the way through to the intake
      email arriving
- [ ] The same test in live mode for one SKU, then refunded

## The refund position

Refund on request, no argument, until the film is delivered. After delivery,
one free re-cut instead of a refund.

This is not generosity, it is arithmetic. The render cost of a delivered film is
between $1.57 and $2.10. Arguing with a customer over $149 costs more in time
than re-cutting the film does in credits, and a chargeback costs the fee plus
$15 plus the dispute. Re-cut it.

The one thing that is not refundable is a job where the customer's photos
cannot make a film and they were told so before we charged — which is what the
intake check exists to catch, before the money moves.

## What is deliberately not for sale online

**Anything with a person in it.** `products.PERSON_RISK` flags `in_use` and
`scale` frames at intake because generating motion across a photograph of an
identifiable person is a different question from moving a camera past a
handbag. That gets a conversation, not a checkout.

**Testimonials, in any form.** The FTC Rule on Consumer Reviews and Testimonials
(in force 21 October 2024) bans AI-generated testimonials outright —
**regardless of disclosure** — at $53,088 per violation as adjusted for 2026.
There is no version of this we sell. See `business/05-compliance.md`.

**Real estate without a disclosure pack.** `compliance.check_placement` refuses
`none` for the `rooms` vertical in code, so it cannot be sold as an option even
by accident.
