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

HREF = re.compile(r'href="([^"]+)"')
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


def main() -> int:
    for label, cmd in STEPS:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  FAILED: {label}\n{r.stdout}{r.stderr}", file=sys.stderr)
            return r.returncode
        print(f"  {label}")

    bad = check_links()
    print()
    if bad:
        print(f"  {len(bad)} DEAD LINK(S):", file=sys.stderr)
        for b in bad:
            print(f"    {b}", file=sys.stderr)
        return 1
    pages = sum(1 for _ in DIST.rglob("*.html"))
    size = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"  {pages} pages, {size / 1_048_576:.1f} MB, no dead links")
    print(f"  deploy: upload {DIST}/ to Netlify, Cloudflare Pages or any bucket")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
