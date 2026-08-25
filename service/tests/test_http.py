"""End-to-end tests through the real ASGI app.

These drive HTTP, not functions: the routing, the cookies, the CSRF checks and
the redirects are the parts most likely to be wrong, and calling the handlers
directly would skip every one of them.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "service"))

from flythrough_service import payments  # noqa: E402
from flythrough_service.app import SESSION_COOKIE, create_app  # noqa: E402
from flythrough_service.config import load  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 8192
SECRET = "whsec_test"


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("FLYTHROUGH_SECRET_KEY", "test-key")
    s = load(data_dir=tmp_path, dev=True)
    rendered = []

    def renderer(*, out_dir, slug, **kw):
        rendered.append(slug)
        m = Path(out_dir) / f"{slug}_master.mp4"
        m.write_bytes(b"video-bytes")
        return [("master", m)]

    a = create_app(s, renderer=renderer)
    a.state.rendered = rendered
    return a


@pytest.fixture()
def client(app):
    return TestClient(app)


def sign_in(client, app, email="agent@example.com") -> str:
    client.post("/login", data={"email": email}, follow_redirects=False)
    token = None
    for m in app.state.mailer.outbox():
        if m.to == email and "token=" in m.body:
            token = m.body.split("token=")[1].split("&")[0].split()[0]
    assert token, "no login link was sent"
    r = client.get(f"/auth?token={token}", follow_redirects=False)
    assert r.status_code == 303
    return client.cookies.get(SESSION_COOKIE)


def csrf_of(client, app, path):
    html = client.get(path).text
    marker = 'name="csrf" value="'
    assert marker in html, f"no csrf field on {path}"
    return html.split(marker)[1].split('"')[0]


# ------------------------------------------------------------------ basics


def test_health(client):
    assert client.get("/healthz").json()["ok"] is True


def test_catalogue_lists_every_sellable_sku_at_the_model_price(client):
    """Every SKU appears, grouped under its vertical, at the price the model
    says. A SKU missing here is one nobody can buy; a price that disagrees with
    the model is the worst bug this system could have."""
    from flythrough_service import catalog_bridge as cat
    from flythrough_service.ui import money
    body = client.get("/").text
    for sku in cat.skus().values():
        assert sku.name.replace(" - ", " — ") in body, f"{sku.id} is not on the shop"
        assert money(cat.price_cents(sku.id)) in body, f"{sku.id} price missing"
    for heading in ("Property", "Vehicles", "Product"):
        assert f">{heading}<" in body, f"no {heading} section"


def test_dashboard_requires_a_session(client):
    r = client.get("/orders", follow_redirects=False)
    assert r.status_code == 303 and "/login" in r.headers["location"]


def test_no_api_docs_are_exposed(client):
    """An auto-generated schema is a map of every endpoint, for free."""
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


# -------------------------------------------------------------------- auth


def test_magic_link_signs_you_in(client, app):
    assert sign_in(client, app)
    assert client.get("/orders").status_code == 200


def test_a_used_link_will_not_sign_you_in_twice(client, app):
    client.post("/login", data={"email": "a@b.com"})
    tok = app.state.mailer.outbox()[-1].body.split("token=")[1].split("&")[0].split()[0]
    client.get(f"/auth?token={tok}", follow_redirects=False)
    client.cookies.clear()
    r = client.get(f"/auth?token={tok}", follow_redirects=False)
    assert "/login?err" in r.headers["location"]


def test_session_cookie_is_httponly(client, app):
    client.post("/login", data={"email": "a@b.com"})
    tok = app.state.mailer.outbox()[-1].body.split("token=")[1].split("&")[0].split()[0]
    r = client.get(f"/auth?token={tok}", follow_redirects=False)
    assert "httponly" in r.headers["set-cookie"].lower()


def test_logout_ends_the_session(client, app):
    sign_in(client, app)
    client.post("/logout", follow_redirects=False)
    assert client.get("/orders", follow_redirects=False).status_code == 303


# ------------------------------------------------------------- order flow


def start_order(client, sku="re-listing-pro") -> str:
    r = client.post("/order", data={"sku": sku}, follow_redirects=False)
    assert r.status_code == 303
    return r.headers["location"].rsplit("/", 1)[1]


def test_the_whole_purchase(client, app):
    """Upload, brief, pay, render, download -- the actual product."""
    sign_in(client, app)
    oid = start_order(client)
    path = f"/order/{oid}"

    csrf = csrf_of(client, app, path)
    files = [("files", (f"{i:02d}_{n}.jpg", io.BytesIO(JPEG + bytes([i])), "image/jpeg"))
             for i, n in enumerate(["front-elevation", "foyer", "kitchen",
                                    "patio", "rear-aerial"], 1)]
    r = client.post(f"{path}/upload", files=files, data={"csrf": csrf},
                    follow_redirects=False)
    assert r.status_code == 303 and "err" not in r.headers["location"]

    from flythrough_service import catalog_bridge as cat, orders
    qs = cat.intake_for("rooms")
    answers = {f"q{i}": v for i, v in enumerate(
        ["1420 Cedar Ridge Rd", "Cedar Realty", "golden hour"][:len(qs)])}
    answers["csrf"] = csrf
    client.post(f"{path}/brief", data=answers, follow_redirects=False)

    ready = orders.readiness(app.state.db, oid)
    assert ready.ok, ready.problems

    ev = {"id": "evt_1", "type": "checkout.session.completed",
          "data": {"object": {"id": "cs_1", "payment_status": "paid",
                              "amount_total": 24900, "client_reference_id": oid}}}
    raw = json.dumps(ev).encode()
    r = client.post("/webhooks/stripe", content=raw,
                    headers={"stripe-signature": payments.sign(raw, SECRET)})
    assert r.status_code == 200

    assert app.state.worker.run_one() is not None
    assert orders.get(app.state.db, oid)["status"] == "delivered"
    assert app.state.rendered

    dl = client.get(f"/orders/{oid}/file/master")
    assert dl.status_code == 200 and dl.content == b"video-bytes"


def test_you_cannot_pay_before_the_set_is_complete(client, app):
    """The whole point of uploading first."""
    sign_in(client, app)
    oid = start_order(client)
    csrf = csrf_of(client, app, f"/order/{oid}")
    r = client.post(f"/order/{oid}/checkout", data={"csrf": csrf},
                    follow_redirects=False)
    assert "err=" in r.headers["location"]
    from flythrough_service import orders
    assert orders.get(app.state.db, oid)["status"] == "draft"


def test_a_bad_file_is_refused_with_a_readable_reason(client, app):
    sign_in(client, app)
    oid = start_order(client)
    csrf = csrf_of(client, app, f"/order/{oid}")
    r = client.post(f"/order/{oid}/upload",
                    files=[("files", ("cv.pdf", io.BytesIO(b"%PDF-1.4 nope"),
                                      "image/jpeg"))],
                    data={"csrf": csrf}, follow_redirects=False)
    assert "err=" in r.headers["location"]
    assert "photograph" in r.headers["location"] or "cannot" in r.headers["location"]


def test_the_same_photo_twice_is_rejected(client, app):
    sign_in(client, app)
    oid = start_order(client)
    csrf = csrf_of(client, app, f"/order/{oid}")
    for _ in range(2):
        r = client.post(f"/order/{oid}/upload",
                        files=[("files", ("kitchen.jpg", io.BytesIO(JPEG),
                                          "image/jpeg"))],
                        data={"csrf": csrf}, follow_redirects=False)
    assert "already+uploaded" in r.headers["location"].replace("%20", "+")


def test_uploads_without_csrf_are_refused(client, app):
    """Otherwise any page on the internet can post files into someone's order."""
    sign_in(client, app)
    oid = start_order(client)
    r = client.post(f"/order/{oid}/upload",
                    files=[("files", ("k.jpg", io.BytesIO(JPEG), "image/jpeg"))],
                    data={"csrf": "wrong"}, follow_redirects=False)
    assert "err=" in r.headers["location"]
    with app.state.db.tx() as c:
        assert c.execute("SELECT count(*) FROM uploads WHERE order_id=?",
                         (oid,)).fetchone()[0] == 0


