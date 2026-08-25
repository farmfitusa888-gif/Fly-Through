"""The FastAPI application.

Route map:

    /                       pick what to buy
    /order/{id}             upload photographs + answer the brief
    /order/{id}/upload      POST  add files
    /order/{id}/brief       POST  save answers
    /order/{id}/checkout    POST  hand off to Stripe
    /start                  post-payment landing (shows status, never sets it)
    /webhooks/stripe        POST  the ONLY thing that marks an order paid
    /login  /auth           magic link
    /orders                 the customer dashboard
    /orders/{id}/file/{k}   download a deliverable
    /partner                the reseller ledger
    /partner/join           enrol
    /admin/queue            operator view

Ordering that is load-bearing, not incidental: photographs are uploaded and
validated BEFORE payment. Any other sequence occasionally charges someone whose
photos cannot make a film.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, FileResponse

from . import (auth, catalog_bridge as cat, limits, notify, orders,
               outcomes, payments, render, reseller)
from .config import Settings, load
from .db import Database, new_id, now
from .mail import Mailer
from .queue import Worker
from .storage import Store, UploadRejected
from .ui import esc, flash, money, page, status_pill

SESSION_COOKIE = "ft_session"
REFERRAL_COOKIE = "ft_ref"


def default_renderer(*, order_id, vertical, slug, originals, out_dir, brief,
                     placement):
    """The real renderer: pipeline.plan_runner, unchanged.

    Imported lazily so the web app starts on a machine with no ffmpeg. The
    dashboard and the ledger do not need a codec, and refusing to boot the whole
    service because one is missing would take the money side down with it.

    The provider comes from provider_from_env(). If it is not configured this
    raises, the queue records a failed job with the reason, and the operator
    sees it on /admin/queue -- which is the correct outcome. A renderer that
    quietly produces something without a provider is how a customer receives a
    slideshow and an invoice.
    """
    import sys
    root = Path(__file__).resolve().parents[2]
    if str(root / "pipeline") not in sys.path:
        sys.path.insert(0, str(root / "pipeline"))
    from flythrough.plan_runner import render_order

    submit, poll = provider_from_env()
    return render_order(vertical=vertical, slug=slug, originals=Path(originals),
                        out_dir=Path(out_dir), brief=brief, placement=placement,
                        submit=submit, poll=poll)


def provider_from_env():
    """(submit, poll) for the configured render provider.

    Kept as one small seam because the provider is the single most likely thing
    to change: OpenArt today, something else the moment a model with better
    dual-frame anchoring ships. Nothing above this function knows the vendor.
    """
    import os
    profile = os.environ.get("FLYTHROUGH_PROVIDER", "")
    if not profile:
        raise RuntimeError(
            "no render provider configured. Set FLYTHROUGH_PROVIDER and the "
            "provider credentials, or pass renderer= to create_app().")
    raise RuntimeError(
        f"provider {profile!r} has no submit/poll implementation in this build. "
        "Add it in pipeline/flythrough/providers/ and wire it here.")


def create_app(settings: Settings | None = None, *, renderer=None,
               start_worker: bool = False) -> FastAPI:
    s = settings or load()
    db = Database(s.data_dir / "flythrough.db")
    store = Store(s.data_dir / "blobs")
    mailer = Mailer(s.smtp_url, spool=s.data_dir / "outbox.jsonl",
                    sender=s.contact_email)
    worker = Worker(db=db, data_dir=s.data_dir,
                    renderer=renderer or default_renderer,
                    concurrency=s.render_concurrency,
                    mailer=mailer, settings=s)

    app = FastAPI(title=s.brand, docs_url=None, redoc_url=None,
                  openapi_url=None)
    app.state.settings, app.state.db = s, db
    app.state.store, app.state.mailer, app.state.worker = store, mailer, worker

    if start_worker:
        worker.start()

    # ------------------------------------------------------------- helpers
    def who(request: Request) -> auth.Principal | None:
        return auth.resolve_session(db, request.cookies.get(SESSION_COOKIE))

    def nav(p: auth.Principal | None):
        links = [("Buy", "/")]
        if p and p.is_reseller:
            links.append(("Partner", "/partner"))
        elif p:
            links.append(("My orders", "/orders"))
        else:
            links += [("Sign in", "/login"), ("Partner", "/partner/join")]
        return links

    def render_page(request, title, body, *, narrow=False):
        p = who(request)
        return HTMLResponse(page(title, body, brand=s.brand, nav_links=nav(p),
                                 here=request.url.path, narrow=narrow))

    def require(request: Request):
        p = who(request)
        if p is None:
            return None
        return p

    def is_operator(request: Request) -> bool:
        """Operator pages list every order in the system. `require()` only
        proves SOMEONE is signed in -- which was enough to let any customer read
        the whole queue. Membership is checked by address against the
        allow-list, and in production an empty list admits nobody.
        """
        p = who(request)
        if p is None:
            return False
        if s.dev_mode and not s.operator_emails:
            return True          # laptop with nothing configured
        email = auth.email_of(db, p)
        return bool(email) and email in s.operator_emails

    def check_csrf(request: Request, token: str) -> bool:
        sess = request.cookies.get(SESSION_COOKIE) or ""
        return bool(sess) and auth.csrf_ok(sess, s.secret_key or "dev", token)

    def csrf_field(request: Request) -> str:
        sess = request.cookies.get(SESSION_COOKIE) or ""
        if not sess:
            return ""
        t = auth.csrf_token(sess, s.secret_key or "dev")
        return f'<input type="hidden" name="csrf" value="{esc(t)}">'

    # ------------------------------------------------------------ buy flow
    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, ref: str = ""):
        # Grouped by vertical. Thirteen SKUs in one list is a wall of choices
        # that makes an agent read nine lines about vehicles to find their own.
        groups = {"rooms": ("Property", "Listings, per property or on a retainer."),
                  "vehicles": ("Vehicles", "Per unit, or every VIN on the lot."),
                  "products": ("Product", "One product, one film.")}
        sections = []
        for vert, (heading, blurb) in groups.items():
            rows = []
            for sku in cat.skus().values():
                if sku.vertical != vert:
                    continue
                per = " / month" if sku.mode == "recurring" else ""
                rows.append(
                    f'<tr><td class="k">{esc(sku.name.replace(" - ", " — "))}</td>'
                    f'<td>{esc(sku.turnaround)}</td>'
                    f'<td>{esc(money(round(sku.price * 100)))}{per}</td>'
                    f'<td><form method="post" action="/order">'
                    f'<input type="hidden" name="sku" value="{esc(sku.id)}">'
                    f'<button>Start</button></form></td></tr>')
            sections.append(
                f'<h2>{esc(heading)}</h2><p class="note">{esc(blurb)}</p>'
                f'<table><tr><th>What</th><th>Turnaround</th><th>Price</th>'
                f'<th></th></tr>{"".join(rows)}</table>')
        body = (
            '<p class="kicker">Order</p><h1>Send us the photos.</h1>'
            '<p class="lede">Upload first, then pay. We check the set before '
            'anything is charged — if your photographs cannot make a film, you '
            'find out before you spend money, not after.</p>'
            + "".join(sections))
        resp = render_page(request, "Order", body)
        if ref:
            # First-touch attribution is decided when the account is created;
            # this only remembers who sent them until then.
            resp.set_cookie(REFERRAL_COOKIE, ref[:16].upper(), max_age=90 * 86400,
                            httponly=True, samesite="lax")
        return resp

    @app.post("/order")
    def start_order(request: Request, sku: str = Form(...)):
        p = who(request)
        if p is None or p.customer_id is None:
            return RedirectResponse(f"/login?next=/&sku={quote(sku)}", 303)
        try:
            cat.get(sku)
        except cat.UnknownSku:
            return RedirectResponse("/", 303)
        oid = orders.create(db, p.customer_id, sku)
        return RedirectResponse(f"/order/{oid}", 303)

    @app.get("/order/{order_id}", response_class=HTMLResponse)
    def order_page(request: Request, order_id: str, msg: str = "", err: str = ""):
        p = who(request)
        if p is None or p.customer_id is None:
            return RedirectResponse(f"/login?next=/order/{order_id}", 303)
        o = orders.get(db, order_id, customer_id=p.customer_id)
        if o is None:
            return render_page(request, "Not found",
                               "<h1>Not found.</h1>", narrow=True)
        sku = cat.get(o["sku"])
        brief = json.loads(o["brief"] or "{}")
        with db.tx() as c:
            ups = c.execute("SELECT * FROM uploads WHERE order_id=? ORDER BY position",
                            (order_id,)).fetchall()
        ready = orders.readiness(db, order_id)

        files = "".join(
            f'<li><span>{esc(u["filename"])}</span>'
            f'<span class="mono">{esc(u["room_key"] or "?")}</span></li>'
            for u in ups) or '<li><span class="note">Nothing uploaded yet.</span></li>'

        fields = "".join(
            f'<label>{esc(q)}</label>'
            f'<input name="q{i}" value="{esc(brief.get(q, ""))}" autocomplete="off">'
            for i, q in enumerate(cat.intake_for(o["vertical"])))

        problems = ("".join(f"<li><span>{esc(x)}</span></li>" for x in ready.problems)
                    if ready.problems else "")

        # The V3 loop, spent. Not a dashboard -- one sentence, at the only moment
        # it can change a decision, and only when the evidence is strong enough
        # to say out loud. best_advice() returns None far more often than not.
        advice = ""
        if o["vertical"] == "rooms":
            line = outcomes.best_advice(db, "Daylight, golden hour or twilight")
            if line:
                advice = (f'<div class="card"><h3>From our delivered work</h3>'
                          f'<p>{esc(line)}</p></div>')
        gate = (f'<form method="post" action="/order/{esc(order_id)}/checkout">'
                f'{csrf_field(request)}<button>Pay {esc(money(o["price_cents"]))} →</button></form>'
                if ready.ok else
                f'<div class="card plain"><h3>Not ready yet</h3>'
                f'<ul class="plain">{problems}</ul>'
                f'<p class="note">We check before charging, on purpose.</p></div>')

        paid = o["status"] not in ("draft", "awaiting_payment")
        body = (
            f'{flash(err) or flash(msg, "ok")}'
            f'<p class="kicker">{esc(sku.name)} · {esc(money(o["price_cents"]))}</p>'
            f'<h1>Your brief</h1>'
            f'<p class="lede">{esc(sku.blurb)}</p>'
            + ("" if paid else
               f'<div class="card"><h3>Photographs</h3>'
               f'<p>{esc(ready.required)} minimum. '
               f'<a href="/shot-guide/{esc({"rooms": "property", "vehicles": "vehicle", "products": "product"}[o["vertical"]])}/">'
               f'What to send →</a></p>'
               f'<ul class="plain">{files}</ul>'
               f'<form method="post" action="/order/{esc(order_id)}/upload" '
               f'enctype="multipart/form-data">{csrf_field(request)}'
               f'<input type="file" name="files" multiple accept="image/*">'
               f'<button>Upload</button></form></div>'
               f'<div class="card"><h3>Three questions</h3>'
               f'<form method="post" action="/order/{esc(order_id)}/brief">'
               f'{csrf_field(request)}{fields}<button>Save</button></form></div>'
               f'{advice}{gate}')
            + (f'<div class="card"><h3>Status</h3><p>{status_pill(o["status"])}</p>'
               f'<p><a href="/orders">Your orders →</a></p></div>' if paid else ""))
        return render_page(request, "Your brief", body)

    @app.post("/order/{order_id}/upload")
    async def upload(request: Request, order_id: str, files: list[UploadFile] = None,
                     csrf: str = Form("")):
        p = who(request)
        if p is None or p.customer_id is None:
            return RedirectResponse("/login", 303)
        if not check_csrf(request, csrf):
            return RedirectResponse(f"/order/{order_id}?err=Please+try+again", 303)
        o = orders.get(db, order_id, customer_id=p.customer_id)
        if o is None or o["status"] not in ("draft", "awaiting_payment"):
            return RedirectResponse(f"/order/{order_id}"
                                    "?err=This+order+is+already+paid", 303)
        try:
            limits.hit(db, "upload", order_id, limits.UPLOAD_PER_ORDER)
        except limits.TooMany as e:
            return RedirectResponse(f"/order/{order_id}?err={quote(str(e))}", 303)
        mod = render.TAXONOMY[o["vertical"]]
        added, errs = 0, []
        with db.tx() as c:
            used = c.execute("SELECT COALESCE(sum(bytes),0), count(*) FROM uploads"
                             " WHERE order_id=?", (order_id,)).fetchone()
            total, count = used[0], used[1]
        for f in (files or []):
            if count + added >= s.upload_max_files:
                errs.append(f"we cap an order at {s.upload_max_files} photographs")
                break
            try:
                stored = store.put(f.file, max_bytes=s.upload_max_bytes,
                                   allowed=s.allowed_upload_types)
            except UploadRejected as e:
                errs.append(f"{f.filename}: {e}")
                continue
            if total + stored.bytes > s.order_max_bytes:
                errs.append("that would take the order over its total size limit")
                break
            total += stored.bytes
            with db.tx() as c:
                dupe = c.execute("SELECT 1 FROM uploads WHERE order_id=? AND sha256=?",
                                 (order_id, stored.sha256)).fetchone()
                if dupe:
                    errs.append(f"{f.filename}: already uploaded")
                    continue
                pos = c.execute("SELECT COALESCE(max(position),0)+1 FROM uploads"
                                " WHERE order_id=?", (order_id,)).fetchone()[0]
                c.execute("INSERT INTO uploads(id,order_id,filename,mime,bytes,"
                          "sha256,path,room_key,position,created_at)"
                          " VALUES(?,?,?,?,?,?,?,?,?,?)",
                          (new_id("upl"), order_id, f.filename or "photo.jpg",
                           "image/jpeg", stored.bytes, stored.sha256,
                           str(stored.path),
                           mod.resolve(Path(f.filename or "").stem).key,
                           pos, now()))
            added += 1
        q = f"?msg={quote(f'{added} added')}" if added else ""
        if errs:
            q = f"?err={quote('; '.join(errs[:3]))}"
        return RedirectResponse(f"/order/{order_id}{q}", 303)

    @app.post("/order/{order_id}/brief")
    async def save_brief(request: Request, order_id: str):
        p = who(request)
        if p is None or p.customer_id is None:
            return RedirectResponse("/login", 303)
        form = await request.form()
        if not check_csrf(request, form.get("csrf", "")):
            return RedirectResponse(f"/order/{order_id}?err=Please+try+again", 303)
        o = orders.get(db, order_id, customer_id=p.customer_id)
        if o is None:
            return RedirectResponse("/orders", 303)
        qs = cat.intake_for(o["vertical"])
        brief = {q: str(form.get(f"q{i}", "")).strip()[:400]
                 for i, q in enumerate(qs)}
        orders.set_brief(db, order_id, brief)
        return RedirectResponse(f"/order/{order_id}?msg=Saved", 303)

    @app.post("/order/{order_id}/checkout")
    async def checkout(request: Request, order_id: str, csrf: str = Form("")):
        p = who(request)
        if p is None or p.customer_id is None:
            return RedirectResponse("/login", 303)
        if not check_csrf(request, csrf):
            return RedirectResponse(f"/order/{order_id}?err=Please+try+again", 303)
        o = orders.get(db, order_id, customer_id=p.customer_id)
        if o is None:
            return RedirectResponse("/orders", 303)
        ready = orders.readiness(db, order_id)
        if not ready.ok:
            return RedirectResponse(f"/order/{order_id}"
                                    f"?err={quote('; '.join(ready.problems))}", 303)
        with db.tx() as c:
            if o["status"] == "draft":
                orders.transition(c, db, order_id, "awaiting_payment")
        link = (load_links().get(o["sku"]) or "").strip()
        if not link:
            # No Payment Link configured yet. Say so plainly rather than
            # bouncing the customer to a dead URL.
            return RedirectResponse(
                f"/order/{order_id}?err={quote('Card payment is not switched on for this item yet — email ' + s.contact_email + ' and we will invoice you.')}",
                303)
        sep = "&" if "?" in link else "?"
        return RedirectResponse(f"{link}{sep}client_reference_id={quote(order_id)}", 303)

    def load_links() -> dict:
        return json.loads((Path(__file__).resolve().parents[2] / "site" /
                           "config.json").read_text()).get("payments", {}).get("links", {})

    # ------------------------------------------------------------- webhooks
    @app.post("/webhooks/stripe")
    async def stripe_webhook(request: Request):
        raw = await request.body()
        sig = request.headers.get("stripe-signature", "")
        try:
            event = payments.verify(raw, sig, s.stripe_webhook_secret)
        except payments.WebhookError as e:
            # 400, never 500: a bad signature must not be retried.
            return Response(str(e), status_code=400)
        msg, paid = payments.handle(db, event)
        if paid:
            o = orders.get(db, paid)
            sku = cat.skus().get(o["sku"]) if o else None
            notify.receipt(db, mailer, s, paid,
                           what=(sku.name if sku else o["sku"]),
                           amount_cents=o["price_cents"])
            worker.enqueue(paid)
        return Response(msg, status_code=200)

    # ------------------------------------------------------------ post-pay
    @app.get("/start", response_class=HTMLResponse)
    def start(request: Request, order: str = ""):
        o = orders.get(db, order) if order else None
        state = (f"<p>{status_pill(o['status'])}</p>" if o else "")
        body = (
            '<p class="kicker">Thank you</p><h1>We have it.</h1>'
            '<p class="lede">Your film is queued. You will have it within the '
            'turnaround on your order, and an email the moment it is ready.</p>'
            f'{state}<p><a class="btn" href="/orders">Your orders →</a></p>')
        return render_page(request, "Thank you", body, narrow=True)

    # ----------------------------------------------------------------- auth
    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request, next: str = "/orders", sent: str = "",
                   err: str = ""):
        if sent:
            body = ('<h1>Check your email.</h1><p class="lede">We sent a link. It '
                    'works once, and only for the next 20 minutes.</p>')
            return render_page(request, "Check your email", body, narrow=True)
        body = (f'{flash(err)}<p class="kicker">Sign in</p>'
                '<h1>No password.</h1>'
                '<p class="lede">We email you a link. There is no password to '
                'forget, reset, or have stolen from us.</p>'
                f'<form method="post" action="/login">'
                f'<input type="hidden" name="next" value="{esc(next)}">'
                '<label>Your email</label>'
                '<input name="email" type="email" required autocomplete="email">'
                '<button>Email me a link</button></form>')
        return render_page(request, "Sign in", body, narrow=True)

    @app.post("/login")
    def login_send(request: Request, email: str = Form(...),
                   next: str = Form("/orders")):
        try:
            # Both limits, and the address one first: without it anyone can post
            # a stranger's address in a loop and have us mail-bomb someone who
            # is not even a customer.
            normalised = auth.normalise_email(email)
            limits.hit(db, "login_email", normalised, limits.LOGIN_PER_EMAIL)
            limits.hit(db, "login_ip", limits.client_ip(request),
                       limits.LOGIN_PER_IP)
            token = auth.issue_login_token(db, email, ttl_s=s.login_link_ttl_s)
        except (auth.AuthError, limits.TooMany) as e:
            return RedirectResponse(f"/login?err={quote(str(e))}", 303)
        url = f"{s.base_url}/auth?token={quote(token)}&next={quote(next)}"
        mailer.send(auth.normalise_email(email), f"Sign in to {s.brand}",
                    f"Here is your sign-in link. It works once and expires in "
                    f"20 minutes.\n\n{url}\n\nIf you did not ask for this, "
                    f"ignore it — nothing has changed.")
        return RedirectResponse("/login?sent=1", 303)

    @app.get("/auth")
    def auth_redeem(request: Request, token: str = "", next: str = "/orders"):
        try:
            session, principal = auth.redeem_login_token(
                db, token, session_ttl_s=s.session_ttl_s)
        except auth.AuthError as e:
            return RedirectResponse(f"/login?err={quote(str(e))}", 303)
        ref = request.cookies.get(REFERRAL_COOKIE)
        if ref and principal.customer_id:
            reseller.attribute(db, principal.customer_id, ref)
        target = next if next.startswith("/") else "/orders"
        if principal.is_reseller:
            target = "/partner"
        resp = RedirectResponse(target, 303)
        resp.set_cookie(SESSION_COOKIE, session, max_age=s.session_ttl_s,
                        httponly=True, samesite="lax", secure=not s.dev_mode)
        return resp

    @app.post("/logout")
    def logout(request: Request):
        tok = request.cookies.get(SESSION_COOKIE)
        if tok:
            auth.end_session(db, tok)
        resp = RedirectResponse("/", 303)
        resp.delete_cookie(SESSION_COOKIE)
        return resp

    # ------------------------------------------------------------ dashboard
    @app.get("/orders", response_class=HTMLResponse)
    def dashboard(request: Request):
        p = require(request)
        if p is None:
            return RedirectResponse("/login", 303)
        if p.is_reseller:
            return RedirectResponse("/partner", 303)
        rows = []
        for o in orders.list_for_customer(db, p.customer_id):
            sku = cat.skus().get(o["sku"])
            dls = orders.deliverables(db, o["id"])
            links = " ".join(
                f'<a href="/orders/{esc(o["id"])}/file/{esc(d["kind"])}">'
                f'{esc(d["kind"])}</a>' for d in dls) or '<span class="note">—</span>'
            action = (f'<form method="post" action="/order">'
                      f'<input type="hidden" name="sku" value="{esc(o["sku"])}">'
                      f'<button class="btn ghost">Again</button></form>'
                      if o["status"] == "delivered" else
                      f'<a href="/order/{esc(o["id"])}">Open</a>')
            rows.append(
                f'<tr><td class="k">{esc(sku.name if sku else o["sku"])}</td>'
                f'<td>{status_pill(o["status"])}</td>'
                f'<td>{esc(money(o["price_cents"]))}</td>'
                f'<td>{links}</td><td>{action}</td></tr>')
        body = ('<p class="kicker">Your account</p><h1>Your orders</h1>'
                + (f'<table><tr><th>What</th><th>Status</th><th>Paid</th>'
                   f'<th>Files</th><th></th></tr>{"".join(rows)}</table>'
                   if rows else
                   '<p class="lede">Nothing yet. '
                   '<a href="/">Start an order →</a></p>')
                + f'<form method="post" action="/logout">'
                  f'<button class="btn ghost">Sign out</button></form>')
        return render_page(request, "Your orders", body)

    @app.get("/orders/{order_id}/file/{kind}")
    def download(request: Request, order_id: str, kind: str):
        p = require(request)
        if p is None or p.customer_id is None:
            return RedirectResponse("/login", 303)
        o = orders.get(db, order_id, customer_id=p.customer_id)
        if o is None:
            return Response("Not found", status_code=404)
        for d in orders.deliverables(db, order_id):
            if d["kind"] == kind:
                path = Path(d["path"])
                if not path.is_file():
                    return Response("Not found", status_code=404)
                return FileResponse(path, filename=path.name)
        return Response("Not found", status_code=404)

    # -------------------------------------------------------------- partner
    @app.get("/partner/join", response_class=HTMLResponse)
    def partner_join(request: Request, err: str = "", done: str = ""):
        if done:
            body = ('<h1>You are in.</h1><p class="lede">Check your email for a '
                    'sign-in link — your code and ledger are behind it.</p>')
            return render_page(request, "Partner", body, narrow=True)
        pct = int(s.commission_rate * 100)
        body = (f'{flash(err)}<p class="kicker">Partners</p>'
                f'<h1>{pct}% of everything.<br>For as long as they stay.</h1>'
                f'<p class="lede">Not the first order — everything a client you '
                f'introduce ever spends, including retainers and lot plans. '
                f'Whoever introduces a client keeps them: attribution is first '
                f'touch and it never moves.</p>'
                f'<div class="card"><h3>What you get</h3>'
                f'<ul class="plain">'
                f'<li><span>Commission</span><span class="mono">{pct}% lifetime</span></li>'
                f'<li><span>Paid out above</span><span class="mono">'
                f'{esc(money(int(s.payout_minimum_usd * 100)))}</span></li>'
                f'<li><span>On a $249 listing</span><span class="mono">'
                f'{esc(money(round(24900 * s.commission_rate)))}</span></li>'
                f'<li><span>On a $2,600 lot plan</span><span class="mono">'
                f'{esc(money(round(260000 * s.commission_rate)))} a month</span></li>'
                f'</ul></div>'
                f'<form method="post" action="/partner/join">'
                f'<label>Your name</label><input name="name" required>'
                f'<label>Your email</label><input name="email" type="email" required>'
                f'<button>Get my code</button></form>')
        return render_page(request, "Partner programme", body, narrow=True)

    @app.post("/partner/join")
    def partner_enrol(request: Request, name: str = Form(...),
                      email: str = Form(...)):
        try:
            limits.hit(db, "enrol_ip", limits.client_ip(request),
                       limits.ENROL_PER_IP)
            reseller.enrol(db, email, name.strip()[:80],
                           rate=s.commission_rate, lifetime=s.commission_lifetime)
        except (reseller.ResellerError, auth.AuthError, limits.TooMany) as e:
            return RedirectResponse(f"/partner/join?err={quote(str(e))}", 303)
        token = auth.issue_login_token(db, email, ttl_s=s.login_link_ttl_s)
        mailer.send(auth.normalise_email(email), f"Your {s.brand} partner code",
                    f"You are enrolled. Sign in to see your code and ledger:\n\n"
                    f"{s.base_url}/auth?token={quote(token)}&next=/partner\n")
        return RedirectResponse("/partner/join?done=1", 303)

    @app.get("/partner", response_class=HTMLResponse)
    def partner(request: Request):
        p = require(request)
        if p is None:
            return RedirectResponse("/login?next=/partner", 303)
        if not p.is_reseller:
            return RedirectResponse("/partner/join", 303)
        with db.tx() as c:
            r = c.execute("SELECT * FROM resellers WHERE id=?",
                          (p.reseller_id,)).fetchone()
            rows = c.execute(
                "SELECT cm.amount_cents, cm.status, cm.created_at, o.sku"
                " FROM commissions cm JOIN orders o ON o.id = cm.order_id"
                " WHERE cm.reseller_id=? ORDER BY cm.created_at DESC LIMIT 100",
                (p.reseller_id,)).fetchall()
        led = reseller.ledger(db, p.reseller_id,
                              payout_minimum_cents=int(s.payout_minimum_usd * 100))
        link = f"{s.base_url}/?ref={r['code']}"
        table = "".join(
            f'<tr><td class="k">{esc(cat.skus()[x["sku"]].name if x["sku"] in cat.skus() else x["sku"])}</td>'
            f'<td>{esc(money(x["amount_cents"]))}</td>'
            f'<td>{status_pill(x["status"])}</td></tr>' for x in rows)
        body = (
            f'<p class="kicker">Partner · {esc(r["name"])}</p>'
            f'<h1>Your ledger</h1>'
            f'<div class="grid">'
            f'<div class="stat"><div class="big">{esc(money(led.lifetime_cents))}</div>'
            f'<div class="l">Lifetime earned</div></div>'
            f'<div class="stat"><div class="big">{esc(money(led.payable_cents))}</div>'
            f'<div class="l">Payable now</div></div>'
            f'<div class="stat"><div class="big">{esc(money(led.accrued_cents))}</div>'
            f'<div class="l">Accruing</div></div>'
            f'<div class="stat"><div class="big">{led.orders}</div>'
            f'<div class="l">Orders</div></div></div>'
            f'<div class="card"><h3>Your link</h3>'
            f'<p class="mono">{esc(link)}</p>'
            f'<p class="note">Code <strong>{esc(r["code"])}</strong>. Anyone who '
            f'arrives on it is yours from their first order onward — first touch, '
            f'and it never moves to anyone else.</p></div>'
            + (f'<table><tr><th>Order</th><th>Commission</th><th>Status</th></tr>'
               f'{table}</table>' if rows else
               '<p class="note">No commissions yet.</p>')
            + f'<p class="note">Paid out once the payable balance passes '
              f'{esc(money(int(s.payout_minimum_usd * 100)))}.</p>'
              f'<form method="post" action="/logout">'
              f'<button class="btn ghost">Sign out</button></form>')
        return render_page(request, "Partner", body)

    # ------------------------------------------------------------- outcomes
    @app.get("/o/{order_id}", response_class=HTMLResponse)
    def outcome_form(request: Request, order_id: str, done: str = ""):
        """Answering must not require a login. A question that costs a sign-in
        to answer is a question nobody answers, and the response rate IS the
        value -- the order id in the emailed link is the credential, and it is
        already unguessable."""
        o = orders.get(db, order_id)
        if o is None or o["status"] not in ("delivered", "refunded"):
            return Response("Not found", status_code=404)
        if done:
            body = ('<h1>Thank you.</h1><p class="lede">That genuinely helps '
                    '&mdash; it is what lets us tell the next person which way '
                    'of cutting a film actually moves a listing.</p>')
            return render_page(request, "Thank you", body, narrow=True)
        sku = cat.skus().get(o["sku"])
        body = (f'<p class="kicker">One question</p><h1>Did it sell?</h1>'
                f'<p class="lede">About your {esc(sku.name if sku else o["sku"])}.'
                f' A few words is plenty &mdash; sold, still listed, withdrawn, '
                f'and roughly how long it took.</p>'
                f'<form method="post" action="/o/{esc(order_id)}">'
                f'<label>What happened?</label>'
                f'<input name="reply" autocomplete="off" autofocus '
                f'placeholder="sold in about 3 weeks">'
                f'<button>Send</button></form>'
                f'<p class="note">No account needed. We use it to work out which '
                f'briefs sell faster, and everyone who answers gets the benefit '
                f'of every other answer.</p>')
        return render_page(request, "Did it sell?", body, narrow=True)

    @app.post("/o/{order_id}")
    def outcome_save(request: Request, order_id: str, reply: str = Form("")):
        try:
            limits.hit(db, "outcome", order_id, limits.Limit(5, 3600))
            outcomes.record(db, order_id, reply)
        except (outcomes.OutcomeError, limits.TooMany):
            return Response("Not found", status_code=404)
        return RedirectResponse(f"/o/{order_id}?done=1", 303)

    @app.post("/admin/ask")
    def admin_ask(request: Request, csrf: str = Form("")):
        """Send the outstanding "did it sell?" asks. Operator-triggered rather
        than a cron: the batch is small, it costs nothing to hold, and a human
        pressing a button cannot mail two hundred people at 4am by accident."""
        if not is_operator(request) or not check_csrf(request, csrf):
            return Response("Not found", status_code=404)
        sent = 0
        for oid in outcomes.due(db):
            o = orders.get(db, oid)
            sku = cat.skus().get(o["sku"])
            if notify.outcome_request(db, mailer, s, oid,
                                      what=(sku.name if sku else o["sku"])):
                outcomes.mark_asked(db, oid)
                sent += 1
        with db.tx() as c:
            db.log(c, "outcome.asked_batch", "", str(sent))
        return RedirectResponse("/admin/queue", 303)

    # ---------------------------------------------------------------- admin
    @app.get("/admin/queue", response_class=HTMLResponse)
    def admin_queue(request: Request):
        if not is_operator(request):
            # 404, not 403. A 403 tells an unauthorised reader that an operator
            # console exists at this path and is worth attacking.
            return Response("Not found", status_code=404)
        with db.tx() as c:
            jobs = c.execute(
                "SELECT j.*, o.sku, o.status ostatus FROM jobs j"
                " JOIN orders o ON o.id=j.order_id"
                " ORDER BY j.queued_at DESC LIMIT 50").fetchall()
        rows = "".join(
            f'<tr><td class="k">{esc(j["order_id"])}</td><td>{esc(j["sku"])}</td>'
            f'<td>{status_pill(j["status"])}</td><td>{j["attempts"]}</td>'
            f'<td class="note">{esc(j["error"][:80])}</td></tr>' for j in jobs)
        summ = outcomes.summary(db)
        pending = len(outcomes.due(db))
        body = (f'<h1>Queue</h1><p class="lede">{esc(worker.stats())}</p>'
                f'<table><tr><th>Order</th><th>SKU</th><th>Job</th>'
                f'<th>Tries</th><th>Error</th></tr>{rows}</table>'
                f'<h2>Outcomes</h2>'
                f'<div class="grid">'
                f'<div class="stat"><div class="big">{summ["answered"]}</div>'
                f'<div class="l">Answered</div></div>'
                f'<div class="stat"><div class="big">'
                f'{summ["response_rate"]:.0%}</div>'
                f'<div class="l">Response rate</div></div>'
                f'<div class="stat"><div class="big">{pending}</div>'
                f'<div class="l">Ready to ask</div></div></div>'
                f'<form method="post" action="/admin/ask">'
                f'{csrf_field(request)}'
                f'<button>Ask the {pending} due</button></form>')
        return render_page(request, "Queue", body)

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "queue": worker.stats()}

    return app
