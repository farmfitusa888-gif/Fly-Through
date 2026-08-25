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
from starlette.concurrency import run_in_threadpool

from . import (auth, catalog_bridge as cat, limits, manual, notify, orders,
               outcomes, payments, render, reseller, turnaround)
from .config import Settings, load
from .db import Database, new_id, now
from .mail import Mailer
from .queue import SHORT_DELIVERY, Worker
from .storage import Store, UploadRejected
from .ui import esc, flash, money, page, status_pill

SESSION_COOKIE = "ft_session"
REFERRAL_COOKIE = "ft_ref"


def default_renderer(*, order_id, vertical, slug, originals, out_dir, brief,
                     placement, originals_url="", tempo="tour", max_seconds=None):
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
                        submit=submit, poll=poll, tempo=tempo,
                        max_seconds=max_seconds,
                        originals_url=originals_url)


def provider_from_env(model: str = "wan2-7", mode: str = "image2video"):
    """(submit, poll) for the configured render provider.

    One small seam, because the provider is the single most likely thing in this
    system to change: the moment a model with better dual-frame anchoring ships,
    we move. Nothing above this function knows the vendor.

    FLYTHROUGH_PROVIDER  path to a connection profile (JSON)
    FLYTHROUGH_PROVIDER_TOKEN  the credential, environment only, never on disk

    The endpoint and response paths come from the operator's own provider
    account. They are not guessed here: inventing a URL produces a component
    that looks finished, passes review, and fails the first time real money is
    behind it.
    """
    import os
    import sys
    root = Path(__file__).resolve().parents[2]
    if str(root / "pipeline") not in sys.path:
        sys.path.insert(0, str(root / "pipeline"))
    from flythrough.providers.http import Connection, make

    profile = os.environ.get("FLYTHROUGH_PROVIDER", "").strip()
    token = os.environ.get("FLYTHROUGH_PROVIDER_TOKEN", "").strip()
    if not profile:
        raise RuntimeError(
            "no render provider configured. Set FLYTHROUGH_PROVIDER to a "
            "connection profile (see pipeline/flythrough/providers/"
            "connection.example.json), or pass renderer= to create_app().")
    if not token:
        raise RuntimeError(
            "FLYTHROUGH_PROVIDER_TOKEN is not set. The credential belongs in "
            "the environment, never in the profile on disk.")
    if not Path(profile).is_file():
        raise RuntimeError(f"provider profile not found: {profile}")
    return make(Connection.from_file(profile, token), model=model, mode=mode)