def test_one_customer_cannot_open_anothers_order(client, app):
    sign_in(client, app, "first@example.com")
    oid = start_order(client)
    client.cookies.clear()
    sign_in(client, app, "second@example.com")
    assert "Not found" in client.get(f"/order/{oid}").text


def test_one_customer_cannot_download_anothers_file(client, app):
    sign_in(client, app, "first@example.com")
    oid = start_order(client)
    client.cookies.clear()
    sign_in(client, app, "second@example.com")
    assert client.get(f"/orders/{oid}/file/master").status_code == 404


# ---------------------------------------------------------------- webhooks


def test_an_unsigned_webhook_is_rejected(client):
    r = client.post("/webhooks/stripe", content=b'{"id":"evt"}')
    assert r.status_code == 400


def test_a_forged_webhook_is_rejected(client):
    raw = b'{"id":"evt_1","type":"checkout.session.completed"}'
    r = client.post("/webhooks/stripe", content=raw,
                    headers={"stripe-signature": payments.sign(raw, "wrong")})
    assert r.status_code == 400


def test_the_success_page_cannot_mark_an_order_paid(client, app):
    """A redirect is a URL the customer controls. ?paid=1 must be worthless."""
    sign_in(client, app)
    oid = start_order(client)
    client.get(f"/start?order={oid}&paid=1&status=paid")
    from flythrough_service import orders
    assert orders.get(app.state.db, oid)["status"] == "draft"


