#!/usr/bin/env python3
"""Build the FlyThrough landing page as one self-contained file.

    python3 site/build_landing.py

Images are embedded as data URIs so the page is a single file that works from a
bucket, a CDN, or a published artifact with no external requests. The domain and
brand come from site/config.json -- never hardcoded here.
"""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "config.json").read_text())
MEDIA = json.loads((HERE / "media.json").read_text())
PRICING = json.loads((HERE / "pricing.json").read_text())
IMG = Path("/tmp/claude-0/-home-user-Fly-Through/fe243ec4-8c0d-5a0f-b58d-a7344e98d8b6/scratchpad/web")
OUT = HERE / "dist" / "index.html"


def data_uri(name: str) -> str:
    p = IMG / name
    if not p.is_file():
        return ""
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


CSS = """
:root{
  --ink:#08090B; --ink-2:#101216; --card:#14171C;
  --paper:#F4F1EC; --dim:#9A968D; --faint:#5C5952;
  --ember:#E0762E; --ember-dim:#8A4A21;
  --rule:#20242B;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--ink);color:var(--paper);
  font:400 17px/1.65 "Instrument Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased;overflow-x:hidden}
h1,h2,h3,.display{font-family:"Anton","Impact",sans-serif;font-weight:400;
  text-transform:uppercase;letter-spacing:.005em;line-height:.95;text-wrap:balance}
.mono{font-family:"JetBrains Mono",ui-monospace,Menlo,monospace}
.wrap{max-width:1120px;margin:0 auto;padding:0 24px}
.narrow{max-width:720px}
a{color:var(--ember)}

/* ---------- hero ---------- */
.hero{position:relative;min-height:min(94vh,860px);display:flex;align-items:flex-end;
  overflow:hidden;border-bottom:1px solid var(--rule)}
.hero-img{position:absolute;inset:0;background-size:cover;background-position:center;
  transform:scale(1.06);animation:drift 26s ease-in-out infinite alternate}
@keyframes drift{to{transform:scale(1.14) translate3d(-1.5%,-1%,0)}}
.hero::after{content:"";position:absolute;inset:0;
  background:linear-gradient(180deg,rgba(8,9,11,.62) 0%,rgba(8,9,11,.30) 38%,rgba(8,9,11,.97) 100%)}
.hero .wrap{position:relative;z-index:2;padding-bottom:72px;padding-top:120px}
.kicker{font-family:"JetBrains Mono",monospace;font-size:.74rem;letter-spacing:.22em;
  text-transform:uppercase;color:var(--ember);margin:0 0 20px}
h1{font-size:clamp(3rem,10.5vw,8.2rem);margin:0 0 22px}
h1 em{font-style:normal;color:var(--ember);display:block}
h2 em{font-style:normal;color:var(--ember);display:block}
.hero p{font-size:clamp(1.05rem,2.2vw,1.36rem);color:var(--paper);max-width:34ch;
  margin:0 0 34px;opacity:.92}
.cta{display:inline-flex;align-items:center;gap:12px;background:var(--ember);
  color:#120A04;font-family:"Anton",sans-serif;text-transform:uppercase;
  letter-spacing:.04em;font-size:1.02rem;padding:16px 30px;border-radius:2px;
  text-decoration:none;transition:transform .18s,background .18s}
.cta:hover{transform:translateY(-2px);background:#EE873F}
.cta:focus-visible{outline:2px solid var(--paper);outline-offset:3px}
.cta.ghost{background:none;color:var(--paper);border:1px solid var(--faint)}
.cta.ghost:hover{background:rgba(255,255,255,.05)}

/* ---------- sections ---------- */
section{padding:104px 0;border-bottom:1px solid var(--rule)}
.eyebrow{font-family:"JetBrains Mono",monospace;font-size:.72rem;letter-spacing:.22em;
  text-transform:uppercase;color:var(--ember);margin:0 0 18px}
h2{font-size:clamp(2rem,5.2vw,3.6rem);margin:0 0 22px}
.lede{font-size:1.16rem;color:var(--dim);max-width:60ch;margin:0 0 40px}
p{max-width:66ch}

/* ---------- mechanism ---------- */
.mech{display:grid;grid-template-columns:1fr auto 1fr;gap:0;align-items:center;
  margin:44px 0 8px;border:1px solid var(--rule);border-radius:4px;overflow:hidden;
  background:var(--ink-2)}
.mech-end{padding:30px 26px}
.mech-end .tag{font-family:"JetBrains Mono",monospace;font-size:.7rem;letter-spacing:.18em;
  text-transform:uppercase;color:var(--ember);margin:0 0 8px}
.mech-end strong{font-family:"Anton",sans-serif;font-size:1.5rem;text-transform:uppercase;
  display:block;margin-bottom:6px;font-weight:400}
.mech-end span{color:var(--dim);font-size:.94rem}
.mech-mid{padding:30px 22px;text-align:center;border-left:1px solid var(--rule);
  border-right:1px solid var(--rule);background:#0C0E12;min-width:200px}
.mech-mid .arrow{color:var(--ember);font-size:1.6rem;line-height:1}
.mech-mid p{margin:10px 0 0;font-size:.88rem;color:var(--dim);max-width:none}
@media(max-width:760px){.mech{grid-template-columns:1fr}
  .mech-mid{border-left:0;border-right:0;border-top:1px solid var(--rule);
    border-bottom:1px solid var(--rule)}}

/* ---------- strip ---------- */
.strip{display:grid;grid-template-columns:repeat(5,1fr);gap:2px;margin:40px 0 0}
.strip figure{margin:0;position:relative;overflow:hidden;background:#000;aspect-ratio:16/10}
.strip img{width:100%;height:100%;object-fit:cover;display:block;
  filter:saturate(.92);transition:transform .5s,filter .5s}
.strip figure:hover img{transform:scale(1.06);filter:saturate(1.05)}
.strip figcaption{position:absolute;left:0;bottom:0;right:0;
  font-family:"JetBrains Mono",monospace;font-size:.62rem;letter-spacing:.14em;
  text-transform:uppercase;padding:8px 10px;color:var(--paper);
  background:linear-gradient(180deg,transparent,rgba(0,0,0,.85))}
@media(max-width:860px){.strip{grid-template-columns:repeat(2,1fr)}}

/* ---------- verticals ---------- */
.verts{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:40px}
.vert{background:var(--card);border:1px solid var(--rule);border-radius:4px;
  padding:30px 26px;position:relative;overflow:hidden}
.vert::before{content:"";position:absolute;left:0;top:0;bottom:0;width:2px;background:var(--ember)}
.vert h3{font-size:1.5rem;margin:0 0 8px}
.vert .arg{color:var(--paper);font-style:italic;opacity:.86;margin:0 0 18px;font-size:.98rem}
.vert ul{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:8px}
.vert li{color:var(--dim);font-size:.92rem;display:grid;grid-template-columns:16px 1fr;gap:9px}
.vert li b{color:var(--ember);font-weight:400}
@media(max-width:900px){.verts{grid-template-columns:1fr}}

/* ---------- pricing ---------- */
.tiers{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:40px}
.tier{background:var(--card);border:1px solid var(--rule);border-radius:4px;
  padding:32px 26px;display:flex;flex-direction:column}
.tier.feature{border-color:var(--ember);background:#17120D}
.tier .name{font-family:"JetBrains Mono",monospace;font-size:.72rem;letter-spacing:.2em;
  text-transform:uppercase;color:var(--dim);margin:0 0 14px}
.tier.feature .name{color:var(--ember)}
.tier .price{font-family:"Anton",sans-serif;font-size:3rem;line-height:1;margin:0 0 4px}
.tier .per{color:var(--faint);font-size:.86rem;margin:0 0 22px}
.tier ul{list-style:none;padding:0;margin:0 0 auto;display:flex;flex-direction:column;gap:10px}
.tier li{font-size:.93rem;color:var(--dim);display:grid;grid-template-columns:14px 1fr;gap:10px}
.tier li b{color:var(--ember);font-weight:400}
.tiers.four{grid-template-columns:repeat(4,1fr);gap:14px}
.tiers.four .tier{padding:26px 20px}
.tiers.four .tier .price{font-size:2.4rem}
.rail{display:flex;align-items:baseline;gap:16px;margin:64px 0 0;flex-wrap:wrap}
.rail h3{font-size:1.6rem;margin:0}
.rail span{color:var(--faint);font-size:.93rem}
.rail:first-of-type{margin-top:40px}
.bands{width:100%;border-collapse:collapse;margin-top:34px;
  border:1px solid var(--rule);border-radius:4px;overflow:hidden}
.bands th{font-family:"JetBrains Mono",monospace;font-size:.68rem;letter-spacing:.18em;
  text-transform:uppercase;color:var(--dim);text-align:left;padding:14px 18px;
  background:var(--ink-2);border-bottom:1px solid var(--rule);font-weight:400}
.bands td{padding:16px 18px;border-bottom:1px solid var(--rule);
  color:var(--dim);font-size:.93rem;vertical-align:top}
.bands tr:last-child td{border-bottom:0}
.bands td.b{font-family:"Anton",sans-serif;text-transform:uppercase;color:var(--paper);
  font-size:1.05rem;white-space:nowrap}
.bands td.p span{font-family:"JetBrains Mono",monospace;font-size:.62rem;
  color:var(--faint);letter-spacing:.1em}
.bands td.p{font-family:"Anton",sans-serif;color:var(--ember);font-size:1.3rem;
  font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
@media(max-width:900px){.tiers,.tiers.four{grid-template-columns:1fr}
  .bands td.why{display:none}}

/* ---------- buy ---------- */
.buy{display:inline-flex;align-items:center;gap:8px;margin-top:22px;
  background:var(--ember);color:#120A04;font-family:"Anton",sans-serif;
  text-transform:uppercase;letter-spacing:.04em;font-size:.9rem;
  padding:11px 20px;border-radius:2px;text-decoration:none;
  transition:transform .16s,background .16s;white-space:nowrap}
.buy:hover{transform:translateY(-1px);background:#EE873F}
.buy:focus-visible{outline:2px solid var(--paper);outline-offset:3px}
.buy.ghost{background:none;color:var(--paper);border:1px solid var(--faint)}
.buy.ghost:hover{background:rgba(255,255,255,.05)}
.tier .buy{width:100%;justify-content:center}
.bands .buy{margin-top:0;font-size:.76rem;padding:8px 14px}

/* ---------- doors ---------- */
.doors{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:44px 0 0;text-align:left}
.door{background:var(--card);border:1px solid var(--rule);border-radius:4px;padding:34px 30px;
  display:flex;flex-direction:column}
.door.hot{border-color:var(--ember);background:#17120D}
.door .who{font-family:"JetBrains Mono",monospace;font-size:.68rem;letter-spacing:.2em;
  text-transform:uppercase;color:var(--ember);margin:0 0 12px}
.door h3{font-size:1.7rem;margin:0 0 14px}
.door p{color:var(--dim);font-size:.96rem;max-width:none;margin:0 0 16px}
.door p.mono{color:var(--faint);font-size:.8rem;letter-spacing:.06em;margin-bottom:24px}
.door .cta{margin-top:auto;align-self:flex-start}
@media(max-width:860px){.doors{grid-template-columns:1fr}}

/* ---------- split compare ---------- */
.split{display:grid;grid-template-columns:1fr 1fr;gap:2px;margin-top:40px;
  border:1px solid var(--rule);border-radius:4px;overflow:hidden}
.split > div{background:var(--ink-2);padding:34px 30px}
.split > div.hot{background:#17120D}
.split h3{font-size:1.7rem;margin:0 0 6px}
.split .who{font-family:"JetBrains Mono",monospace;font-size:.68rem;letter-spacing:.18em;
  text-transform:uppercase;color:var(--ember);margin:0 0 18px}
.split p{color:var(--dim);font-size:.96rem;max-width:none;margin:0 0 14px}
.split p:last-child{margin:0}
.split strong{color:var(--paper);font-weight:500}
@media(max-width:860px){.split{grid-template-columns:1fr}}

/* ---------- compliance ---------- */
.warn{border:1px solid var(--ember-dim);background:#16100A;border-radius:4px;
  padding:30px 32px;margin-top:36px}
.warn h3{font-size:1.3rem;color:var(--ember);margin:0 0 14px}
.warn p{color:var(--dim);margin:0 0 12px}
.warn p:last-child{margin:0}
.warn strong{color:var(--paper)}

.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:2px;margin-top:44px;
  border:1px solid var(--rule);border-radius:4px;overflow:hidden}
.stat{background:var(--ink-2);padding:26px 22px}
.stat .n{font-family:"Anton",sans-serif;font-size:2.4rem;line-height:1;color:var(--ember);
  font-variant-numeric:tabular-nums}
.stat .l{font-family:"JetBrains Mono",monospace;font-size:.68rem;letter-spacing:.16em;
  text-transform:uppercase;color:var(--dim);margin-top:8px}
@media(max-width:860px){.stats{grid-template-columns:repeat(2,1fr)}}

footer{padding:70px 0 90px}
.foot{display:flex;justify-content:space-between;gap:24px;flex-wrap:wrap;
  color:var(--faint);font-size:.87rem}

.reveal{opacity:0;transform:translateY(22px);transition:opacity .7s ease,transform .7s ease}
.reveal.in{opacity:1;transform:none}
@media(prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
  .reveal{opacity:1;transform:none}}
"""


