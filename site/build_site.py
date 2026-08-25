#!/usr/bin/env python3
"""Build the deployable disclosure site.

    python3 site/build_site.py            # build all jobs found
    python3 site/build_site.py --job 1420-cedar-ridge

Produces site/dist/, a static site ready for Netlify, Cloudflare Pages, GitHub
Pages or any bucket:

    dist/o/index.html            the originals hub: what these pages are for
    dist/o/<slug>/index.html     the unaltered-originals page for one job
    dist/o/<slug>/originals/     the client's own photographs, untouched

dist/index.html belongs to build_landing.py and is NOT written here. Both
builders used to write it and this one ran second, so a full build silently
replaced the sales page with the disclosure explainer.

WHY THIS EXISTS

California AB 723 (Bus. & Prof. Code s.10140.8) requires a link to the ORIGINAL
unaltered image, reachable by URL or QR. That is a hosted artefact, not a
sentence. Competitors ship a video and a disclaimer; neither satisfies the link
requirement. This is the thing that does.

The domain lives in site/config.json and nowhere else, so changing it updates
every disclosure URL, QR and caption on the next build.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from flythrough.compliance import make_page, make_qr, CAPTION, CAPTION_SHORT  # noqa: E402

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "config.json").read_text())
DIST = HERE / "dist"

ROOT_CSS = """
:root{--bg:#F6F8FA;--card:#FFF;--ink:#141D26;--ink2:#41505F;--muted:#6E7C8A;
--rule:#DDE3EA;--blue:#21528C;--blue-soft:#E8EFF7}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0E1319;
--card:#161D25;--ink:#E7ECF1;--ink2:#B3BFCB;--muted:#8494A3;--rule:#26303B;
--blue:#7FADE4;--blue-soft:#16233250}}
:root[data-theme=dark]{--bg:#0E1319;--card:#161D25;--ink:#E7ECF1;--ink2:#B3BFCB;
--muted:#8494A3;--rule:#26303B;--blue:#7FADE4;--blue-soft:#16233250}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:400 17px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:680px;margin:0 auto;padding:56px 22px 80px}
h1{font-size:2.1rem;letter-spacing:-.02em;margin:0 0 10px;text-wrap:balance}
.lede{font-size:1.15rem;color:var(--ink2);margin:0 0 34px}
.card{background:var(--card);border:1px solid var(--rule);border-left:3px solid var(--blue);
border-radius:0 10px 10px 0;padding:20px 24px;margin:0 0 22px}
.card h2{font-size:.75rem;letter-spacing:.12em;text-transform:uppercase;
color:var(--blue);margin:0 0 10px}
.card p{margin:0 0 10px;color:var(--ink2);font-size:.98rem}.card p:last-child{margin:0}
a{color:var(--blue)}
footer{margin-top:48px;padding-top:20px;border-top:1px solid var(--rule);
color:var(--muted);font-size:.87rem}
"""


def originals_index(cfg: dict, jobs: list[str]) -> str:
    return f"""<title>{cfg['brand']}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{ROOT_CSS}</style>
<div class="wrap">
  <h1>{cfg['brand']}</h1>
  <p class="lede">{cfg['tagline']}</p>

  <div class="card">
    <h2>What this site is for</h2>
    <p>Every video we produce links here, to the <strong>original, unaltered
    photographs</strong> the video was built from.</p>
    <p>That link is not a courtesy. Under California Business &amp; Professions
    Code &sect;10140.8, a digitally altered image in a real-estate advertisement
    must carry a conspicuous notice <em>and</em> a link to the unaltered original
    by URL or QR code. NAR&rsquo;s Code of Ethics, Article 12, requires the same
    disclosure nationally.</p>
  </div>

  <div class="card">
    <h2>How the video is made</h2>
    <p>Each shot begins and ends on a real photograph of the property. The AI
    generates only the camera travel between two genuine frames &mdash; it is
    never asked what the building looks like.</p>
    <p>We do not retouch, stage or colour-correct anything a client sends. The
    photographs on these pages are the files we received.</p>
  </div>

  <footer><a href="/">{cfg['domain']}</a> &middot; <a href="mailto:{cfg['contact_email']}">{cfg['contact_email']}</a></footer>
</div>
"""


def build_job(cfg: dict, slug: str, listing: str, photos: list[dict],
              src_dir: Path | None) -> Path:
    out = DIST / "o" / slug
    out.mkdir(parents=True, exist_ok=True)
    url = f"https://{cfg['domain']}{cfg['originals_path']}/{slug}"

    if src_dir and src_dir.is_dir():
        dest = out / "originals"
        dest.mkdir(exist_ok=True)
        for p in sorted(src_dir.iterdir()):
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                shutil.copy2(p, dest / p.name)

    make_page(listing, photos, out / "index.html", url=url,
              produced_by=cfg["brand"])
    make_qr(url, out / "qr.png")
    (out / "disclosure.json").write_text(json.dumps({
        "listing": listing, "url": url,
        "caption_mls": CAPTION.format(url=url),
        "caption_social": CAPTION_SHORT.format(url=url),
    }, indent=2))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", help="build only this slug")
    a = ap.parse_args()

    DIST.mkdir(parents=True, exist_ok=True)
    jobs_dir = ROOT / "samples"
    built: list[str] = []
    skipped: list[tuple[str, list[str]]] = []

    for manifest in sorted(jobs_dir.glob("*/assets.json")):
        spec = json.loads(manifest.read_text())
        slug = spec["slug"]
        if a.job and slug != a.job:
            continue
        photos = [{"path": f"{i+1:02d}_{s['room']}.png", "room_key": s["room"]}
                  for i, s in enumerate(spec["stills"])]
        src = manifest.parent / "delivery" / "originals"
        have = ({p.name for p in src.iterdir()
                 if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}}
                if src.is_dir() else set())
        want = {ph["path"] for ph in photos}
        if not want <= have:
            # REFUSE to publish. This page's entire purpose is to be the
            # unaltered original that Bus. & Prof. Code s.10140.8 requires a
            # link to. A page that makes that claim and then shows broken
            # images is not a weaker version of compliance -- it is a false
            # statement, and it is the first thing anyone checking would open.
            skipped.append((slug, sorted(want - have)))
            # Remove any page a previous build left behind. Leaving a stale one
            # is the same false claim, just with an older timestamp.
            stale = DIST / "o" / slug
            if stale.exists():
                shutil.rmtree(stale)
                print(f"  REMOVED stale /o/{slug}/")
            print(f"  SKIPPED /o/{slug}/ -- {len(want - have)} original(s) missing")
            continue
        build_job(CONFIG, slug, spec["listing"], photos, src)
        built.append(slug)
        print(f"  built /o/{slug}/")

    # NOT dist/index.html -- that is the landing page, built by build_landing.py.
    (DIST / "o").mkdir(parents=True, exist_ok=True)
    (DIST / "o" / "index.html").write_text(originals_index(CONFIG, built))
    # _headers is written by build_all.py, which is the only place that knows the
    # whole output tree. Two writers of one host-config file is how a security
    # header silently disappears.
    print(f"  built /o/  (originals hub)")
    print()
    print(f"  domain : {CONFIG['domain']}   (change it in site/config.json only)")
    print(f"  deploy : upload site/dist/ to Netlify, Cloudflare Pages or any bucket")
    if built:
        print(f"  verify : https://{CONFIG['domain']}{CONFIG['originals_path']}/{built[0]}")
    if skipped:
        print()
        print("  NOT PUBLISHED -- these jobs have no originals on disk:")
        for slug, missing in skipped:
            print(f"    {slug}: {', '.join(missing)}")
        print("  Put the client's own unedited photographs in")
        print("    samples/<slug>/delivery/originals/  and re-run.")
        print("  Until then the disclosure link for these jobs does not resolve,")
        print("  so the videos must not be published either.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
