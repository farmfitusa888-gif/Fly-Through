#!/usr/bin/env python3
"""Build dist/start/ -- where Stripe sends a customer after they pay.

    python3 site/build_start.py

A checkout that ends on "thanks for your order" is a job that never starts. We
need photos and four facts before anything can be rendered, and the one moment a
customer is guaranteed to be paying attention is the second after they buy. So
the success page is the intake form, not a receipt.

It is static on purpose. Stripe appends ?sku= to the success URL, the page reads
it, and shows the questions for that SKU's vertical. There is no backend to
receive a form POST, so the submit button composes a pre-filled email instead --
which also means the customer's own outbox holds a copy of what they sent, and
their reply-with-photos lands in a normal inbox thread rather than a database
nobody checks.

An unknown or missing sku shows all three paths rather than an error. People
bookmark things, and Stripe redirects can lose a query string.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "config.json").read_text())
PRICING = json.loads((HERE / "pricing.json").read_text())
OUT = HERE / "dist" / "start" / "index.html"

VERTICAL_LABEL = {"rooms": "Property", "vehicles": "Vehicle", "products": "Product"}
# Which shot guide a vertical sends people to. A dealer who just bought an ad cut
# should never land on a page about aerial continuity over a back yard.
GUIDE_PATH = {"rooms": "/shot-guide/property/", "vehicles": "/shot-guide/vehicle/",
              "products": "/shot-guide/product/"}

CSS = """
:root{--ink:#08090B;--ink-2:#101216;--card:#14171C;--paper:#F4F1EC;
  --dim:#9A968D;--faint:#5C5952;--ember:#E0762E;--rule:#20242B}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--paper);
  font:400 17px/1.65 "Instrument Sans",-apple-system,BlinkMacSystemFont,sans-serif}
h1,h2{font-family:"Anton","Impact",sans-serif;font-weight:400;
  text-transform:uppercase;line-height:.98;margin:0 0 14px}
h1{font-size:clamp(2.2rem,7vw,4rem)}
h2{font-size:1.35rem}
.wrap{max-width:720px;margin:0 auto;padding:64px 24px 90px}
.kicker{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.72rem;
  letter-spacing:.22em;text-transform:uppercase;color:var(--ember);margin:0 0 18px}
.lede{font-size:1.1rem;color:var(--dim);margin:0 0 36px}
.card{background:var(--card);border:1px solid var(--rule);border-left:2px solid var(--ember);
  border-radius:0 4px 4px 0;padding:28px 30px;margin:0 0 20px}
ol{margin:0;padding-left:1.15em}
li{margin:0 0 18px;color:var(--dim)}
li strong{color:var(--paper);font-weight:500;display:block;margin-bottom:8px}
input,select,textarea{width:100%;background:var(--ink-2);color:var(--paper);
  border:1px solid var(--rule);border-radius:3px;padding:11px 13px;font:inherit;
  font-size:.95rem}
input:focus,select:focus,textarea:focus{outline:2px solid var(--ember);outline-offset:1px}
.cta{display:inline-flex;align-items:center;gap:10px;background:var(--ember);
  color:#120A04;font-family:"Anton",sans-serif;text-transform:uppercase;
  letter-spacing:.04em;font-size:1rem;padding:15px 28px;border-radius:2px;
  text-decoration:none;border:0;cursor:pointer;transition:transform .16s,background .16s}
