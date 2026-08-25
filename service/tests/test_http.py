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


# ------------------------------------------------------------------- limits


def test_login_cannot_be_used_to_mail_bomb_a_stranger(client, app):
    """Without a per-address limit, anyone can post someone else's address in a
    loop and have us mail them repeatedly — a way to get our sending domain
    blocklisted using our own service, aimed at a person who is not a customer."""
    from flythrough_service import limits
    victim = "victim@example.com"
    for _ in range(limits.LOGIN_PER_EMAIL.count):
        client.post("/login", data={"email": victim}, follow_redirects=False)
    r = client.post("/login", data={"email": victim}, follow_redirects=False)
    assert "err=" in r.headers["location"]
    sent = [m for m in app.state.mailer.outbox() if m.to == victim]
    assert len(sent) == limits.LOGIN_PER_EMAIL.count


def test_the_limit_is_per_address_not_global(client, app):
    """One person hammering the form must not lock everyone else out."""
    from flythrough_service import limits
    for _ in range(limits.LOGIN_PER_EMAIL.count + 2):
        client.post("/login", data={"email": "noisy@example.com"})
    r = client.post("/login", data={"email": "quiet@example.com"},
                    follow_redirects=False)
    assert "err=" not in r.headers["location"]


def test_partner_enrolment_is_rate_limited(client, app):
    from flythrough_service import limits
    for i in range(limits.ENROL_PER_IP.count):
        client.post("/partner/join", data={"name": f"P{i}",
                                           "email": f"p{i}@example.com"})
    r = client.post("/partner/join",
                    data={"name": "Spam", "email": "spam@example.com"},
                    follow_redirects=False)
    assert "err=" in r.headers["location"]


def test_rate_rows_are_the_only_events_ever_deleted(client, app):
    """Everything else in that table is the audit trail. Sweeping counters must
    not touch it."""
    from flythrough_service import limits
    sign_in(client, app)
    start_order(client)
    with app.state.db.tx() as c:
        before = c.execute("SELECT count(*) FROM events WHERE kind NOT LIKE 'rate.%'"
                           ).fetchone()[0]
    # -1, not 0: `at` has one-second granularity, so rows written this second
    # are not yet "older than now" and a 0 window would leave them.
    limits.sweep(app.state.db, older_than_s=-1)
    with app.state.db.tx() as c:
        after = c.execute("SELECT count(*) FROM events WHERE kind NOT LIKE 'rate.%'"
                          ).fetchone()[0]
        rates = c.execute("SELECT count(*) FROM events WHERE kind LIKE 'rate.%'"
                          ).fetchone()[0]
    assert after == before and before > 0
    assert rates == 0


def test_forwarded_for_uses_the_last_hop(app):
    """Earlier entries are supplied by the client and are trivially forged."""
    from flythrough_service import limits

    class R:
        headers = {"x-forwarded-for": "1.2.3.4, 9.9.9.9, 10.0.0.7"}
        client = None
    assert limits.client_ip(R()) == "10.0.0.7"


# ------------------------------------------------------------ outcome loop


def test_answering_did_it_sell_needs_no_login(client, app):
    """A question that costs a sign-in to answer is a question nobody answers,
    and the response rate is the entire value."""
    from flythrough_service import orders
    sign_in(client, app, "agent@example.com")
    oid = start_order(client)
    with app.state.db.tx() as c:
        orders.transition(c, app.state.db, oid, "awaiting_payment")
        orders.transition(c, app.state.db, oid, "paid")
        orders.transition(c, app.state.db, oid, "rendering")
        orders.transition(c, app.state.db, oid, "delivered")

    client.cookies.clear()                      # signed out entirely
    assert client.get(f"/o/{oid}").status_code == 200
    r = client.post(f"/o/{oid}", data={"reply": "sold in about 3 weeks"},
                    follow_redirects=False)
    assert r.status_code == 303
    with app.state.db.tx() as c:
        row = c.execute("SELECT * FROM outcomes WHERE order_id=?", (oid,)).fetchone()
    assert row["result"] == "sold" and row["days_to_sell"] == 21


def test_an_undelivered_order_has_no_outcome_page(client, app):
    sign_in(client, app)
    oid = start_order(client)
    assert client.get(f"/o/{oid}").status_code == 404


def test_a_guessed_order_id_gets_nothing(client):
    assert client.get("/o/ord_deadbeefdeadbeefdead").status_code == 404


def test_outcome_answers_are_rate_limited(client, app):
    from flythrough_service import orders
    sign_in(client, app)
    oid = start_order(client)
    with app.state.db.tx() as c:
        orders.transition(c, app.state.db, oid, "awaiting_payment")
        orders.transition(c, app.state.db, oid, "paid")
        orders.transition(c, app.state.db, oid, "rendering")
        orders.transition(c, app.state.db, oid, "delivered")
    client.cookies.clear()
    for _ in range(5):
        client.post(f"/o/{oid}", data={"reply": "sold"}, follow_redirects=False)
    assert client.post(f"/o/{oid}", data={"reply": "sold"},
                       follow_redirects=False).status_code == 404


