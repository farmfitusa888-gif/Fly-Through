#!/usr/bin/env python3
"""Pack the built site into one self-contained file you can open anywhere.

    python3 site/build_artifact.py [out.html]

dist/ is fifteen files that only work when something is serving them. This
folds every one into a single page with a working navigator, so the site can be
looked at on a phone, sent to somebody, or published as an artifact -- without
a bucket, a host or a domain.

The pages are not re-rendered here. Each is dropped in exactly as
`build_all.py` produced it and shown inside an iframe, which is the only
embedding that keeps five different stylesheets from bleeding into each other.
What you are looking at is the real output, not a mock-up of it -- which is the
entire point of building this rather than describing it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"

# Route, label, and the group it sits under. Written out rather than walked so
# the order is the reading order -- a directory listing would put /o/ first and
# the landing page ninth.
PAGES: list[tuple[str, str, str]] = [
    ("/", "Landing page", "The site"),
    ("/start/", "After checkout", "The site"),
    ("/shot-guide/", "Shot guides", "What clients get"),
    ("/shot-guide/property/", "Property", "What clients get"),
    ("/shot-guide/vehicle/", "Vehicle", "What clients get"),
    ("/shot-guide/product/", "Product", "What clients get"),
    ("/writing/", "Index", "Writing"),
    ("/writing/ab-723-what-it-actually-requires/", "AB 723", "Writing"),
    ("/writing/questions-to-ask-an-ai-listing-video-vendor/",
     "Vendor questions", "Writing"),
    ("/writing/what-a-249-dollar-listing-video-costs-to-make/",
     "What it costs", "Writing"),
    ("/o/", "Disclosure index", "Compliance"),
    ("/terms/", "Terms", "Compliance"),
    ("/privacy/", "Privacy", "Compliance"),
    ("/refunds/", "Refunds", "Compliance"),
]

# The full-length films are 47 MB and are downloads, not page content. A viewer
# reading this file has no server to fetch them from, and a dead link is worse
# than an honest absence.
FILMS = re.compile(
    r'<span><a href="media/[^"]*">Full film 16:9</a>[^<]*'
    r'<a href="media/[^"]*">9:16</a></span>')


def read(route: str) -> str:
    p = DIST / ("index.html" if route == "/" else route.strip("/") + "/index.html")
    if not p.is_file():
        raise FileNotFoundError(
            f"{route} is in PAGES but not in dist/. Run site/build_all.py first.")
    html = p.read_text()
    html = FILMS.sub(
        '<span>Full film plays above &mdash; the 16:9 and 9:16 downloads '
        'are on the live site</span>', html)
    return html


def build(out: Path) -> Path:
    pages = {route: read(route) for route, _, _ in PAGES}
    # A page built into dist/ and left out of PAGES would be silently invisible
    # here, which is the failure mode of every hand-maintained index.
    built = {"/"} | {f"/{p.parent.relative_to(DIST).as_posix()}/"
                     for p in DIST.rglob("index.html") if p.parent != DIST}
    unlisted = sorted(built - set(pages))
    if unlisted:
        raise SystemExit(f"dist/ has pages PAGES does not list: {unlisted}")

    nav, seen = [], None
    for route, label, group in PAGES:
        if group != seen:
            nav.append(f'<p class="grp">{group}</p>')
            seen = group
        nav.append(f'<button class="nav" data-route="{route}">'
                   f'<span class="lbl">{label}</span>'
                   f'<span class="rt">{route}</span></button>')

    # JSON in a script tag needs exactly one escape to be safe, and it is the
    # one everybody forgets.
    blob = json.dumps(pages).replace("</", "<\\/")
    page = TEMPLATE.replace("__NAV__", "".join(nav)).replace("__PAGES__", blob)
    out.write_text(page)
    return out


TEMPLATE = r"""<title>iFlyThroughIt.com</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Anton&family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
/* The site commits to one dark world and has since the first build. The
   navigator borrows its tokens rather than inventing a second identity to
   frame the first one in. */
:root{
  --ink:#08090B; --ink-2:#101216; --card:#14171C;
  --paper:#F4F1EC; --dim:#9A968D; --faint:#5C5952;
  --ember:#E0762E; --ember-dim:#8A4A21; --rule:#20242B;
  --rail:248px;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--paper);
  font-family:"Instrument Sans",system-ui,-apple-system,sans-serif;
  height:100vh;display:grid;grid-template-columns:var(--rail) 1fr;
  /* The shell owns the viewport; the nav and the frame own their own scroll.
     Without this the mobile nav's horizontal scroller widens the body instead
     of scrolling inside itself, and the whole page slides sideways. */
  overflow:hidden}
aside{background:var(--ink-2);border-right:1px solid var(--rule);
  display:flex;flex-direction:column;min-height:0;min-width:0}
.head{padding:20px 18px 16px;border-bottom:1px solid var(--rule)}
.mark{font-family:"Anton",Impact,sans-serif;font-size:1.15rem;letter-spacing:.03em;
  margin:0 0 6px;text-transform:uppercase}