.cta:hover{transform:translateY(-2px);background:#EE873F}
.cta:focus-visible{outline:2px solid var(--paper);outline-offset:3px}
.cta[aria-disabled=true]{opacity:.45;pointer-events:none}
.mono{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.8rem;color:var(--faint)}
a{color:var(--ember)}
.pick{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:0 0 30px}
.pick a{display:block;text-align:center;padding:16px 10px;background:var(--card);
  border:1px solid var(--rule);border-radius:4px;text-decoration:none;
  color:var(--paper);font-family:"Anton",sans-serif;text-transform:uppercase}
.pick a:hover{border-color:var(--ember)}
@media(max-width:620px){.pick{grid-template-columns:1fr}}
.note{color:var(--faint);font-size:.9rem;margin-top:26px}
"""


def build() -> Path:
    d, intake = CONFIG, PRICING["intake"]
    skus = {s["id"]: s for s in PRICING["catalog"]}
    payload = json.dumps({
        "skus": {k: {"name": v["name"], "vertical": v["vertical"],
                     "turnaround": v["turnaround"]} for k, v in skus.items()},
        "intake": intake,
        "labels": VERTICAL_LABEL,
        "guides": GUIDE_PATH,
        "email": d["contact_email"],
    })

    html = f"""<title>Start your film</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Anton&family=Instrument+Sans:wght@400;500&family=JetBrains+Mono&display=swap">
<style>{CSS}</style>
<div class="wrap">
  <p class="kicker">{d['domain']}</p>
  <h1 id="head">You're in.<br>Now send the photos.</h1>
  <p class="lede" id="lede">Four answers and a link. That is the whole brief &mdash;
  we do not need a call, and nothing starts until this lands.</p>

  <div id="picker" hidden>
    <p class="mono">Which did you order?</p>
    <div class="pick">
      <a href="?v=rooms">Property</a>
      <a href="?v=vehicles">Vehicle</a>
      <a href="?v=products">Product</a>
    </div>
  </div>

  <form class="card" id="form" hidden>
    <h2 id="what">Your brief</h2>
    <ol id="fields"></ol>
    <button class="cta" type="submit">Send it &rarr;</button>
    <p class="note" id="turn"></p>
  </form>

  <p class="note">Photographing it yourself? The
  <a href="/shot-guide/" id="guide">shot guide</a> covers what to shoot and from
  where &mdash; following it is the difference between a good film and a great one.</p>
  <p class="note mono">Stuck? <a href="mailto:{d['contact_email']}">{d['contact_email']}</a></p>
</div>

<script>
const DATA = {payload};
const q = new URLSearchParams(location.search);
const sku = DATA.skus[q.get("sku")] || null;
const vertical = sku ? sku.vertical : (DATA.intake[q.get("v")] ? q.get("v") : null);

if (!vertical) {{
  document.getElementById("picker").hidden = false;
}} else {{
  const qs = DATA.intake[vertical];
  const form = document.getElementById("form");
  form.hidden = false;
  document.getElementById("what").textContent =
    (sku ? sku.name : DATA.labels[vertical]) + " — your brief";
  if (sku) {{
    document.getElementById("turn").textContent =
      "Delivered in " + sku.turnaround + " from the moment this arrives.";
  }}
  document.getElementById("guide").href = DATA.guides[vertical];
  const ol = document.getElementById("fields");
  qs.forEach((label, i) => {{
    const li = document.createElement("li");
    const s = document.createElement("strong");
    s.textContent = label;
    const input = document.createElement("input");
    input.type = "text";
    input.id = "f" + i;
    input.autocomplete = "off";
    li.append(s, input);
    ol.append(li);
  }});
  form.addEventListener("submit", (e) => {{
    e.preventDefault();
    const lines = qs.map((label, i) =>
      label + "\\n  " + (document.getElementById("f" + i).value || "(not given)"));
    const subject = "Brief — " + (sku ? sku.name : DATA.labels[vertical]);
    const body = lines.join("\\n\\n") + "\\n\\n---\\nSent from " + location.href;
    location.href = "mailto:" + DATA.email +
      "?subject=" + encodeURIComponent(subject) +
      "&body=" + encodeURIComponent(body);
  }});
}}
</script>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    return OUT


if __name__ == "__main__":
    p = build()
    print(f"  built {p}  ({p.stat().st_size / 1024:.0f} KB)")
    print(f"  Stripe success URL: https://{CONFIG['domain']}"
          f"{CONFIG['payments']['success_path']}?sku=<sku-id>")