# ---------------------------------------------------------------- partner


def test_partner_signup_then_ledger(client, app):
    r = client.post("/partner/join",
                    data={"name": "Sam Partner", "email": "sam@partner.com"},
                    follow_redirects=False)
    assert r.status_code == 303 and "done=1" in r.headers["location"]
    sign_in(client, app, "sam@partner.com")
    page = client.get("/partner").text
    with app.state.db.tx() as c:
        code = c.execute("SELECT code FROM resellers").fetchone()["code"]
    assert "Your ledger" in page
    assert code in page, "the partner cannot see the code they were given"
    assert f"/?ref={code}" in page, "no shareable link on the page"
    assert "$0.00" in page, "an empty ledger should read zero, not blank"


def test_a_referred_customer_earns_the_partner_commission(client, app):
    client.post("/partner/join", data={"name": "Sam", "email": "sam@p.com"})
    with app.state.db.tx() as c:
        code = c.execute("SELECT code FROM resellers").fetchone()["code"]
        rid = c.execute("SELECT id FROM resellers").fetchone()["id"]

    client.get(f"/?ref={code}")                 # arrives on the partner link
    sign_in(client, app, "buyer@example.com")
    oid = start_order(client)
    ev = {"id": "e1", "type": "checkout.session.completed",
          "data": {"object": {"id": "cs", "payment_status": "paid",
                              "amount_total": 24900, "client_reference_id": oid}}}
    raw = json.dumps(ev).encode()
    client.post("/webhooks/stripe", content=raw,
                headers={"stripe-signature": payments.sign(raw, SECRET)})

    from flythrough_service import reseller
    led = reseller.ledger(app.state.db, rid, payout_minimum_cents=0)
    assert led.lifetime_cents == 6225


def test_a_customer_is_not_shown_the_partner_ledger(client, app):
    sign_in(client, app, "buyer@example.com")
    r = client.get("/partner", follow_redirects=False)
    assert r.status_code == 303 and "/partner/join" in r.headers["location"]


# ------------------------------------------------------------------ safety


