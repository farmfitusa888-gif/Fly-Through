#!/usr/bin/env python3
"""Build the whole site, in the one order that produces a correct dist/.

    python3 site/build_all.py

Order matters and used to bite: build_site.py once wrote dist/index.html too, so
running it after build_landing.py silently replaced the sales page with the
disclosure explainer. They own separate paths now, but the sequence is still
real -- the guides must be generated before they can be published, and the
prices must be exported before any page can render a button.

Finishes by walking every internal href in the output. A dead link on a page
that just took someone's money is the most expensive kind.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DIST = HERE / "dist"

STEPS = [
    ("prices + catalogue", [sys.executable, str(ROOT / "model" / "export_pricing.py")]),
    ("property shot guide", [sys.executable, str(ROOT / "docs" / "shot_guide.py")]),
    ("ad shot guides", [sys.executable, str(ROOT / "docs" / "shot_guide_ads.py")]),
    ("landing page", [sys.executable, str(HERE / "build_landing.py")]),
    ("disclosure pages", [sys.executable, str(HERE / "build_site.py")]),
    ("shot guide pages", [sys.executable, str(HERE / "build_guides.py")]),
    ("post-checkout intake", [sys.executable, str(HERE / "build_start.py")]),
]

# src too, not just href: the full-length films are referenced only by <source>,
# and 47 MB of unreferenced video sat in dist/ until this checker learned to look.
HREF = re.compile(r'(?:href|src)="([^"]+)"')
# Anchors into a page we do not resolve here, and schemes that leave the site.
SKIP = ("http://", "https://", "mailto:", "tel:", "#", "data:")


def check_links() -> list[str]:
    """Every internal href must resolve to a file in dist/."""
    bad: list[str] = []
    for page in sorted(DIST.rglob("*.html")):
        for href in HREF.findall(page.read_text()):
            if href.startswith(SKIP):
                continue
            path = href.split("#")[0].split("?")[0]
            if not path:
                continue
            target = DIST / path.lstrip("/") if path.startswith("/") else page.parent / path
            if target.is_dir():
                target = target / "index.html"
            elif target.suffix == "":
                target = Path(str(target).rstrip("/")) / "index.html"
            if not target.exists():
                bad.append(f"{page.relative_to(DIST)} -> {href}")
    return bad


def referenced() -> set[Path]:
    """Every local file any page points at. Used to spot media we ship but never
    link -- dead weight in a bucket, and usually a sign the page meant to show it."""
    hit: set[Path] = set()
    for page in sorted(DIST.rglob("*.html")):
        for href in HREF.findall(page.read_text()):
            if href.startswith(SKIP):
                continue
            path = href.split("#")[0].split("?")[0]
            if not path:
                continue
            t = DIST / path.lstrip("/") if path.startswith("/") else page.parent / path
            hit.add(t.resolve())
    return hit


def deploy_files() -> None:
    """Host config that has to sit next to the HTML, written from site/config.json
    so the domains are never typed twice.

    _headers and _redirects are the Netlify/Cloudflare Pages format. Both hosts
    read them from the publish root; other buckets ignore them harmlessly.
    """
    import json as _json
    cfg = _json.loads((HERE / "config.json").read_text())
    domain, short = cfg["domain"], cfg["short_domain"]

    (DIST / "_headers").write_text(
        "/*\n"
        "  X-Content-Type-Options: nosniff\n"
        "  Referrer-Policy: strict-origin-when-cross-origin\n"
        # The disclosure pages are the artefact AB 723 asks for. They must not be
        # framed by a third party and presented as something else.
        "  X-Frame-Options: SAMEORIGIN\n"
        "  Permissions-Policy: geolocation=(), microphone=(), camera=()\n"
        "\n"
        "/o/*\n"
        # Originals must stay fetchable and must not be cached so long that a
        # corrected upload keeps serving the old file to a regulator.
        "  Cache-Control: public, max-age=300\n"
        "\n"
        "/*.mp4\n"
        "  Cache-Control: public, max-age=31536000, immutable\n")

    # The short domain exists only for QR codes and texted links. It must land on
    # the same page, not serve a second copy -- two indexed copies of the same
    # site is an SEO own-goal and a second thing to keep in sync.
    (DIST / "_redirects").write_text(
        f"https://{short}/*  https://{domain}/:splat  301!\n"
        f"https://www.{short}/*  https://{domain}/:splat  301!\n"
        f"https://www.{domain}/*  https://{domain}/:splat  301!\n"
        "/shot-guide  /shot-guide/  301\n"
        "/start/*  /start/index.html  200\n")

    (DIST / "robots.txt").write_text(
        "User-agent: *\n"
        "Allow: /\n"
        # The post-checkout page is per-order and useless in an index.
        "Disallow: /start\n"
        f"Sitemap: https://{domain}/sitemap.xml\n")

    pages = []
    for f in sorted(DIST.rglob("index.html")):
        rel = f.relative_to(DIST).parent.as_posix()
        path = "/" if rel == "." else f"/{rel}/"
        if path.startswith("/start"):
            continue
        pages.append(path)
    urls = "\n".join(
        f"  <url><loc>https://{domain}{p}</loc></url>" for p in pages)
    (DIST / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n</urlset>\n")

    (DIST / "404.html").write_text(
        "<title>Not found</title>\n"
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        "<style>body{margin:0;background:#08090B;color:#F4F1EC;font:400 17px/1.6 "
        "-apple-system,BlinkMacSystemFont,sans-serif;display:grid;place-items:center;"
        "min-height:100vh;text-align:center}a{color:#E0762E}</style>\n"
        "<div><h1>Nothing here.</h1>"
        '<p><a href="/">Back to the front page</a></p></div>\n')
    print(f"  host config (_headers, _redirects, robots, sitemap: {len(pages)} urls, 404)")


def main() -> int:
    for label, cmd in STEPS:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  FAILED: {label}\n{r.stdout}{r.stderr}", file=sys.stderr)
            return r.returncode
        print(f"  {label}")

    deploy_files()
    bad = check_links()
    print()
    if bad:
        print(f"  {len(bad)} DEAD LINK(S):", file=sys.stderr)
        for b in bad:
            print(f"    {b}", file=sys.stderr)
        return 1
    linked = referenced()
    orphans = [f.relative_to(DIST) for f in DIST.rglob("*")
               if f.is_file() and f.suffix.lower() in {".mp4", ".jpg", ".png", ".webp"}
               and f.resolve() not in linked]
    if orphans:
        mb = sum((DIST / o).stat().st_size for o in orphans) / 1_048_576
        print(f"  note: {len(orphans)} unreferenced media file(s), {mb:.1f} MB")
        for o in orphans[:6]:
            print(f"    {o}")

    pages = sum(1 for _ in DIST.rglob("*.html"))
    size = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"  {pages} pages, {size / 1_048_576:.1f} MB, no dead links")
    print(f"  deploy: upload {DIST}/ to Netlify, Cloudflare Pages or any bucket")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
