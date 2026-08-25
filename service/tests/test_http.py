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
