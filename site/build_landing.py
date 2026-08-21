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
.tier{background:var(--card);border:1px solid var(--rule);border-radius:4px;padding:32px 26px}
.tier.feature{border-color:var(--ember);background:#17120D}
.tier .name{font-family:"JetBrains Mono",monospace;font-size:.72rem;letter-spacing:.2em;
  text-transform:uppercase;color:var(--dim);margin:0 0 14px}
.tier.feature .name{color:var(--ember)}
.tier .price{font-family:"Anton",sans-serif;font-size:3rem;line-height:1;margin:0 0 4px}
.tier .per{color:var(--faint);font-size:.86rem;margin:0 0 22px}
.tier ul{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:10px}
.tier li{font-size:.93rem;color:var(--dim);display:grid;grid-template-columns:14px 1fr;gap:10px}
.tier li b{color:var(--ember);font-weight:400}
@media(max-width:900px){.tiers{grid-template-columns:1fr}}

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

<section id="price">
  <div class="wrap">
    <p class="eyebrow">Pricing</p>
    <h2>Below a crew.<br>Above a filter.</h2>
    <p class="lede">A walkthrough video runs $300–$500 and takes a week. A drone package runs $150–$500 and needs a weather window and a licensed pilot. We need a folder.</p>
    <div class="tiers">
      <div class="tier">
        <p class="name">Single listing</p>
        <p class="price">$149</p>
        <p class="per">one property · 30 seconds</p>
        <ul>
          <li><b>·</b><span>16:9 master + thumbnail</span></li>
          <li><b>·</b><span>Full disclosure pack</span></li>
          <li><b>·</b><span>24-hour delivery</span></li>
          <li><b>·</b><span>One revision</span></li>
        </ul>
      </div>
      <div class="tier feature">
        <p class="name">Listing pro · most taken</p>
        <p class="price">$249</p>
        <p class="per">one property · 42 seconds</p>
        <ul>
          <li><b>·</b><span>Everything in Single</span></li>
          <li><b>·</b><span>9:16 vertical for Reels</span></li>
          <li><b>·</b><span>MLS + social caption text</span></li>
          <li><b>·</b><span>Two revisions</span></li>
        </ul>
      </div>
      <div class="tier">
        <p class="name">Dealer lot plan</p>
        <p class="price">$39</p>
        <p class="per">per vehicle · 50/mo from $1,450</p>
        <ul>
          <li><b>·</b><span>20s walkaround, every VIN</span></li>
          <li><b>·</b><span>9:16 + 16:9 + thumbnail</span></li>
          <li><b>·</b><span>Folder drop, 24h turnaround</span></li>
          <li><b>·</b><span>You own it outright</span></li>
        </ul>
      </div>
    </div>
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
  <div class="wrap narrow" style="text-align:center">
    <p class="eyebrow" style="justify-content:center">Start here</p>
    <h2>Send one listing.<br>We'll do it free.</h2>
    <p class="lede" style="margin-left:auto;margin-right:auto">Pick a property that's currently active. Send the photos you already have. You'll have the film tomorrow. If you like it, it's $249 a listing after that — and if you don't, keep it anyway.</p>
    <p style="margin:0 auto 34px;max-width:none">
      <a class="cta" href="mailto:{d['contact_email']}?subject=Free%20sample%20—%20my%20listing">Email the photos →</a>
      <a class="cta ghost" href="#how" style="margin-left:10px">See how it works</a>
    </p>
    <p class="mono" style="color:var(--faint);font-size:.8rem;margin:0 auto">{d['contact_email']}</p>
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
