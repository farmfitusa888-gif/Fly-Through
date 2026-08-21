#!/usr/bin/env python3
"""Publish the shot guides as pages on the site.

    python3 site/build_guides.py

Produces:
    dist/shot-guide/index.html            the three doors
    dist/shot-guide/property/index.html
    dist/shot-guide/vehicle/index.html
    dist/shot-guide/product/index.html

The guides are generated markdown (docs/shot_guide.py, docs/shot_guide_ads.py)
whose rules come from the taxonomies. This only styles them -- it does not add,
reword or reorder a single instruction, because the moment this file starts
editing copy there are two versions of the truth and the printable one is wrong.

The post-checkout page at /start links straight to the right vertical, so a
dealer who just bought an ad cut lands on the vehicle guide and never sees a
paragraph about aerials.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONFIG = json.loads((HERE / "config.json").read_text())
DOCS = ROOT / "docs"
DIST = HERE / "dist" / "shot-guide"

GUIDES = {
    "property": ("shot-guide-agent.md", "Property",
                 "For listing agents. What to send and what to add."),
    "vehicle": ("shot-guide-vehicle.md", "Vehicle",
                "For a lot photographer. One lap, one folder per VIN."),
    "product": ("shot-guide-product.md", "Product",
                "For a brand. One product per folder, one lighting setup."),
}

CSS = """
:root{--ink:#08090B;--ink-2:#101216;--card:#14171C;--paper:#F4F1EC;
  --dim:#9A968D;--faint:#5C5952;--ember:#E0762E;--rule:#20242B}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--paper);
  font:400 17px/1.7 "Instrument Sans",-apple-system,BlinkMacSystemFont,sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:56px 24px 100px}
h1,h2,h3{font-family:"Anton","Impact",sans-serif;font-weight:400;
  text-transform:uppercase;line-height:1;letter-spacing:.005em}
h1{font-size:clamp(2rem,6vw,3.2rem);margin:0 0 28px}
h2{font-size:1.5rem;margin:52px 0 16px;padding-top:22px;border-top:1px solid var(--rule)}
h3{font-size:1.1rem;margin:30px 0 10px}
p,li{color:var(--dim)}
strong{color:var(--paper);font-weight:500}
code{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.86em;
  background:var(--ink-2);border:1px solid var(--rule);border-radius:3px;padding:1px 6px;
  color:var(--ember)}
a{color:var(--ember)}
hr{border:0;border-top:1px solid var(--rule);margin:44px 0}
.tablewrap{overflow-x:auto;margin:22px 0;border:1px solid var(--rule);border-radius:4px}
table{width:100%;border-collapse:collapse;min-width:520px}
th{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.66rem;
  letter-spacing:.16em;text-transform:uppercase;color:var(--dim);text-align:left;
  padding:12px 16px;background:var(--ink-2);border-bottom:1px solid var(--rule);font-weight:400}
td{padding:11px 16px;border-bottom:1px solid var(--rule);font-size:.92rem;color:var(--dim)}
tr:last-child td{border-bottom:0}
td:first-child{color:var(--paper)}
ol li,ul li{margin-bottom:10px}
.back{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.72rem;
  letter-spacing:.16em;text-transform:uppercase;color:var(--ember);
  text-decoration:none;display:inline-block;margin-bottom:26px}
.doors{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:36px}
.door{display:block;background:var(--card);border:1px solid var(--rule);
  border-left:2px solid var(--ember);border-radius:0 4px 4px 0;padding:26px 24px;
  text-decoration:none}
.door:hover{background:var(--ink-2)}
.door h2{font-size:1.4rem;margin:0 0 8px;border:0;padding:0;color:var(--paper)}
.door p{margin:0;font-size:.92rem}
@media(max-width:760px){.doors{grid-template-columns:1fr}}
footer{margin-top:70px;padding-top:22px;border-top:1px solid var(--rule);
  font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.74rem;color:var(--faint)}
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Anton&family=Instrument+Sans:wght@400;500&family=JetBrains+Mono'
         '&display=swap">')


def page(title: str, body: str, *, back: bool = True) -> str:
    d = CONFIG
    nav = '<a class="back" href="/shot-guide/">&larr; All guides</a>' if back else ""
    return (f'<title>{title} — {d["brand"]}</title>\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'{FONTS}\n<style>{CSS}</style>\n'
            f'<div class="wrap">{nav}\n{body}\n'
            f'<footer><a href="/">{d["domain"]}</a> · '
            f'<a href="mailto:{d["contact_email"]}">{d["contact_email"]}</a></footer>'
            f'</div>\n')


def main() -> int:
    try:
        import markdown
    except ImportError:
        print("This build needs the `markdown` package:  pip install markdown",
              file=sys.stderr)
        return 2

    md = markdown.Markdown(extensions=["tables", "attr_list"])
    missing = [f for f, _, _ in GUIDES.values() if not (DOCS / f).is_file()]
    if missing:
        print(f"missing generated guides: {missing}\n"
              "  run: python3 docs/shot_guide.py && python3 docs/shot_guide_ads.py",
              file=sys.stderr)
        return 2

    for slug, (fname, label, _) in GUIDES.items():
        md.reset()
        html = md.convert((DOCS / fname).read_text())
        # Tables must scroll inside their own box, never the page body.
        html = html.replace("<table>", '<div class="tablewrap"><table>')
        html = html.replace("</table>", "</table></div>")
        out = DIST / slug / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(f"{label} shot guide", html))
        print(f"  built /shot-guide/{slug}/")

    doors = "\n".join(
        f'<a class="door" href="/shot-guide/{slug}/"><h2>{label}</h2><p>{blurb}</p></a>'
        for slug, (_, label, blurb) in GUIDES.items())
    (DIST / "index.html").write_text(page(
        "Shot guides",
        "<h1>What to send us</h1>"
        "<p>Every film is built from photographs you already have. These say which "
        "ones, and where the camera should stand for the few you might be missing. "
        "Following them is the difference between a good film and a great one.</p>"
        f'<div class="doors">{doors}</div>', back=False))
    print("  built /shot-guide/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
