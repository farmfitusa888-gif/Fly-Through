#!/usr/bin/env python3
"""Build the legal pages.

    python3 site/build_legal.py

Produces dist/terms/, dist/privacy/, dist/refunds/.

Stripe asks for a terms URL when you create a Payment Link, and "we'll write
that later" becomes a placeholder on a live checkout. These are real, specific
to how this business actually works, and generated from site/config.json so a
domain or an address is never typed twice.

NOT LEGAL ADVICE, and the pages say so where a reader will see it. They are a
solid draft for a lawyer to review, not a substitute for one -- the compliance
claims elsewhere on this site are the reason to get that review done properly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "config.json").read_text())
PRICING = json.loads((HERE / "pricing.json").read_text())
DIST = HERE / "dist"

CSS = """
:root{--ink:#08090B;--ink-2:#101216;--paper:#F4F1EC;--dim:#9A968D;
  --faint:#5C5952;--ember:#E0762E;--rule:#20242B}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--paper);
  font:400 17px/1.72 "Instrument Sans",-apple-system,BlinkMacSystemFont,sans-serif}
.wrap{max-width:720px;margin:0 auto;padding:56px 24px 100px}
h1{font-family:"Anton","Impact",sans-serif;font-weight:400;text-transform:uppercase;
  font-size:clamp(2rem,6vw,3rem);line-height:1;margin:0 0 10px}
h2{font-family:"Anton","Impact",sans-serif;font-weight:400;text-transform:uppercase;
  font-size:1.25rem;margin:44px 0 12px;padding-top:22px;border-top:1px solid var(--rule)}
p,li{color:var(--dim)}
strong{color:var(--paper);font-weight:500}
a{color:var(--ember)}
.updated{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.72rem;
  letter-spacing:.16em;text-transform:uppercase;color:var(--faint);margin:0 0 36px}
.note{border:1px solid var(--rule);background:var(--ink-2);border-left:2px solid var(--ember);
  border-radius:0 4px 4px 0;padding:18px 22px;margin:26px 0;font-size:.94rem}
.back{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.72rem;
  letter-spacing:.16em;text-transform:uppercase;color:var(--ember);
  text-decoration:none;display:inline-block;margin-bottom:26px}
footer{margin-top:56px;padding-top:20px;border-top:1px solid var(--rule);
  font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.74rem;color:var(--faint)}
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Anton&family=Instrument+Sans:wght@400;500&family=JetBrains+Mono'
         '&display=swap">')

UPDATED = "25 August 2026"


def page(title: str, body: str) -> str:
    d = CONFIG
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<title>{title} — {d["brand"]}</title>'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'{FONTS}<style>{CSS}</style></head><body><div class="wrap">'
            f'<a class="back" href="/">&larr; {d["domain"]}</a>'
            f'<h1>{title}</h1><p class="updated">Last updated {UPDATED}</p>'
            f'{body}'
            f'<footer>{d["brand"]} · '
            f'<a href="mailto:{d["contact_email"]}">{d["contact_email"]}</a> · '
            f'<a href="/terms/">Terms</a> · <a href="/privacy/">Privacy</a> · '
            f'<a href="/refunds/">Refunds</a></footer></div></body></html>')


DISCLAIMER = ('<div class="note"><strong>This is not legal advice.</strong> '
              'These terms are written to describe honestly how this service '
              'actually works, and they should be reviewed by a lawyer in your '
              'jurisdiction before you rely on them.</div>')


def terms() -> str:
    d = CONFIG
    return page("Terms of service", f"""
<p>These terms cover your use of {d['brand']} at {d['domain']} and {d['short_domain']}.
By placing an order you agree to them.</p>
{DISCLAIMER}

<h2>What we do</h2>
<p>You send us photographs. We generate camera movement between them and return
a video. <strong>Every shot begins and ends on a photograph you supplied</strong>
— the AI generates only the travel between two real frames. It is never asked
what your property, vehicle or product looks like.</p>

<h2>What we never do</h2>
<ul>
<li><strong>We do not retouch, stage, crop or colour-correct your photographs.</strong>
Not a limitation — the moment we edit an image, the originals page we host stops
containing originals, and the disclosure position collapses for both of us.</li>
<li><strong>We do not add, remove or alter anything in the frame.</strong> No
furniture, no sky replacement, no removing a car from a driveway.</li>
<li><strong>We do not produce testimonials, reviews or endorsements</strong>, and
we will not accept an order for one. The FTC Rule on Consumer Reviews and
Testimonials prohibits AI-generated testimonials regardless of disclosure.</li>
</ul>

<h2>Your photographs, and your right to send them</h2>
<p>You keep ownership of everything you send. By uploading you confirm that you
own the images or have the right to use them for advertising — most commonly
that means your photographer has assigned you those rights, which is not
automatic and is worth checking before your first order.</p>
<p>You grant us only the licence needed to do the work: to store your files, to
produce the video, and to host your unaltered originals at the disclosure link
that accompanies a real-estate delivery. We will not use your images to promote
{d['brand']} without asking you first, in writing, per job.</p>

<h2>What you get</h2>
<p>On delivery you own the finished video outright and may use it however you
like, indefinitely. There is no per-view, per-platform or per-year licence.</p>

<h2>Disclosure obligations</h2>
<p>Video we produce is generated imagery, and advertising it carries duties that
are <strong>yours</strong> as the advertiser. We supply the tools to meet them —
an on-screen mark, a hosted page carrying your unaltered originals, a QR code
and ready-to-paste caption text — and for real-estate work the disclosure is not
optional and cannot be removed from the delivery.</p>
<p>You remain responsible for what you publish and where. Rules vary by MLS,
platform and state; have your broker's counsel review the disclosure text before
your first listing goes out.</p>

<h2>Turnaround</h2>
<p>The turnaround shown on each item starts when your photographs and brief are
both complete, not when you pay. We check the set before charging you, so an
incomplete order is told so rather than silently queued.</p>

<h2>If something goes wrong</h2>
<p>See <a href="/refunds/">Refunds</a>. Short version: refund on request until
the film is delivered; after delivery, a free re-cut.</p>

<h2>Limits</h2>
<p>We are liable to you for no more than what you paid for the order in
question. We are not liable for lost sales, lost listings or any indirect loss.
Nothing here limits liability that cannot lawfully be limited.</p>

<h2>Ending it</h2>
<p>Subscriptions can be cancelled at any time and run to the end of the period
already paid for. We may decline or refund any order — most likely because the
photographs cannot make a film, or because the request is one of the things
under <em>What we never do</em>.</p>

<h2>Contact</h2>
<p><a href="mailto:{d['contact_email']}">{d['contact_email']}</a></p>
""")