def test_only_an_operator_can_send_the_asks(app_with_operator):
    c = TestClient(app_with_operator)
    sign_in(c, app_with_operator, "buyer@example.com")
    assert c.post("/admin/ask", data={"csrf": "x"}).status_code == 404


# ----------------------------------------------------------- on-site shoot


def _shoot_upload(client, app, oid, slot, name, salt=b"\x01"):
    csrf = csrf_of(client, app, f"/shoot/{oid}")
    return client.post(f"/order/{oid}/upload",
                       data={"csrf": csrf, "slot": slot},
                       files=[("files", (name, io.BytesIO(JPEG + salt),
                                         "image/jpeg"))],
                       headers={"referer": f"http://testserver/shoot/{oid}"},
                       follow_redirects=False)


def test_the_shot_list_names_what_is_still_missing(client, app):
    sign_in(client, app)
    oid = start_order(client)
    page = client.get(f"/shoot/{oid}").text
    assert "Still needed" in page
    for anchor in ("exterior", "living", "kitchen"):
        assert anchor in page


def test_a_slot_beats_the_filename(client, app):
    """A phone names everything IMG_4417.jpg, which resolves to nothing useful.
    The slot the photographer tapped is the truth."""
    sign_in(client, app)
    oid = start_order(client)
    _shoot_upload(client, app, oid, "kitchen", "IMG_4417.jpg")
    with app.state.db.tx() as c:
        row = c.execute("SELECT room_key FROM uploads WHERE order_id=?",
                        (oid,)).fetchone()
    assert row["room_key"] == "kitchen"


def test_a_bogus_slot_falls_back_to_the_filename(client, app):
    """A hand-posted slot must not be able to invent a room key the taxonomy
    does not have -- that would reach the planner as an unknown room."""
    sign_in(client, app)
    oid = start_order(client)
    _shoot_upload(client, app, oid, "not_a_real_room", "kitchen.jpg")
    with app.state.db.tx() as c:
        row = c.execute("SELECT room_key FROM uploads WHERE order_id=?",
                        (oid,)).fetchone()
    assert row["room_key"] == "kitchen"


def test_shooting_returns_you_to_the_shot_list(client, app):
    """Not to the brief page. On site you take the next shot."""
    sign_in(client, app)
    oid = start_order(client)
    r = _shoot_upload(client, app, oid, "kitchen", "IMG_1.jpg")
    assert f"/shoot/{oid}" in r.headers["location"]


def test_the_page_says_you_can_leave_once_the_set_holds(client, app):
    sign_in(client, app)
    oid = start_order(client)
    for i, slot in enumerate(("exterior", "living", "kitchen", "patio"), 1):
        _shoot_upload(client, app, oid, slot, f"IMG_{i}.jpg", salt=bytes([i]))
    page = client.get(f"/shoot/{oid}").text
    assert "You can leave" in page
    assert "Still needed" not in page


def test_the_aerial_warning_fires_on_site_not_after(client, app):
    """The exact failure this project hit: a rear-framed ground shot cut to a
    front-framed aerial. On site it is a two-minute fix; a week later it is a
    re-shoot nobody will do."""
    sign_in(client, app)
    oid = start_order(client)
    for i, slot in enumerate(("exterior", "living", "kitchen"), 1):
        _shoot_upload(client, app, oid, slot, f"IMG_{i}.jpg", salt=bytes([i]))
    _shoot_upload(client, app, oid, "patio", "IMG_9.jpg", salt=b"\x09")
    _shoot_upload(client, app, oid, "aerial", "drone-overhead.jpg", salt=b"\x0a")
    page = client.get(f"/shoot/{oid}").text
    assert "aerial" in page.lower()
    assert "You can leave" not in page


def test_the_shot_list_is_per_vertical(client, app):
    sign_in(client, app)
    oid = start_order(client, "veh-ad-premium")
    page = client.get(f"/shoot/{oid}").text
    assert "Three-quarter front" in page and "Odometer" in page
    assert "Kitchen" not in page


def test_a_paid_order_has_no_shoot_page(client, app):
    """The shot list is for before payment. After it, nothing more is uploaded."""
    from flythrough_service import orders
    sign_in(client, app)
    oid = start_order(client)
    with app.state.db.tx() as c:
        orders.transition(c, app.state.db, oid, "awaiting_payment")
        orders.transition(c, app.state.db, oid, "paid")
    r = client.get(f"/shoot/{oid}", follow_redirects=False)
    assert r.status_code == 303 and f"/order/{oid}" in r.headers["location"]