.sub{margin:0;color:var(--faint);font-size:.76rem;line-height:1.5}
nav{overflow-y:auto;padding:12px 10px 20px;flex:1;min-height:0;min-width:0}
.grp{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.6rem;
  letter-spacing:.16em;text-transform:uppercase;color:var(--faint);
  margin:16px 0 6px;padding:0 8px}
.grp:first-child{margin-top:2px}
button.nav{display:block;width:100%;text-align:left;background:none;
  border:0;border-left:2px solid transparent;border-radius:0;cursor:pointer;
  padding:7px 8px 7px 12px;color:var(--dim);font:inherit;font-size:.88rem}
button.nav:hover{color:var(--paper);background:var(--card)}
button.nav:focus-visible{outline:2px solid var(--ember);outline-offset:-2px}
button.nav[aria-current="true"]{color:var(--paper);background:var(--card);
  border-left-color:var(--ember)}
.lbl{display:block}
.rt{display:block;font-family:"JetBrains Mono",ui-monospace,monospace;
  font-size:.62rem;color:var(--faint);margin-top:2px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
button.nav[aria-current="true"] .rt{color:var(--ember-dim)}
.foot{padding:12px 18px 16px;border-top:1px solid var(--rule);
  color:var(--faint);font-size:.7rem;line-height:1.55}
main{min-width:0;min-height:0;display:flex;flex-direction:column}
.bar{display:flex;align-items:center;gap:12px;padding:0 14px;height:38px;
  border-bottom:1px solid var(--rule);background:var(--ink-2)}
.url{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.72rem;
  color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.back{background:none;border:1px solid var(--rule);color:var(--dim);
  font:inherit;font-size:.7rem;padding:3px 9px;border-radius:2px;cursor:pointer}
.back:hover{color:var(--paper);border-color:var(--ember-dim)}
.back:disabled{opacity:.35;cursor:default}
iframe{flex:1;width:100%;border:0;background:var(--ink);min-height:0}
@media (max-width:760px){
  body{grid-template-columns:1fr;grid-template-rows:auto 1fr}
  aside{border-right:0;border-bottom:1px solid var(--rule)}
  .head{padding:12px 16px 8px}
  .sub{display:none}
  nav{display:flex;gap:6px;overflow-x:auto;overflow-y:hidden;padding:10px}
  .grp{display:none}
  button.nav{width:auto;flex:0 0 auto;border-left:0;border-bottom:2px solid transparent;
    padding:6px 10px;white-space:nowrap}
  button.nav[aria-current="true"]{border-left:0;border-bottom-color:var(--ember)}
  .rt{display:none}
  .foot{display:none}
}
</style>

<aside>
  <div class="head">
    <p class="mark">FlyThrough</p>
    <p class="sub">The built site, all fifteen pages, in one file. Every
      page is the real output of <code>site/build_all.py</code>.</p>
  </div>
  <nav>__NAV__</nav>
  <div class="foot">Prices come from <code>model/</code> at build time &mdash;
    a test fails if a figure is typed into a page.</div>
</aside>

<main>
  <div class="bar">
    <button class="back" id="back" disabled>&larr; Back</button>
    <span class="url" id="url">/</span>
  </div>
  <!-- allow-same-origin is required, not incidental: without it the frame is
       opaque to the navigator, contentDocument comes back null, and every link
       inside the site silently does nothing. The content is this project's own
       build output, not third-party HTML. -->
  <iframe id="view" title="FlyThrough site"
          sandbox="allow-scripts allow-same-origin"></iframe>
</main>

<script type="application/json" id="pages">__PAGES__</script>
<script>
(function(){
  var pages = JSON.parse(document.getElementById("pages").textContent);
  var view = document.getElementById("view");
  var url = document.getElementById("url");
  var back = document.getElementById("back");
  var stack = [];

  function show(route, push){
    if(!pages[route]) return false;
    if(push && stack[stack.length-1] !== route) stack.push(route);
    view.srcdoc = pages[route];
    url.textContent = route;
    back.disabled = stack.length < 2;
    document.querySelectorAll("button.nav").forEach(function(b){
      b.setAttribute("aria-current", String(b.dataset.route === route));
    });
    try { localStorage.setItem("ft-route", route); } catch(e){}
    return true;
  }

  document.querySelectorAll("button.nav").forEach(function(b){
    b.addEventListener("click", function(){ show(b.dataset.route, true); });
  });
  back.addEventListener("click", function(){
    stack.pop(); show(stack[stack.length-1], false);
  });

  // Links inside the page are real site links. Catching them in the frame is
  // what makes this a site rather than fifteen screenshots -- and a route we
  // did not pack has to say so out loud, not fail silently.
  view.addEventListener("load", function(){
    var doc = view.contentDocument;
    if(!doc) return;
    doc.querySelectorAll('a[href^="/"]').forEach(function(a){
      a.addEventListener("click", function(e){
        e.preventDefault();
        var to = a.getAttribute("href");
        if(!show(to, true)) url.textContent = to + "  (not packed)";
      });
    });
  });

  var start = "/";
  try { start = localStorage.getItem("ft-route") || "/"; } catch(e){}
  if(!pages[start]) start = "/";
  show(start, true);
})();
</script>
"""


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "dist-single.html"
    p = build(out)
    print(f"  {p}  {p.stat().st_size/1e6:.1f} MB  ({len(PAGES)} pages)")
