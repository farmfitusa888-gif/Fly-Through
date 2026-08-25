# Deploying

    python3 site/build_all.py

Then publish `site/dist/`. That is the whole build. It fails loudly rather than
shipping something broken: a dead internal link, a missing shot guide, or a
disclosure page whose originals are not on disk all stop the build.

## Host

Netlify or Cloudflare Pages. Both read `_headers` and `_redirects` straight out
of the publish root, which is where `build_all.py` writes them. Any other bucket
works too — it will just ignore those two files, and you will have to configure
the redirects and headers in the host's own console instead.

**Publish directory:** `site/dist`
**Build command:** `python3 site/build_all.py`
**No server, no environment variables, no secrets.** There is nothing in this
deployment that can leak, because there is nothing in it to leak.

## DNS

Both domains point at the same deployment.

| Record | Value |
|---|---|
| `iflythroughit.com` | the host's apex target (ALIAS/ANAME, or A record if that is all your registrar offers) |
| `www.iflythroughit.com` | CNAME to the host |
| `iflytoit.com` | same host, added as a domain alias |
| `www.iflytoit.com` | CNAME to the host |

`_redirects` then 301s **everything** on the short domain to the canonical one.
That is deliberate: the short domain exists only so a QR code encodes at version
3 (29 modules) instead of version 5 (37) — about 22% denser, which is what makes
it scan off a yard sign from a car. It must never serve a second copy of the
site. Two indexed copies is an SEO own-goal and a second thing to keep in sync.

Turn HTTPS on for all four names before the first Payment Link goes live.
Stripe will redirect a paying customer to `/start`, and a certificate warning at
that exact moment is the most expensive one you can serve.

## Going live in the order that de-risks it

**1. Deploy with no Payment Links at all.** Every price renders an *Order by
email* button. The site is fully functional, sells, and cannot break. Do this
first and let it sit for a day.

**2. Create three Stripe Payment Links**, not thirteen:

| SKU | Product | Success URL |
|---|---|---|
| `re-listing-pro` | Listing Pro, $249 one-time | `https://iflythroughit.com/start?sku=re-listing-pro` |
| `veh-walkaround-3` | Walkaround ×3, $117 one-time | `https://iflythroughit.com/start?sku=veh-walkaround-3` |
| `lot-25` | 25 walkarounds a month, $850 **recurring** | `https://iflythroughit.com/start?sku=lot-25` |

These three cover one of each shape — the default property purchase, the
smallest vehicle order, and a subscription — so the first live transaction
exercises every path without thirteen chances to get a redirect wrong. The other
ten keep their email fallback and you lose nothing.

Paste them into `site/config.json` under `payments.links`, rebuild, redeploy.
Full setup detail is in `business/09-store.md`.

**3. Test in Stripe test mode, all the way through** — pay, land on `/start`,
fill the four fields, send the email, watch it arrive. Then once in live mode
for one SKU, then refund it.

## What the build refuses to ship

- **A dead internal link.** Checked across every page, `href` and `src` both.
- **A disclosure page without its originals.** `/o/<slug>/` is the artefact
  Bus. & Prof. Code §10140.8 requires a link to. If the client's unedited
  photographs are not in `samples/<slug>/delivery/originals/`, that page is not
  published and a stale copy is deleted. A page that claims to show unaltered
  originals and shows broken images is not weaker compliance — it is a false
  statement, and it is the first thing anyone checking would open. **The video
  for that job must not be published either until the originals are there.**
- **A price typed into a template.** Every number on the page comes from
  `model/` through `model/export_pricing.py`.

## Currently blocking a full launch

`1420-cedar-ridge` has no originals on disk, so its disclosure page is not
published. The six unedited source photographs need to go in
`samples/1420-cedar-ridge/delivery/originals/` — the genuine originals as the
client sent them, **not frames pulled from the finished video**. Until then the
property film is a demo on the landing page only; it cannot go out as a
delivered listing video.