def test_another_customer_cannot_open_the_shot_list(client, app):
    sign_in(client, app, "first@example.com")
    oid = start_order(client)
    client.cookies.clear()
    sign_in(client, app, "second@example.com")
    assert "Not found" in client.get(f"/shoot/{oid}").text


# --------------------------------------------------------------- payouts UI


def test_payouts_page_is_operator_only(app_with_operator):
    c = TestClient(app_with_operator)
    sign_in(c, app_with_operator, "buyer@example.com")
    assert c.get("/admin/payouts").status_code == 404
    c.cookies.clear()
    sign_in(c, app_with_operator, "boss@flythrough.test")
    assert c.get("/admin/payouts").status_code == 200


def test_recording_a_payout_tells_the_partner(app_with_operator):
    c = TestClient(app_with_operator)
    app = app_with_operator
    c.post("/partner/join", data={"name": "Sam", "email": "sam@p.com"})
    with app.state.db.tx() as x:
        code = x.execute("SELECT code FROM resellers").fetchone()["code"]
        rid = x.execute("SELECT id FROM resellers").fetchone()["id"]
    c.get(f"/?ref={code}")
    sign_in(c, app, "buyer@example.com")
    oid = start_order(c)
    _pay(c, oid)
    c.cookies.clear()

    sign_in(c, app, "boss@flythrough.test")
    page = c.get("/admin/payouts").text
    assert "sam@p.com" in page and "$62.25" in page
    csrf = page.split('name="csrf" value="')[1].split('"')[0]
    c.post("/admin/payouts", data={"reseller_id": rid, "reference": "BACS 9",
                                   "csrf": csrf}, follow_redirects=False)

    subs = [m.subject for m in app.state.mailer.outbox() if m.to == "sam@p.com"]
    assert any("commission paid" in s for s in subs), subs
    from flythrough_service import reseller
    assert reseller.ledger(app.state.db, rid,
                           payout_minimum_cents=0).paid_cents == 6225


def test_a_payout_cannot_be_posted_without_csrf(app_with_operator):
    c = TestClient(app_with_operator)
    sign_in(c, app_with_operator, "boss@flythrough.test")
    assert c.post("/admin/payouts",
                  data={"reseller_id": "res_x", "csrf": "no"}).status_code == 404


# ------------------------------------------------- arriving from the site


def test_a_link_from_the_marketing_site_starts_the_flow(client, app):
    """GET /order?sku=... is the href a static page can produce: no session, no
    CSRF token to give."""
    r = client.get("/order?sku=re-listing-pro", follow_redirects=False)
    assert r.status_code == 303 and "/login" in r.headers["location"]
    sign_in(client, app)
    r = client.get("/order?sku=re-listing-pro", follow_redirects=False)
    assert r.status_code == 303 and "/shoot/" in r.headers["location"]


def test_arriving_lands_on_the_shot_list_not_the_brief(client, app):
    """Someone who clicked Buy is about to take photographs. Put the shot list
    in front of them, not a form."""
    sign_in(client, app)
    r = client.get("/order?sku=veh-ad-premium", follow_redirects=False)
    assert "/shoot/" in r.headers["location"]


def test_an_unknown_sku_from_a_stale_link_goes_home(client, app):
    sign_in(client, app)
    r = client.get("/order?sku=this-was-discontinued", follow_redirects=False)
    assert r.headers["location"] == "/"


def test_a_signed_out_visitor_creates_no_order(client, app):
    """A GET that created a paid-for object would be a URL a crawler could fire."""
    client.get("/order?sku=re-listing-pro", follow_redirects=False)
    with app.state.db.tx() as c:
        assert c.execute("SELECT count(*) FROM orders").fetchone()[0] == 0


def test_a_referral_survives_the_hop_through_sign_in(client, app):
    """The partner link lands on the marketing site, the customer clicks Buy,
    then signs in. The attribution has to survive both hops or the partner is
    never paid for the customer they sent."""
    client.post("/partner/join", data={"name": "Sam", "email": "sam@p.com"})
    with app.state.db.tx() as c:
        code = c.execute("SELECT code FROM resellers").fetchone()["code"]
        rid = c.execute("SELECT id FROM resellers").fetchone()["id"]

    client.get(f"/order?sku=re-listing-pro&ref={code}", follow_redirects=False)
    sign_in(client, app, "buyer@example.com")
    r = client.get("/order?sku=re-listing-pro", follow_redirects=False)
    oid = r.headers["location"].rsplit("/", 1)[1]
    _pay(client, oid)

    from flythrough_service import reseller
    assert reseller.ledger(app.state.db, rid,
                           payout_minimum_cents=0).lifetime_cents == 6225