def test_customer_text_is_escaped_not_rendered(client, app):
    """A property address is customer-supplied text on a page we render."""
    sign_in(client, app)
    oid = start_order(client)
    csrf = csrf_of(client, app, f"/order/{oid}")
    client.post(f"/order/{oid}/brief",
                data={"q0": '<script>alert(1)</script>', "q1": "x", "q2": "y",
                      "csrf": csrf}, follow_redirects=False)
    html = client.get(f"/order/{oid}").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# -------------------------------------------------------------- operator only


@pytest.fixture()
def app_with_operator(tmp_path, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("FLYTHROUGH_SECRET_KEY", "test-key")
    monkeypatch.setenv("FLYTHROUGH_OPERATORS", "boss@flythrough.test")
    s = load(data_dir=tmp_path, dev=True)
    return create_app(s, renderer=lambda **kw: [])


def test_a_customer_cannot_read_the_operator_queue(app_with_operator):
    """It lists every order in the system. `require()` only proved someone was
    signed in, which let any customer read the whole book of business."""
    c = TestClient(app_with_operator)
    sign_in(c, app_with_operator, "buyer@example.com")
    assert c.get("/admin/queue").status_code == 404


def test_an_operator_can_read_the_queue(app_with_operator):
    c = TestClient(app_with_operator)
    sign_in(c, app_with_operator, "boss@flythrough.test")
    assert c.get("/admin/queue").status_code == 200


def test_a_signed_out_visitor_gets_404_not_a_redirect(app_with_operator):
    """404, not 403 or a login redirect: both of those confirm an operator
    console exists at this path and is worth attacking."""
    assert TestClient(app_with_operator).get("/admin/queue").status_code == 404


def test_production_with_no_operator_list_admits_nobody(tmp_path, monkeypatch):
    """Empty list must fail closed, not open."""
    for k in ("FLYTHROUGH_OPERATORS",):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("FLYTHROUGH_SECRET_KEY", "k")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "k")
    monkeypatch.setenv("FLYTHROUGH_SMTP_URL", "smtp://x")
    s = load(data_dir=tmp_path, dev=False)
    app = create_app(s, renderer=lambda **kw: [])
    c = TestClient(app)
    # Session made directly: in production the login route sends real mail, and
    # a test must never be one bad env var away from emailing a stranger.
    from flythrough_service import auth
    tok = auth.issue_login_token(app.state.db, "anyone@example.com", ttl_s=600)
    session, _ = auth.redeem_login_token(app.state.db, tok, session_ttl_s=600)
    c.cookies.set(SESSION_COOKIE, session)
    assert auth.resolve_session(app.state.db, session), "session should be valid"
    assert c.get("/admin/queue").status_code == 404


# ---------------------------------------------------------------- notifications


def _pay(client, oid, amount=24900, eid="evt_n"):
    ev = {"id": eid, "type": "checkout.session.completed",
          "data": {"object": {"id": "cs", "payment_status": "paid",
                              "amount_total": amount, "client_reference_id": oid}}}
    raw = json.dumps(ev).encode()
    return client.post("/webhooks/stripe", content=raw,
                       headers={"stripe-signature": payments.sign(raw, SECRET)})


def _subjects(app, to):
    return [m.subject for m in app.state.mailer.outbox() if m.to == to]


def test_the_customer_is_told_when_the_film_is_ready(client, app):
    """The one message the whole service exists to send. Before this, an order
    could complete and the customer would never learn it."""
    email = "agent@example.com"
    sign_in(client, app, email)
    oid = start_order(client)
    csrf = csrf_of(client, app, f"/order/{oid}")
    client.post(f"/order/{oid}/upload", data={"csrf": csrf}, files=[
        ("files", (f"{i:02d}_{n}.jpg", io.BytesIO(JPEG + bytes([i])), "image/jpeg"))
        for i, n in enumerate(["front-elevation", "foyer", "kitchen", "patio"], 1)])
    client.post(f"/order/{oid}/brief", data={
        "q0": "1 Test St", "q1": "Test Realty", "q2": "daylight", "csrf": csrf})
    _pay(client, oid)
    app.state.worker.run_one()

    subs = _subjects(app, email)
    assert any("order received" in s for s in subs), subs
    assert any("your film is ready" in s for s in subs), subs