VIDEO_CSS = """
.reel{margin:44px 0 0;border:1px solid var(--rule);border-radius:4px;overflow:hidden;
  background:#000;position:relative}
.reel video{display:block;width:100%;height:auto}
.reel .meta{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;
  padding:14px 18px;background:var(--ink-2);border-top:1px solid var(--rule);
  font-family:"JetBrains Mono",monospace;font-size:.72rem;letter-spacing:.12em;
  text-transform:uppercase;color:var(--dim)}
.reel .meta b{color:var(--ember);font-weight:400}
.pending{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:26px}
.pending .slot{border:1px dashed var(--rule);border-radius:4px;padding:26px 22px;
  background:#0C0E12}
.pending .slot h4{font-family:"Anton",sans-serif;text-transform:uppercase;
  font-weight:400;font-size:1.15rem;margin:0 0 6px;color:var(--faint)}
.pending .slot p{margin:0;font-size:.86rem;color:var(--faint);max-width:none}
.pending .slot .brief{font-family:"JetBrains Mono",monospace;font-size:.66rem;
  letter-spacing:.14em;text-transform:uppercase;color:var(--ember-dim);margin-top:10px}
@media(max-width:900px){.pending{grid-template-columns:1fr}}
"""


def money(v: float) -> str:
    return f"${v:,.0f}" if float(v).is_integer() else f"${v:,.2f}"