def privacy() -> str:
    d = CONFIG
    return page("Privacy", f"""
<p>What {d['brand']} collects, why, and what we do not do with it.</p>
{DISCLAIMER}

<h2>What we hold</h2>
<ul>
<li><strong>Your email address.</strong> It is how you sign in — there is no
password, so there is no password of yours for us to lose.</li>
<li><strong>The photographs you upload</strong>, and the videos made from them.</li>
<li><strong>Your brief</strong> — the property address, VIN or product name you
typed, and the style you chose.</li>
<li><strong>Order and payment records:</strong> what you bought, when, and how
much. We never see or store your card number.</li>
</ul>

<h2>What we do not hold</h2>
<p><strong>Card details.</strong> Payment happens on Stripe's own checkout. Your
card number never touches our servers, which is deliberate: the safest way to
hold a card number is to not have one.</p>
<p><strong>Tracking.</strong> No analytics, no advertising pixels, no
third-party scripts on the pages you use to buy. If you arrived on a partner
link we store which partner referred you, so they get paid.</p>

<h2>Who else sees it</h2>
<p>Stripe, to take payment. Our render provider, which receives the photographs
needed to produce your video. Nobody else — we do not sell, rent or share your
data, and there is no advertising business here to feed.</p>

<h2>Your originals page</h2>
<p>Real-estate deliveries include a public page carrying your unaltered
photographs, because California Business &amp; Professions Code §10140.8 requires
a link to the original image. <strong>That page is public by design</strong> — a
disclosure link nobody can open is not a disclosure. It carries the property
address and the photographs, nothing about you personally.</p>

<h2>How long</h2>
<p>Order records for seven years, because tax and disclosure obligations both
outlast the job. Photographs and videos for as long as your account is open, so
you can re-download. Ask us to delete a job's files and we will, except where a
live listing's disclosure page still needs its originals.</p>

<h2>Your rights</h2>
<p>Ask us for a copy of what we hold about you, ask for corrections, or ask for
deletion — <a href="mailto:{d['contact_email']}">{d['contact_email']}</a>. We do
not charge for this and we do not need a reason.</p>

<h2>Security</h2>
<p>Sign-in links are single use and expire in twenty minutes. Session tokens are
stored hashed, so a stolen backup is not a stack of working logins. Uploaded
originals are stored read-only and are never modified.</p>
""")


def refunds() -> str:
    d = CONFIG
    return page("Refunds", f"""
<p>Written plainly, because a refund policy that needs interpreting is one you
argue about.</p>

<h2>Before delivery</h2>
<p><strong>Full refund on request, no reason needed, no argument.</strong> Email
us before the film lands and the money goes back.</p>

<h2>After delivery</h2>
<p><strong>A free re-cut, rather than a refund.</strong> Tell us what is wrong
and we will make it again — different pacing, different order, different
opening frame, whatever it needs.</p>
<p>This is arithmetic, not generosity. Re-cutting costs us a couple of dollars;
arguing with you costs more than that in an hour, and a chargeback costs more
again. If a re-cut does not fix it, we refund.</p>

<h2>The one thing we will not refund</h2>
<p>A job where we told you before charging that your photographs could not make
a good film, and you asked us to proceed anyway. We check every set before
taking payment specifically so this conversation happens first.</p>

<h2>Subscriptions</h2>
<p>Cancel any time. You keep everything already delivered and the plan runs to
the end of the period you have paid for. We do not pro-rate a part-used month,
and we do not bill you again after you cancel.</p>

<h2>How to ask</h2>
<p>Email <a href="mailto:{d['contact_email']}">{d['contact_email']}</a> with your
order. Refunds go back to the card you paid with, usually within five business
days once we have processed them.</p>
""")


def main() -> int:
    for slug, html in (("terms", terms()), ("privacy", privacy()),
                       ("refunds", refunds())):
        out = DIST / slug / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html)
        print(f"  built /{slug}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
