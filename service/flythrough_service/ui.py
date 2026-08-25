"""HTML for the service, in the same visual language as the marketing site.

Hand-written rather than templated, exactly like site/build_landing.py. A
template engine earns its place when non-developers edit the markup; here the
same person writes both, and one fewer indirection means one fewer place for an
unescaped value to slip through.

EVERYTHING interpolated goes through esc(). Customer-supplied text -- an
address, a VIN, a filename -- reaches these pages, and a property address
containing a script tag must render as an address.
"""

from __future__ import annotations

import html
from typing import Iterable

BRAND_CSS = """
:root{--ink:#08090B;--ink-2:#101216;--card:#14171C;--paper:#F4F1EC;
  --dim:#9A968D;--faint:#5C5952;--ember:#E0762E;--rule:#20242B;
  --good:#4E9A5E;--bad:#C4553D}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--paper);
  font:400 17px/1.65 "Instrument Sans",-apple-system,BlinkMacSystemFont,sans-serif}
h1,h2,h3{font-family:"Anton","Impact",sans-serif;font-weight:400;
  text-transform:uppercase;line-height:1;letter-spacing:.005em;margin:0 0 16px}
h1{font-size:clamp(2rem,6vw,3.2rem)}
h2{font-size:1.5rem;margin-top:44px;padding-top:26px;border-top:1px solid var(--rule)}
h2:first-of-type{margin-top:20px;border-top:0;padding-top:0}
h3{font-size:1.15rem}
h2 + .note{margin:-8px 0 14px}
.wrap{max-width:860px;margin:0 auto;padding:40px 24px 90px}
.narrow{max-width:620px}
a{color:var(--ember)}
.mono{font-family:"JetBrains Mono",ui-monospace,Menlo,monospace}
.kicker{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.7rem;
  letter-spacing:.22em;text-transform:uppercase;color:var(--ember);margin:0 0 16px}
.lede{font-size:1.08rem;color:var(--dim);margin:0 0 30px}
nav{border-bottom:1px solid var(--rule);background:var(--ink-2)}
nav .wrap{padding:16px 24px;display:flex;gap:22px;align-items:center}
nav a{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.74rem;
  letter-spacing:.16em;text-transform:uppercase;text-decoration:none;color:var(--dim)}
nav a:hover,nav a[aria-current]{color:var(--ember)}
nav .brand{font-family:"Anton",sans-serif;font-size:1.1rem;color:var(--paper);
  text-transform:uppercase;letter-spacing:.02em;margin-right:auto}
.card{background:var(--card);border:1px solid var(--rule);border-left:2px solid var(--ember);
  border-radius:0 4px 4px 0;padding:24px 26px;margin:0 0 18px}
.card.plain{border-left-color:var(--rule)}
.card h3{margin-bottom:10px}
.card p{color:var(--dim);margin:0 0 10px}.card p:last-child{margin:0}
label{display:block;font-size:.9rem;color:var(--paper);margin:0 0 8px;font-weight:500}
input,select,textarea{width:100%;background:var(--ink-2);color:var(--paper);
  border:1px solid var(--rule);border-radius:3px;padding:11px 13px;font:inherit;
  font-size:.95rem;margin:0 0 18px}
input:focus,select:focus,textarea:focus{outline:2px solid var(--ember);outline-offset:1px}
input[type=file]{padding:9px}
button,.btn{display:inline-flex;align-items:center;gap:9px;background:var(--ember);
  color:#120A04;font-family:"Anton",sans-serif;text-transform:uppercase;
  letter-spacing:.04em;font-size:.95rem;padding:13px 24px;border-radius:2px;
  text-decoration:none;border:0;cursor:pointer;transition:transform .16s,background .16s}
button:hover,.btn:hover{transform:translateY(-1px);background:#EE873F}
button:focus-visible,.btn:focus-visible{outline:2px solid var(--paper);outline-offset:3px}
.btn.ghost{background:none;color:var(--paper);border:1px solid var(--faint)}
.btn.ghost:hover{background:rgba(255,255,255,.06)}
.flash{border-radius:3px;padding:13px 16px;margin:0 0 20px;font-size:.94rem}
.flash.err{background:#2A1512;border:1px solid var(--bad);color:#F0C4B9}
.flash.ok{background:#12210F;border:1px solid var(--good);color:#CBE6CF}
table{width:100%;border-collapse:collapse;margin:0 0 18px}
th{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.66rem;
  letter-spacing:.16em;text-transform:uppercase;color:var(--dim);text-align:left;
  padding:11px 14px;background:var(--ink-2);border-bottom:1px solid var(--rule);font-weight:400}
td{padding:12px 14px;border-bottom:1px solid var(--rule);color:var(--dim);font-size:.93rem}
td.k{color:var(--paper)}
.pill{display:inline-block;font-family:"JetBrains Mono",ui-monospace,monospace;
  font-size:.62rem;letter-spacing:.12em;text-transform:uppercase;padding:4px 9px;
  border-radius:2px;border:1px solid var(--rule);color:var(--dim)}
.pill.delivered{border-color:var(--good);color:#9AD2A6}
.pill.failed,.pill.refunded{border-color:var(--bad);color:#E8AB9C}
.pill.paid,.pill.rendering{border-color:var(--ember);color:var(--ember)}
.big{font-family:"Anton",sans-serif;font-size:2.4rem;color:var(--ember);
  font-variant-numeric:tabular-nums;line-height:1}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin:0 0 24px}
.stat{background:var(--ink-2);border:1px solid var(--rule);border-radius:4px;padding:20px 22px}
.stat .l{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.64rem;
  letter-spacing:.14em;text-transform:uppercase;color:var(--dim);margin-top:8px}
.note{color:var(--faint);font-size:.88rem}
ul.plain{list-style:none;padding:0;margin:0 0 18px}
ul.plain li{padding:9px 0;border-bottom:1px solid var(--rule);color:var(--dim);
  display:flex;justify-content:space-between;gap:14px;font-size:.93rem}
ul.plain li:last-child{border-bottom:0}
footer{border-top:1px solid var(--rule);margin-top:50px;padding-top:20px;
  color:var(--faint);font-size:.84rem}
@media(max-width:620px){nav .wrap{gap:14px;flex-wrap:wrap}}
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Anton&family=Instrument+Sans:wght@400;500&family=JetBrains+Mono'
         '&display=swap">')


def esc(v) -> str:
    """Escape everything, including quotes, so a value is safe in an attribute
    as well as in text."""
    return html.escape("" if v is None else str(v), quote=True)


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def page(title: str, body: str, *, brand: str, nav_links: Iterable[tuple[str, str]] = (),
         here: str = "", narrow: bool = False) -> str:
    current = ' aria-current="page"'
    links = "".join(
        f'<a href="{esc(href)}"{current if href == here else ""}>{esc(label)}</a>'
        for label, href in nav_links)
    cls = "wrap narrow" if narrow else "wrap"
    return (
        f"<!doctype html><html lang=\"en\"><head>"
        f"<meta charset=\"utf-8\">"
        f"<title>{esc(title)} — {esc(brand)}</title>"
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="robots" content="noindex">'
        f"{FONTS}<style>{BRAND_CSS}</style></head><body>"
        f'<nav><div class="wrap"><a class="brand" href="/">{esc(brand)}</a>{links}</div></nav>'
        f'<div class="{cls}">{body}'
        f'<footer>{esc(brand)} · every shot begins and ends on a real photograph</footer>'
        f"</div></body></html>")


def flash(message: str, kind: str = "err") -> str:
    return f'<div class="flash {esc(kind)}">{esc(message)}</div>' if message else ""


def status_pill(status: str) -> str:
    label = {"awaiting_payment": "awaiting payment"}.get(status, status)
    return f'<span class="pill {esc(status)}">{esc(label)}</span>'