PAY = CONFIG.get("payments", {})
LINKS = PAY.get("links", {})


def buy(sku: str, label: str = "Buy") -> str:
    """A Buy button when the SKU has a payment link, the email path when it does
    not. Never a dead button: an unclickable price is worse than no price, and a
    button that 404s after someone decides to spend money is worse than both.

    Payment Links are public URLs with no key in them, which is what lets a
    static page take money with no backend to secure."""
    href = LINKS.get(sku, "")
    if href:
        return (f'<a class="buy" href="{href}" data-sku="{sku}">{label} '
                f'<span aria-hidden="true">&rarr;</span></a>')
    subj = f"Order — {sku}"
    return (f'<a class="buy ghost" href="mailto:{CONFIG["contact_email"]}'
            f'?subject={subj.replace(" ", "%20").replace("—", "%E2%80%94")}">'
            f'Order by email <span aria-hidden="true">&rarr;</span></a>')


def tier_cards(rows: list[dict], *, four: bool = False) -> str:
    """Render priced cards straight from pricing.json. No number is typed here."""
    cards = []
    for r in rows:
        bullets = "\n".join(
            f'<li><b>·</b><span>{b}</span></li>' for b in r["bullets"])
        cls = "tier feature" if r.get("featured") else "tier"
        name = r["name"].replace(" - ", " — ") + (" · most taken" if r.get("featured") else "")
        cards.append(
            f'<div class="{cls}"><p class="name">{name}</p>'
            f'<p class="price">{money(r["price"])}</p>'
            f'<p class="per">{r["per"]}</p><ul>{bullets}</ul>'
            f'{buy(r["sku"])}</div>')
    grid = "tiers four" if four else "tiers"
    return f'<div class="{grid}">{"".join(cards)}</div>'