def test_a_failure_is_admitted_not_hidden(tmp_path, monkeypatch):
    """A customer who has to ask what happened to the film they paid for is
    already a refund."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("FLYTHROUGH_SECRET_KEY", "k")
    s = load(data_dir=tmp_path, dev=True)

    def boom(**kw):
        raise RuntimeError("provider exploded")

    app = create_app(s, renderer=boom)
    c = TestClient(app)
    email = "agent@example.com"
    sign_in(c, app, email)
    oid = start_order(c)
    csrf = csrf_of(c, app, f"/order/{oid}")
    c.post(f"/order/{oid}/upload", data={"csrf": csrf}, files=[
        ("files", (f"{i:02d}_{n}.jpg", io.BytesIO(JPEG + bytes([i])), "image/jpeg"))
        for i, n in enumerate(["front-elevation", "foyer", "kitchen", "patio"], 1)])
    c.post(f"/order/{oid}/brief", data={
        "q0": "1 Test St", "q1": "Test Realty", "q2": "daylight", "csrf": csrf})
    _pay(c, oid)
    from flythrough_service import queue as qq
    for _ in range(qq.MAX_ATTEMPTS + 1):
        app.state.worker.run_one()

    assert any("a problem with your order" in x for x in _subjects(app, email))


def test_a_customer_is_never_told_twice_about_one_order(client, app):
    """Nobody forgives being emailed three times about one order."""
    email = "agent@example.com"
    sign_in(client, app, email)
    oid = start_order(client)
    csrf = csrf_of(client, app, f"/order/{oid}")
    client.post(f"/order/{oid}/upload", data={"csrf": csrf}, files=[
        ("files", (f"{i:02d}_{n}.jpg", io.BytesIO(JPEG + bytes([i])), "image/jpeg"))
        for i, n in enumerate(["front-elevation", "foyer", "kitchen", "patio"], 1)])
    client.post(f"/order/{oid}/brief", data={
        "q0": "1 Test St", "q1": "Test Realty", "q2": "daylight", "csrf": csrf})
    for i in range(4):                       # webhook redelivery storm
        _pay(client, oid, eid=f"evt_{i}")
    app.state.worker.run_one()
    app.state.worker.run_one()

    subs = _subjects(app, email)
    assert sum("order received" in x for x in subs) == 1, subs
    assert sum("your film is ready" in x for x in subs) == 1, subs


def test_a_bounced_notification_cannot_undo_a_delivery(tmp_path, monkeypatch):
    """The film exists either way. A mail failure must not turn a delivered
    order back into a failed one."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("FLYTHROUGH_SECRET_KEY", "k")
    s = load(data_dir=tmp_path, dev=True)

    def renderer(*, out_dir, slug, **kw):
        m = Path(out_dir) / f"{slug}.mp4"
        m.write_bytes(b"v")
        return [("master", m)]

    app = create_app(s, renderer=renderer)

    class Exploding:
        def send(self, *a, **k):
            raise RuntimeError("smtp is on fire")

        def outbox(self):
            return []

    app.state.worker.mailer = Exploding()
    c = TestClient(app)
    sign_in(c, app, "agent@example.com")
    oid = start_order(c)
    csrf = csrf_of(c, app, f"/order/{oid}")
    c.post(f"/order/{oid}/upload", data={"csrf": csrf}, files=[
        ("files", (f"{i:02d}_{n}.jpg", io.BytesIO(JPEG + bytes([i])), "image/jpeg"))
        for i, n in enumerate(["front-elevation", "foyer", "kitchen", "patio"], 1)])
    c.post(f"/order/{oid}/brief", data={
        "q0": "1 Test St", "q1": "Test Realty", "q2": "daylight", "csrf": csrf})
    _pay(c, oid)
    app.state.worker.run_one()

    from flythrough_service import orders
    assert orders.get(app.state.db, oid)["status"] == "delivered"
