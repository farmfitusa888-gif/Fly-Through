#!/usr/bin/env python3
"""Publish the articles in site/articles/ as pages.

    python3 site/build_articles.py

Produces dist/writing/ and dist/writing/<slug>/.

Why this exists at all: the compliance position is the one thing a competitor
cannot ship in a weekend, and an article explaining the rule honestly -- including
the parts that do NOT apply -- is the only marketing this business can do that a
reader will thank it for. It is also, incidentally, what people search for.

The credibility IS the marketing, which is why these are written to be useful to
someone who never buys anything, and why every one of them carries the
not-legal-advice line where a reader will actually see it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "config.json").read_text())
SRC = HERE / "articles"
DIST = HERE / "dist" / "writing"

CSS = """
:root{--ink:#08090B;--ink-2:#101216;--paper:#F4F1EC;--dim:#9A968D;
  --faint:#5C5952;--ember:#E0762E;--rule:#20242B}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--paper);
  font:400 18px/1.75 "Instrument Sans",-apple-system,BlinkMacSystemFont,sans-serif}
.wrap{max-width:680px;margin:0 auto;padding:52px 24px 110px}
h1{font-family:"Anton","Impact",sans-serif;font-weight:400;text-transform:uppercase;
  font-size:clamp(2rem,6vw,3rem);line-height:1.02;margin:0 0 14px;text-wrap:balance}
h2{font-family:"Anton","Impact",sans-serif;font-weight:400;text-transform:uppercase;
  font-size:1.3rem;margin:46px 0 14px;padding-top:24px;border-top:1px solid var(--rule)}
p,li{color:var(--dim)}
strong{color:var(--paper);font-weight:500}
a{color:var(--ember)}
blockquote{margin:24px 0;padding:16px 22px;background:var(--ink-2);
  border-left:2px solid var(--ember);border-radius:0 4px 4px 0;color:var(--paper);
  font-size:.98rem}
blockquote p{color:var(--paper);margin:0}
hr{border:0;border-top:1px solid var(--rule);margin:44px 0}
ol,ul{padding-left:1.2em}
li{margin-bottom:10px}
.meta{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.72rem;
  letter-spacing:.16em;text-transform:uppercase;color:var(--faint);margin:0 0 40px}
.back{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.72rem;
  letter-spacing:.16em;text-transform:uppercase;color:var(--ember);
  text-decoration:none;display:inline-block;margin-bottom:28px}
.card{display:block;background:var(--ink-2);border:1px solid var(--rule);
  border-left:2px solid var(--ember);border-radius:0 4px 4px 0;padding:26px 28px;
  margin:0 0 16px;text-decoration:none}
.card:hover{background:#141920}
.card h2{font-size:1.35rem;margin:0 0 8px;border:0;padding:0;color:var(--paper)}
.card p{margin:0;font-size:.95rem}
.cta{display:block;margin-top:52px;padding-top:26px;border-top:1px solid var(--rule);
  color:var(--faint);font-size:.94rem}
footer{margin-top:56px;padding-top:20px;border-top:1px solid var(--rule);
  font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.74rem;color:var(--faint)}
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Anton&family=Instrument+Sans:wght@400;500&family=JetBrains+Mono'
         '&display=swap">')


def parse(path: Path) -> dict:
    raw = path.read_text()
    if "\n---\n" not in raw:
        raise ValueError(f"{path.name}: no front matter (expected a --- line)")
    head, body = raw.split("\n---\n", 1)
    meta = {}
    for line in head.strip().splitlines():
        if ":" not in line:
            raise ValueError(f"{path.name}: bad front-matter line {line!r}")
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip()
    for required in ("title", "slug", "description", "updated"):
        if required not in meta:
            raise ValueError(f"{path.name}: front matter is missing {required!r}")
    meta["body"] = body
    return meta


def shell(title: str, description: str, body: str, *, canonical: str) -> str:
    d = CONFIG
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<title>{title} — {d["brand"]}</title>'
            f'<meta name="description" content="{description}">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<link rel="canonical" href="{canonical}">'
            f'{FONTS}<style>{CSS}</style></head><body><div class="wrap">'
            f'{body}'
            f'<footer><a href="/">{d["brand"]}</a> · '
            f'<a href="/writing/">More writing</a> · '
            f'<a href="mailto:{d["contact_email"]}">{d["contact_email"]}</a>'
            f'</footer></div></body></html>')


def main() -> int:
    try:
        import markdown
    except ImportError:
        print("needs the `markdown` package:  pip install markdown",
              file=sys.stderr)
        return 2
    md = markdown.Markdown(extensions=["tables", "attr_list"])
    base = f"https://{CONFIG['domain']}"

    articles = []
    for path in sorted(SRC.glob("*.md")):
        meta = parse(path)
        md.reset()
        html = md.convert(meta["body"])
        out = DIST / meta["slug"] / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        page = (
            f'<a class="back" href="/writing/">&larr; Writing</a>'
            f'<h1>{meta["title"]}</h1>'
            f'<p class="meta">Updated {meta["updated"]}'
            + (f' · {meta["reading"]}' if "reading" in meta else "") + '</p>'
            f'{html}'
            f'<div class="cta">We make drone-style video from photographs an '
            f'agent already has, and every delivery carries the disclosure pack '
            f'described above &mdash; because we had to build it for ourselves '
            f'first. <a href="/">How it works</a>.</div>')
        out.write_text(shell(meta["title"], meta["description"], page,
                             canonical=f"{base}/writing/{meta['slug']}/"))
        articles.append(meta)
        print(f"  built /writing/{meta['slug']}/")

    cards = "".join(
        f'<a class="card" href="/writing/{a["slug"]}/">'
        f'<h2>{a["title"]}</h2><p>{a["description"]}</p></a>' for a in articles)
    index = (f'<a class="back" href="/">&larr; {CONFIG["domain"]}</a>'
             f'<h1>Writing</h1>'
             f'<p class="meta">On disclosure, and on making video from '
             f'photographs</p>{cards}')
    (DIST / "index.html").write_text(
        shell("Writing", "Notes on real-estate media disclosure and anchored "
                         "AI video.", index, canonical=f"{base}/writing/"))
    print(f"  built /writing/  ({len(articles)} article"
          f"{'s' if len(articles) != 1 else ''})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