def lot_table(rows: list[dict]) -> str:
    body = "\n".join(
        f'<tr><td class="b">{r["name"]}</td>'
        f'<td>{r["units"]} vehicles a month</td>'
        f'<td class="why">{money(r["per_unit"])} a vehicle</td>'
        f'<td class="p">{money(r["price"])}<span>/mo</span></td>'
        f'<td style="text-align:right">{buy(r["sku"], "Subscribe")}</td></tr>'
        for r in rows)
    return (f'<table class="bands"><tr><th>Plan</th><th>Volume</th>'
            f'<th class="why">Effective rate</th>'
            f'<th style="text-align:right">Monthly</th><th></th></tr>{body}</table>')


def band_table(rows: list[dict]) -> str:
    body = "\n".join(
        f'<tr><td class="b">{r["band"]}</td><td>{r["product"]}</td>'
        f'<td class="why">{r["why"]}</td><td class="p">{money(r["price"])}</td></tr>'
        for r in rows)
    return (f'<table class="bands"><tr><th>Vehicle price</th><th>What we cut</th>'
            f'<th class="why">Why</th><th style="text-align:right">Per unit</th></tr>'
            f'{body}</table>')


def build() -> Path:
    d = CONFIG
    hero, closer = data_uri("hero.jpg"), data_uri("closer.jpg")
    beats = [data_uri(f"beat{i}.jpg") for i in range(1, 6)]
    labels = ["Exterior", "Entry", "Living", "Kitchen", "Patio"]

    teaser = data_uri("teaser.mp4")
    prop = MEDIA["property"]
    reel = ""
    if teaser and prop.get("ready"):
        reel = f"""
    <div class="reel">
      <video autoplay muted loop playsinline poster="{closer}">
        <source src="{teaser}" type="video/mp4">
      </video>
      <div class="meta">
        <span>{prop['title']}</span>
        <span>{prop['brief']}</span>
        <span><b>{prop['shots']} shots</b> · {prop['seconds']}s · anchored</span>
        <span><a href="{prop['master']}">Full film 16:9</a> · <a href="{prop['vertical']}">9:16</a></span>
      </div>
    </div>"""

    waiting = [v for k, v in MEDIA.items()
               if not k.startswith("_") and not v.get("ready")]
    slots = ""
    if waiting:
        cards = "\n".join(
            f'<div class="slot"><h4>{v["title"]}</h4>'
            f'<p>{v["waiting_on"]}</p>'
            f'<p class="brief">{v["brief"]}</p></div>' for v in waiting)
        slots = f'<div class="pending">{cards}</div>'

    prop_tiers = tier_cards(PRICING["property"])
    veh_tiers = tier_cards(PRICING["vehicle"], four=True)
    bands = band_table(PRICING["bands"])
    lot_plans = lot_table(PRICING["lot_plans"])
    default = next(t for t in PRICING["property"] if t["featured"])
    default_price = money(default["price"])
    default_seconds = default["per"].rsplit("·", 1)[-1].strip().split()[0]
    lot_entry = PRICING["lot_plans"][0]
    lot_entry_price, lot_entry_units = money(lot_entry["price"]), lot_entry["units"]
    email, domain, short_domain = d["contact_email"], d["domain"], d["short_domain"]
    ret = PRICING["retainer"]
    ret_price, ret_n = money(ret["price"]), ret["listings"]
    ret_each = money(ret["per_listing"])

    strip = "\n".join(
        f'<figure><img src="{b}" alt="{l} anchor frame" loading="lazy">'
        f'<figcaption>{i+1:02d} — {l}</figcaption></figure>'
        for i, (b, l) in enumerate(zip(beats, labels)) if b
    )

    html = f"""<title>FlyThrough</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{d['tagline']}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Anton&family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<style>{CSS}{VIDEO_CSS}</style>

<header class="hero">
  <div class="hero-img" style="background-image:url('{hero}')"></div>
  <div class="wrap">
    <p class="kicker">{d['domain']}</p>
    <h1>They already<br>paid for the<em>photos.</em></h1>
    <p>We turn them into the film they never commissioned. No shoot. No crew. No weather. Next day.</p>
    <a class="cta" href="#start">Send us a listing →</a>
  </div>
</header>

<section id="how">
  <div class="wrap">
    <p class="eyebrow">The mechanism</p>
    <h2>The AI never<br>sees the subject.</h2>
    <p class="lede">Most AI video takes one photo and hallucinates a flight around it. Windows multiply. Furniture melts. The back of the house gets invented. Ours cannot do that, by construction.</p>

    <div class="mech">
      <div class="mech-end">
        <p class="tag">First frame</p>
        <strong>Your photo</strong>
        <span>The real kitchen. Unedited. Exactly as your photographer shot it.</span>
      </div>
      <div class="mech-mid">
        <div class="arrow">→</div>
        <p>AI generates <b>only the travel</b> between two real frames</p>
      </div>
      <div class="mech-end">
        <p class="tag">Last frame</p>
        <strong>Your photo</strong>
        <span>The real dining room. The clip cannot end anywhere else.</span>
      </div>
    </div>
    <p style="color:var(--faint);font-size:.92rem;margin-top:18px">Every shot is anchored at both ends. The model is never asked what the property looks like — it is told, twice, and asked only how the camera gets between them.</p>

    {reel}
    <div class="strip">{strip}</div>
    <p style="color:var(--faint);font-size:.86rem;margin-top:14px" class="mono">Real anchor frames from a delivered 27-second tour. Each shot ends on the frame the next one begins.</p>
  </div>
</section>

<section id="work">
  <div class="wrap">
    <p class="eyebrow">What we make</p>
    <h2>One engine.<br>Three arguments.</h2>
    <p class="lede">A tour asks what is here. An advert asks why you should want it. Same anchoring, different cut — because a supercar and a family home are not selling the same feeling.</p>
    <div class="verts">
      <div class="vert">
        <h3>Property</h3>
        <p class="arg">"Imagine your life here. Take your time."</p>
        <ul>
          <li><b>·</b><span>26–60s, calm, long takes</span></li>
          <li><b>·</b><span>Buyer's-walk order, not file order</span></li>
          <li><b>·</b><span>16:9 for MLS + 9:16 vertical</span></li>
          <li><b>·</b><span>AI disclosure built in</span></li>
        </ul>
      </div>
      <div class="vert">
        <h3>Vehicles</h3>
        <p class="arg">"This is engineering sculpture and you want to be seen in it."</p>
        <ul>
          <li><b>·</b><span>12–20s, fast beats, detail pushes</span></li>
          <li><b>·</b><span>Every VIN, not just the halo cars</span></li>
          <li><b>·</b><span>Bed, wheels, seats, screen</span></li>
          <li><b>·</b><span>From the photos your lot already shoots</span></li>
        </ul>
      </div>
      <div class="vert">
        <h3>Product</h3>
        <p class="arg">"This is beautifully made, and it is new."</p>
        <ul>
          <li><b>·</b><span>15–25s, vertical first</span></li>
          <li><b>·</b><span>Hero, detail, material, scale</span></li>
          <li><b>·</b><span>No person, no testimonial, no claim</span></li>
          <li><b>·</b><span>Nothing to disclose, nothing to defend</span></li>
        </ul>
      </div>
    </div>
    {slots}
  </div>
</section>

<section id="cut">
  <div class="wrap">
    <p class="eyebrow">The difference that matters</p>
    <h2>A walkaround is<br>inventory. An ad<em> is an argument.</em></h2>
    <p class="lede">Most vehicle video is documentation — proof the car exists, shot the same way for every unit on the lot. Useful. Not persuasive. We make both, and we do not pretend they are the same thing.</p>

    <div class="split">
      <div>
        <p class="who">Walkaround</p>
        <h3>Every VIN</h3>
        <p>One template, run across the whole lot. Exterior orbit, interior, dash, wheels. Twenty seconds. It goes on the vehicle detail page and it makes a static gallery feel alive.</p>
        <p>It is <strong>identical for every unit</strong> — and that is the point. A dealer with 300 cars cannot brief 300 films.</p>
        <p>Priced as a commodity, sold by the month.</p>
      </div>
      <div class="hot">
        <p class="who">Ad cut</p>
        <h3>One vehicle</h3>
        <p>Briefed to the unit. A Ferrari opens on the badge and snaps between beats at hype tempo. A Silverado opens wide on the stance, holds on the bed and the red leather, and moves with weight.</p>
        <p><strong>Same anchoring engine, different argument.</strong> Tempo, opening frame, closing frame, which details get a push and which get skipped — all of it changes per vehicle.</p>
        <p>Priced against the marketing budget the unit already carries.</p>
      </div>
    </div>
    <p style="color:var(--faint);font-size:.9rem;margin-top:18px" class="mono">The second one is what we actually sell. The first one is how we get in the door.</p>
  </div>
</section>

<section id="price">
  <div class="wrap">
    <p class="eyebrow">Pricing</p>
    <h2>Below a crew.<br>Above a filter.</h2>
    <p class="lede">A walkthrough video runs $300–$500 and takes a week. A drone package runs $150–$500 and needs a weather window and a licensed pilot. A freelance vehicle spot runs $150–$400. We need a folder.</p>

    <div class="rail"><h3>Property</h3><span>per listing · 24-hour delivery · disclosure pack included</span></div>
    {prop_tiers}
    <p style="color:var(--faint);font-size:.92rem;margin-top:16px">Listing agents who shoot every week take the retainer: <strong style="color:var(--paper)">{ret_price} for {ret_n} listings a month</strong> — {ret_each} each, billed once, no per-job approval.</p>

    <div class="rail"><h3>Vehicles</h3><span>per unit · your photos · you own the file outright</span></div>
    {veh_tiers}

    <p style="color:var(--dim);font-size:.98rem;margin-top:34px;max-width:66ch">We price a vehicle ad against what the vehicle is worth, not what it costs us to make. Production is near-identical at every tier — the render on a premium ad cut is under two dollars. What differs is the marketing budget already attached to the unit.</p>
    {bands}
    <div class="rail"><h3>Lot plans</h3><span>walkarounds in volume · one monthly invoice</span></div>
    {lot_plans}
    <p style="color:var(--faint);font-size:.86rem;margin-top:14px" class="mono">Ad cuts are ordered per unit, on top of any plan, whenever a car deserves one.</p>
  </div>
</section>

<section id="legal">
  <div class="wrap narrow">
    <p class="eyebrow">The part nobody else ships</p>
    <h2>Disclosure,<br>already handled.</h2>
    <p class="lede">An AI video that looks like drone footage is a disclosure problem even when every source photo is genuine. The images are real. The flight is not.</p>

    <div class="warn">
      <h3>What the rules actually say</h3>
      <p><strong>NAR Code of Ethics, Article 12</strong> requires REALTORS® to present a true picture and to disclose the status of any altered photograph. It binds every REALTOR®, in every state.</p>
      <p><strong>California AB 723</strong> — Business &amp; Professions Code §10140.8, effective 1 January 2026 — requires a conspicuous statement that an image was modified <strong>and a link to the original unaltered image</strong> by URL or QR code. It reaches "a person acting on their behalf", which means your vendor too.</p>
      <p>MLS penalties for non-disclosure commonly run <strong>$500–$5,000</strong>.</p>
    </div>

    <p style="margin-top:32px">Most AI video ships you a file and a liability. Every delivery of ours arrives with the disclosure card burned into the video, a QR code, ready-to-paste MLS remark text, and a hosted page carrying your unaltered originals — which is the artefact the statute actually asks for.</p>
    <p><strong>We never retouch, stage or colour-correct what you send.</strong> Not a limitation — the moment we edit a photo, that originals page stops containing originals, and the position collapses for both of us.</p>
    <p style="color:var(--faint);font-size:.9rem">Not legal advice. Rules vary by MLS and state. Have your broker's counsel review the disclosure text.</p>

    <div class="stats">
      <div class="stat"><div class="n">85%</div><div class="l">of buyers watch video</div></div>
      <div class="stat"><div class="n">73%</div><div class="l">of sellers prefer agents who use it</div></div>
      <div class="stat"><div class="n">9%</div><div class="l">of agents actually make it</div></div>
      <div class="stat"><div class="n">24h</div><div class="l">from folder to finished film</div></div>
    </div>
  </div>
</section>

<section id="start" style="background-image:linear-gradient(180deg,rgba(8,9,11,.90),rgba(8,9,11,.97)),url('{closer}');background-size:cover;background-position:center">
  <div class="wrap" style="text-align:center">
    <p class="eyebrow">Start here</p>
    <h2>Send us one.<br>The first one<em>is free.</em></h2>
    <p class="lede" style="margin-left:auto;margin-right:auto;text-align:center">No brief, no call, no card. Send the photos you already have and you will have the film tomorrow. If you like it, you pay for the next one. If you don't, keep it anyway.</p>

    <div class="doors">
      <div class="door">
        <p class="who">Listing agents</p>
        <h3>One active listing</h3>
        <p>Six to twelve photos, whatever your photographer delivered. We cut a {default_seconds}-second tour in buyer's-walk order, with the disclosure pack attached and your originals hosted.</p>
        <p class="mono">Then {default_price} a listing, or {ret_price} for {ret_n} a month.</p>
        <a class="cta" href="mailto:{email}?subject=Free%20sample%20—%20my%20listing">Email the photos →</a>
      </div>
      <div class="door hot">
        <p class="who">Dealers</p>
        <h3>Three vehicles</h3>
        <p>Pick your worst-performing unit, your newest arrival, and the one you are proudest of. You get a walkaround, an ad cut and a vertical back — and you will see immediately which one sells.</p>
        <p class="mono">Then {lot_entry_price} a month for {lot_entry_units} walkarounds. Ad cuts on top.</p>
        <a class="cta" href="mailto:{email}?subject=Three%20free%20vehicles%20—%20my%20lot">Email the VINs →</a>
      </div>
    </div>

    <p class="note" style="color:var(--dim);font-size:.94rem;margin:34px auto 0;max-width:56ch">Not sure your photos are good enough? They almost certainly are — but the <a href="/shot-guide/">shot guides</a> say exactly what we need for a property, a vehicle or a product, and where the camera should stand for anything you are missing.</p>
    <p class="mono" style="color:var(--faint);font-size:.8rem;margin:22px auto 0">{email} · {domain} · {short_domain}</p>
  </div>
</section>

<footer>
  <div class="wrap foot">
    <span>{d['brand']} · {d['domain']}</span>
    <span class="mono">Anchored AI video · every shot begins and ends on a real photograph</span>
  </div>
</footer>

<script>
(function(){{
  var io=new IntersectionObserver(function(es){{
    es.forEach(function(e){{ if(e.isIntersecting){{ e.target.classList.add('in'); io.unobserve(e.target); }} }});
  }},{{threshold:.12}});
  document.querySelectorAll('section .wrap > *').forEach(function(el,i){{
    el.classList.add('reveal'); el.style.transitionDelay=(Math.min(i,6)*45)+'ms'; io.observe(el);
  }});
}})();
</script>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    return OUT


if __name__ == "__main__":
    p = build()
    print(f"  built {p}  ({p.stat().st_size/1024:.0f} KB)")