def safe_next(target: str) -> str:
    """Where a sign-in may send someone. Strict allow-shape, not a blocklist.

    `startswith("/")` is not enough and was the bug: "//evil.com" passes it,
    and a browser reads a protocol-relative URL as an absolute one. So an
    attacker could mail a victim /login?next=//evil.com, the victim signs in
    with us, and lands on the attacker's page still believing they are on
    ours -- a credible phishing hop wearing our domain.

    Backslashes are rejected too: some browsers normalise "/\\evil.com" to
    the same thing.
    """
    t = (target or "").strip()
    if (not t.startswith("/") or t.startswith("//") or t.startswith("/\\")
            or "\\" in t or "\n" in t or "\r" in t):
        return "/orders"
    return t


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

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        """Set on every response, including errors and file downloads.

        The static site gets these from _headers, which the app never sees --
        so without this middleware every page the customer actually transacts
        on was the one without protection.

        The CSP uses a per-response nonce rather than 'unsafe-inline'. A policy
        with unsafe-inline stops almost nothing, and the entire reason to have
        one is that an escaping mistake somewhere else does not become script
        execution.
        """
        request.state.nonce = secrets.token_urlsafe(16)
        response = await call_next(request)
        n = request.state.nonce
        response.headers.setdefault("Content-Security-Policy", "; ".join([
            "default-src 'self'",
            f"script-src 'nonce-{n}'",
            f"style-src 'nonce-{n}' https://fonts.googleapis.com",
            "font-src https://fonts.gstatic.com",
            "img-src 'self' data:",
            # Payment leaves for Stripe's own checkout; nothing posts anywhere else.
            "form-action 'self' https://buy.stripe.com https://checkout.stripe.com",
            "frame-ancestors 'none'",     # nothing here should ever be framed
            "base-uri 'none'",
            "object-src 'none'",
        ]))
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy",
                                    "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=(self)")
        if not s.dev_mode:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains")
        return response
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
                                 here=request.url.path, narrow=narrow,
                                 nonce=getattr(request.state, "nonce", "")))

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

    @app.get("/order")
    def start_order_get(request: Request, sku: str = "", ref: str = ""):
        """Entry point from the marketing site: /order?sku=... in a link.

        A GET because it arrives as an href from a static page that has no
        session and no CSRF token to give. It creates nothing on its own -- it
        sends the visitor to sign in, and the POST on the other side is what
        makes the order. A GET that created a paid-for object would be a URL a
        crawler could fire.
        """
        try:
            cat.get(sku)
        except cat.UnknownSku:
            return RedirectResponse("/", 303)
        p = who(request)
        if p is None or p.customer_id is None:
            resp = RedirectResponse(f"/login?next=/order%3Fsku%3D{quote(sku)}", 303)
            if ref:
                resp.set_cookie(REFERRAL_COOKIE, ref[:16].upper(),
                                max_age=90 * 86400, httponly=True, samesite="lax")
            return resp
        oid = orders.create(db, p.customer_id, sku)
        return RedirectResponse(f"/shoot/{oid}", 303)

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
               f'<p><a href="/shoot/{esc(order_id)}">Shooting it now? '
               f'Open the shot list on your phone →</a></p>'
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
                     csrf: str = Form(""), slot: str = Form("")):
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
                           # A slot chosen on the shoot page beats a filename:
                           # a phone names everything IMG_4417.jpg, which
                           # resolves to nothing useful.
                           (slot if slot in mod.TOUR_ORDER
                            else mod.resolve(Path(f.filename or "").stem).key),
                           pos, now()))
            added += 1
        if not added and not errs:
            # A POST that carried no file at all. It used to return 303 with no
            # row created and nothing said, so a customer whose picker was
            # cancelled -- or whose browser dropped the attachment -- saw a page
            # that looked like it had worked and was missing a shot. Silence is
            # the worst possible answer here: they only find out at the gate.
            errs.append("no photograph came through — tap the row and pick again")
        q = f"?msg={quote(f'{added} added')}" if added else ""
        if errs:
            q = f"?err={quote('; '.join(errs[:3]))}"
        back = str(request.headers.get("referer", ""))
        if "/shoot/" in back:
            # On the shot list the green tick already says it landed. A banner
            # saying "1 added" on top of that is noise on a small screen, and it
            # pushes the thing you came to read off the top.
            return RedirectResponse(
                f"/shoot/{order_id}" + (f"?err={quote('; '.join(errs[:3]))}"
                                        if errs else ""), 303)
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
        target = safe_next(next)
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

    # ---------------------------------------------------------------- shoot
    # Plain-English labels and a one-line instruction per slot, taken from the
    # same guides the client gets. Only the slots worth prompting for on site --
    # a phone screen with twenty rows is a screen nobody scrolls.
    SHOOT_LIST = {
        "rooms": [
            ("exterior", "Front of the house",
             "Square to the front, camera level. Do not tilt up."),
            ("living", "Main living room",
             "Stand in the doorway you came in by, far side of the room in frame."),
            ("kitchen", "Kitchen",
             "Island or main counter, and the way through to the next room."),
            ("entry", "Entry or hallway", "Just inside the front door, looking in."),
            ("dining", "Dining", "Table framed, doorway behind you."),
            ("primary_bed", "Primary bedroom", "From the doorway. Bed and window together."),
            ("primary_bath", "Primary bathroom", "From the doorway. Stay out of the mirror."),
            ("patio", "Patio or deck",
             "Stand on the lawn looking BACK at the house."),
            ("yard", "Yard", "Shoot toward the house so the yard reads as belonging to it."),
            ("aerial", "Aerial (optional)",
             "Must be over the SAME side as your last outdoor shot."),
        ],
        "vehicles": [
            ("hero", "Three-quarter front",
             "Front corner, camera at headlight height, wheels turned slightly toward you."),
            ("dash", "Dashboard", "From the driver's headrest. Screen and gauges in frame."),
            ("front_seats", "Front seats", "From the open driver's door."),
            ("front", "Nose", "Square to the grille, camera level."),
            ("driver_side", "Driver side", "Square to the middle, bumper to bumper."),
            ("rear", "Back", "Square to the tailgate."),
            ("passenger_side", "Passenger side", "Same as driver side, other face."),
            ("wheels", "One wheel", "Crouch. Caliper and badge visible."),
            ("engine", "Engine bay", "Hood fully up, shot from the front corner."),
            ("rear_seats", "Back seats",
             "From the open rear door. Seat backs and legroom visible."),
            ("door_open", "Driver's door open",
             "From outside looking in. This is what carries the camera inside."),
            ("infotainment", "Centre screen", "Screen ON, home screen showing."),
            ("cargo", "Trunk, bed or cargo", "Open, square from behind."),
            ("odometer", "Odometer", "Ignition on so the number is lit."),
        ],
        "products": [
            ("hero", "Three-quarter beauty shot", "Turned slightly so two faces show."),
            ("detail", "One close detail", "Fill the frame with the part you are proud of."),
            ("scale", "Beside something known",
             "A hand, a phone, a coin — anything a buyer knows the size of."),
            ("front", "Front", "Dead square, centred, camera at mid-height."),
            ("side", "Side", "Dead square from one side."),
            ("back", "Back", "Dead square from behind."),
            ("top", "From above", "Directly overhead."),
            ("material", "The surface", "Rake the light across it, do not flatten it."),
            ("open", "Opened", "Lid off, unfolded, unzipped."),
            ("colorway", "Other finishes", "Same angle as the hero, each finish."),
            ("packaging", "The box", "As it arrives."),
        ],
    }

    @app.get("/shoot/{order_id}", response_class=HTMLResponse)
    def shoot(request: Request, order_id: str, msg: str = "", err: str = ""):
        """The shot list, on the phone, while the photographer is still there.

        Every quality problem this project has hit traces to the source set: an
        aerial framed over the wrong side, a missing bridge between the front and
        the back, a dark infotainment screen. The guides are good and are read
        the night before. A check that runs at the moment of capture is worth far
        more, because a re-shoot is free while you are standing in the room and
        impossible once you have driven away.
        """
        p = who(request)
        if p is None or p.customer_id is None:
            return RedirectResponse(f"/login?next=/shoot/{order_id}", 303)
        o = orders.get(db, order_id, customer_id=p.customer_id)
        if o is None:
            return render_page(request, "Not found", "<h1>Not found.</h1>",
                               narrow=True)
        if o["status"] not in ("draft", "awaiting_payment"):
            return RedirectResponse(f"/order/{order_id}", 303)

        with db.tx() as c:
            ups = c.execute("SELECT room_key, filename FROM uploads"
                            " WHERE order_id=? ORDER BY position",
                            (order_id,)).fetchall()
        have = {u["room_key"] for u in ups}
        needed = render.required_anchors(o["vertical"])
        prep = render.prepare(o["vertical"], [
            {"filename": u["filename"], "path": "", "room_key": u["room_key"],
             "position": i} for i, u in enumerate(ups, 1)])

        # The curated list is a subset on purpose -- a phone screen with twenty
        # rows is a screen nobody scrolls. But a customer who followed the guide
        # and took a shot we did not prompt for must still be able to send it,
        # so the list ends with a catch-all that classifies by filename. Without
        # it, "which shots can I upload" and "which shots did we ask for" are
        # two different lists, and only one of them is written down.
        rows = []
        for key, label, howto in SHOOT_LIST[o["vertical"]]:
            done = key in have
            req = key in needed
            tick = "✓" if done else ("●" if req else "")
            cls = "shot done" if done else ("shot need" if req else "shot")
            rows.append(
                f'<li class="{cls}">'
                f'<div class="hd"><span class="tick">{tick}</span>'
                f'<strong>{esc(label)}</strong>'
                f'{" <em>required</em>" if req and not done else ""}</div>'
                f'<p>{esc(howto)}</p>'
                f'<form method="post" action="/order/{esc(order_id)}/upload" '
                f'enctype="multipart/form-data">{csrf_field(request)}'
                f'<input type="hidden" name="slot" value="{esc(key)}">'
                f'<input type="file" name="files" accept="image/*" '
                f'capture="environment" data-autosubmit>'
                f'</form></li>')

        rows.append(
            f'<li class="shot">'
            f'<div class="hd"><span class="tick"></span><strong>Anything else</strong>'
            f'</div>'
            f'<p>A shot from the guide we did not ask for above. Name the file '
            f'after what it is and we will file it correctly.</p>'
            f'<form method="post" action="/order/{esc(order_id)}/upload" '
            f'enctype="multipart/form-data">{csrf_field(request)}'
            f'<input type="file" name="files" accept="image/*" multiple '
            f'data-autosubmit></form></li>')

        missing = [k for k in needed if k not in have]
        if missing:
            state = (f'<div class="flash err">Still needed: '
                     f'{esc(", ".join(m.replace("_", " ") for m in missing))}</div>')
        elif prep.warnings:
            state = ('<div class="flash err">'
                     + "<br>".join(esc(w) for w in prep.warnings) + "</div>")
        else:
            state = ('<div class="flash ok">Every required shot is in, and the '
                     'set holds together. You can leave.</div>')

        body = (f'{flash(err) or flash(msg, "ok")}{state}'
                f'<p class="kicker">On site</p><h1>Shot list</h1>'
                f'<p class="lede">Tap a row to take that shot. It uploads as you '
                f'go and this page tells you what is still missing — while you '
                f'can still walk back and get it.</p>'
                f'<ul class="shots">{"".join(rows)}</ul>'
                f'<p><a class="btn ghost" href="/order/{esc(order_id)}">'
                f'Finish the brief →</a></p>')
        return render_page(request, "Shot list", body, narrow=True)

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

    @app.get("/admin/payouts", response_class=HTMLResponse)
    def admin_payouts(request: Request):
        if not is_operator(request):
            return Response("Not found", status_code=404)
        floor = int(s.payout_minimum_usd * 100)
        owed = reseller.payable(db, payout_minimum_cents=floor)
        rows = "".join(
            f'<tr><td class="k">{esc(r["name"])}</td>'
            f'<td class="mono">{esc(r["email"])}</td>'
            f'<td class="mono">{esc(r["code"])}</td>'
            f'<td>{r["n"]}</td>'
            f'<td>{esc(money(r["owed"]))}</td>'
            f'<td><form method="post" action="/admin/payouts">'
            f'{csrf_field(request)}'
            f'<input type="hidden" name="reseller_id" value="{esc(r["id"])}">'
            f'<input name="reference" placeholder="bank ref" '
            f'style="margin:0 0 8px">'
            f'<button>Mark paid</button></form></td></tr>' for r in owed)
        total = sum(r["owed"] for r in owed)
        body = (f'<h1>Payouts</h1>'
                f'<p class="lede">Everyone over the '
                f'{esc(money(floor))} minimum. Pay them by bank transfer, then '
                f'record it here — this is the ledger, not the payment rail.</p>'
                + (f'<table><tr><th>Partner</th><th>Email</th><th>Code</th>'
                   f'<th>Orders</th><th>Owed</th><th></th></tr>{rows}</table>'
                   f'<p class="note">Total outstanding {esc(money(total))}.</p>'
                   if owed else '<p class="note">Nobody is over the minimum.</p>'))
        return render_page(request, "Payouts", body)

    @app.post("/admin/payouts")
    def admin_pay(request: Request, reseller_id: str = Form(...),
                  reference: str = Form(""), csrf: str = Form("")):
        if not is_operator(request) or not check_csrf(request, csrf):
            return Response("Not found", status_code=404)
        paid = reseller.mark_paid(db, reseller_id, reference=reference[:80])
        if paid:
            with db.tx() as c:
                row = c.execute("SELECT email FROM resellers WHERE id=?",
                                (reseller_id,)).fetchone()
            if row:
                mailer.send(row["email"], f"{s.brand} — commission paid",
                            f"${paid / 100:,.2f} is on its way to you"
                            + (f" (ref {reference[:80]})." if reference else ".")
                            + f"\n\nYour ledger: {s.base_url}/partner\n")
        return RedirectResponse("/admin/payouts", 303)

    @app.get("/admin/order/{order_id}", response_class=HTMLResponse)
    def admin_order(request: Request, order_id: str, err: str = "", msg: str = ""):
        """The render sheet, for working an order by hand.

        This is how the service earns its keep before any provider integration
        exists: the order, the plan, the exact prompts and the cost, on one
        page. The operator renders through the tools they already have and
        uploads the clips here.
        """
        if not is_operator(request):
            return Response("Not found", status_code=404)
        try:
            brief = manual.build(db, s.data_dir, order_id)
        except manual.NotReady as e:
            return render_page(request, "Not ready",
                               f"<h1>Not ready</h1><p>{esc(e)}</p>"
                               f'<p><a href="/admin/queue">Back to the queue</a></p>',
                               narrow=True)
        o = orders.get(db, order_id)
        def settings_rows(sh):
            """Field name, the value to set, and where the form disagrees.

            Read from the provider's own recorded schema, so these are the
            actual defaults the operator is typing over rather than what the
            defaults were the day this page was written.
            """
            return "".join(
                f'<tr><td class="mono">{esc(f["field"])}</td>'
                f'<td class="mono"><strong>{esc(f["value"])}</strong></td>'
                f'<td class="note">'
                + (f'form defaults to {esc(f["default"])}' if f["differs"]
                   else '&mdash;')
                + '</td></tr>' for f in sh["settings"])

        shots = "".join(
            f'<div class="card plain"><h3>Shot {sh["n"]} &middot; '
            f'{esc(sh["from"])} &rarr; {esc(sh["to"])}</h3>'
            f'<p class="mono">{esc(sh["move"])}</p>'
            f'<div class="setme"><div class="big">{sh["seconds"]}s</div>'
            f'<div class="l">{esc(brief.duration_field)} &middot; '
            f'{sh["credits"]} credits &middot; '
            f'{esc("$%.2f" % sh["usd"])}</div></div>'
            + (f'<table class="fields"><tbody>{settings_rows(sh)}</tbody>'
               f'</table>' if sh["settings"] else "")
            + f'<p class="mono">start &nbsp;{esc(sh["start_frame"])}<br>'
            f'end &nbsp;&nbsp;&nbsp;{esc(sh["end_frame"])}</p>'
            f'<p><strong>Prompt</strong><br>{esc(sh["prompt"])}</p>'
            f'<p class="note"><strong>Negative</strong><br>'
            f'{esc(sh["negative_prompt"])}</p></div>' for sh in brief.shots)

        # Before the prompts, not after them. The failure this prevents is an
        # operator working down the sheet on the provider's defaults: wan2-7
        # defaults duration to 5s and resolution to 720p, says nothing, bills
        # normally, and the short clips are only caught by the delivery gate --
        # by which point the credits are gone.
        lengths = " &middot; ".join(
            f'<span class="mono">#{sh["n"]} <strong>{sh["seconds"]}s</strong>'
            f'</span>' for sh in brief.shots)
        setup = (
            f'<div class="card warn"><h3>Set the length on every shot</h3>'
            f'<p>{lengths}</p>'
            f'<p>Total <strong>{brief.total_seconds}s</strong> across '
            f'{len(brief.shots)} shots, at '
            f'<span class="mono">{esc(brief.tempo)}</span> tempo on '
            f'<span class="mono">{esc(brief.model)}</span> at '
            f'<span class="mono">{esc(brief.tier)}</span>'
            + (f' &mdash; sold as <strong>{brief.sold_seconds}s</strong>'
               if brief.sold_seconds else '') + '.</p>'
            + (f'<p class="note">The provider\'s '
               f'<span class="mono">{esc(brief.duration_field)}</span> field '
               f'takes a whole number of seconds, {brief.duration_min}&ndash;'
               f'{brief.duration_max}, and defaults to 5. It will not tell you '
               f'that is wrong.</p>' if brief.duration_max else "")
            + f'<p class="note">A delivery that comes back under '
              f'{int(SHORT_DELIVERY * 100)}% of {brief.total_seconds}s is '
              f'refused on upload, so a shot rendered at the default is '
              f'credits spent for nothing.</p></div>')

        blocked = ("".join(f'<li><span>{esc(b)}</span></li>' for b in brief.blocks))
        warn = ("".join(f'<li><span>{esc(w)}</span></li>' for w in brief.warnings))
        gate = (f'<div class="flash err">Do not render. The shot set cannot be '
                f'filmed:<ul class="plain">{blocked}</ul></div>' if brief.blocks
                else "")

        body = (
            f'{flash(err) or flash(msg, "ok")}{gate}'
            f'<p class="kicker">Render sheet</p><h1>{esc(brief.listing)}</h1>'
            f'<div class="grid">'
            f'<div class="stat"><div class="big">{len(brief.shots)}</div>'
            f'<div class="l">Shots</div></div>'
            f'<div class="stat"><div class="big">{brief.total_seconds}s</div>'
            f'<div class="l">Runtime</div></div>'
            f'<div class="stat"><div class="big">{brief.credits}</div>'
            f'<div class="l">Credits (est.)</div></div>'
            f'<div class="stat"><div class="big">'
            f'{esc("$%.2f" % brief.usd)}</div>'
            f'<div class="l">Cost (est.)</div></div></div>'
            + (f'<div class="card"><h3>Check before rendering</h3>'
               f'<ul class="plain">{warn}</ul></div>' if warn else "")
            + setup
            + f'<div class="card"><h3>Originals</h3>'
              f'<p class="mono">{esc(brief.originals_dir)}</p>'
              f'<p class="note">Upload these to the provider first. The anchor '
              f'frames must be the customer\'s own files &mdash; anything '
              f're-rendered is no longer an original, and the disclosure page '
              f'stops being true.</p>'
              f'<p><a href="/admin/order/{esc(order_id)}/sheet.txt">'
              f'Plain-text render sheet &rarr;</a></p></div>'
            + shots
            + f'<div class="card"><h3>Finished clips</h3>'
              f'<p>Upload every rendered shot. Name them so the shot number is '
              f'recoverable &mdash; <span class="mono">shot_01.mp4</span> and so '
              f'on. The order is delivered and the customer emailed when they '
              f'all land.</p>'
              f'<form method="post" action="/admin/order/{esc(order_id)}/clips" '
              f'enctype="multipart/form-data">{csrf_field(request)}'
              f'<input type="file" name="files" multiple accept="video/*">'
              f'<button>Deliver {len(brief.shots)} clips</button></form></div>'
              f'<p class="note"><a href="/admin/queue">&larr; Queue</a> &middot; '
              f'status {status_pill(o["status"])}</p>')
        return render_page(request, "Render sheet", body)

    @app.get("/admin/order/{order_id}/sheet.txt")
    def admin_sheet(request: Request, order_id: str):
        if not is_operator(request):
            return Response("Not found", status_code=404)
        try:
            return Response(manual.as_text(manual.build(db, s.data_dir, order_id)),
                            media_type="text/plain; charset=utf-8")
        except manual.NotReady as e:
            return Response(str(e), status_code=409)

    @app.post("/admin/order/{order_id}/clips")
    async def admin_clips(request: Request, order_id: str,
                          files: list[UploadFile] = None, csrf: str = Form("")):
        """Accept operator-rendered clips and finish the order.

        Assembly runs through the SAME deliver() the automatic path uses, so a
        hand-worked order and a machine-worked one produce an identical file.
        """
        if not is_operator(request) or not check_csrf(request, csrf):
            return Response("Not found", status_code=404)
        if not files:
            return RedirectResponse(
                f"/admin/order/{order_id}?err={quote('no clips came through')}", 303)
        work = render.output_dir(s.data_dir, order_id) / "clips"
        work.mkdir(parents=True, exist_ok=True)
        saved = []
        for f in sorted(files, key=lambda x: x.filename or ""):
            name = Path(f.filename or "clip.mp4").name
            if not name.lower().endswith((".mp4", ".mov", ".m4v", ".webm")):
                continue
            dest = work / name
            dest.write_bytes(await f.read())
            saved.append(dest)
        if not saved:
            return RedirectResponse(
                f"/admin/order/{order_id}?err={quote('no video files in that upload')}",
                303)
        try:
            # ffmpeg, off the event loop. Assembling a five-shot film takes the
            # better part of a minute; run inline in an async route it does not
            # just hang the operator's tab, it stops the whole process answering
            # anything -- checkout, magic links, Stripe's webhook -- until the
            # last encode lands. Measured at 67s on a real four-clip delivery,
            # during which /healthz timed out.
            await run_in_threadpool(worker.deliver_manual, order_id, saved)
        except Exception as exc:                              # noqa: BLE001
            return RedirectResponse(
                f"/admin/order/{order_id}?err={quote(str(exc)[:160])}", 303)
        return RedirectResponse(
            f"/admin/order/{order_id}?msg={quote('delivered')}", 303)

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
            f'<td class="note">{esc(j["error"][:60])}</td>'
            f'<td><a href="/admin/order/{esc(j["order_id"])}">Render sheet</a>'
            f'</td></tr>' for j in jobs)
        summ = outcomes.summary(db)
        pending = len(outcomes.due(db))
        # The provider-switch trigger, as a number rather than an intention.
        # business/12-render-provider.md says to buy an automatic renderer when
        # the operator becomes the reason a delivery is late; this is where that
        # stops being a judgement call.
        ta = turnaround.measure(db)
        late = (f'<div class="stat"><div class="big">{ta.overdue_now}</div>'
                f'<div class="l">Overdue now</div></div>' if ta.waiting else "")
        turn = (f'<h2>Turnaround</h2>'
                f'<p class="lede">{esc(ta.headline)}</p>'
                f'<div class="grid">'
                f'<div class="stat"><div class="big">'
                f'{esc("%.1fh" % ta.median_hours)}</div>'
                f'<div class="l">Median paid &rarr; delivered</div></div>'
                f'<div class="stat"><div class="big">'
                f'{esc("%.1fh" % ta.slowest_hours)}</div>'
                f'<div class="l">Slowest of {ta.delivered}</div></div>'
                f'<div class="stat"><div class="big">{ta.waiting}</div>'
                f'<div class="l">Waiting'
                + (f' &middot; oldest {ta.oldest_waiting_hours:.0f}h'
                   if ta.waiting else "")
                + f'</div></div>{late}</div>'
                f'<p class="note">Measured against each SKU\'s own turnaround '
                f'promise, the one next to the money in the catalogue.</p>')
        body = (f'<h1>Queue</h1><p class="lede">{esc(worker.stats())}</p>'
                f'<table><tr><th>Order</th><th>SKU</th><th>Job</th>'
                f'<th>Tries</th><th>Error</th><th></th></tr>{rows}</table>'
                + turn
                + f'<h2>Outcomes</h2>'
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
                f'<button>Ask the {pending} due</button></form>'
                f'<p class="note"><a href="/admin/payouts">Partner payouts →</a></p>')
        return render_page(request, "Queue", body)

    @app.get("/o/{order_id}/originals", response_class=HTMLResponse)
    def originals_page(request: Request, order_id: str):
        """The artefact Bus. & Prof. Code s.10140.8 requires a link TO.

        Public and unauthenticated on purpose: a disclosure link a regulator or
        a buyer cannot open is not a disclosure. It carries the address and the
        photographs, and nothing about the customer as a person.

        Only for verticals that carry the duty. A vehicle or product order has
        no altered-image rule to satisfy and gets a 404 rather than publishing
        someone's photographs for no reason.
        """
        o = orders.get(db, order_id)
        if o is None or o["vertical"] != "rooms":
            return Response("Not found", status_code=404)
        if o["status"] not in ("delivered", "refunded"):
            # Before delivery there is nothing to disclose, and publishing an
            # address for an order that was never paid for would be worse.
            return Response("Not found", status_code=404)
        page_path = render.output_dir(s.data_dir, order_id) / "delivery" / "originals.html"
        if not page_path.is_file():
            return Response("Not found", status_code=404)
        return HTMLResponse(page_path.read_text())

    @app.get("/o/{order_id}/originals/{name}")
    def originals_file(request: Request, order_id: str, name: str):
        o = orders.get(db, order_id)
        if o is None or o["vertical"] != "rooms" or o["status"] not in (
                "delivered", "refunded"):
            return Response("Not found", status_code=404)
        # A public route that joins a user-supplied name onto a path is exactly
        # how one becomes an arbitrary file read. Two independent checks,
        # because the first alone was only safe by accident: Path("..").name is
        # ".." , not "", and it passed the basename test -- it was the later
        # is_file() on a directory that happened to stop it.
        root = (render.output_dir(s.data_dir, order_id) / "originals").resolve()
        if name != Path(name).name or name in ("", ".", "..") or "%" in name:
            return Response("Not found", status_code=404)
        f = (root / name).resolve()
        # The decisive check: wherever the join landed, it must be inside root.
        if not f.is_file() or root not in f.parents:
            return Response("Not found", status_code=404)
        return FileResponse(f)

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "queue": worker.stats()}

    return app
