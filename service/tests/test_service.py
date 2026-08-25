"""Tests for the service layer."""

import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "service"))

from flythrough_service import config  # noqa: E402
from flythrough_service.db import Database, new_id, now  # noqa: E402


def test_production_refuses_to_start_without_secrets(monkeypatch):
    """A production service missing STRIPE_WEBHOOK_SECRET accepts forged payment
    events -- it would render and mark paid on anyone's POST. Refusing to boot is
    the only safe behaviour; degrading to 'warn and continue' is not."""
    for k in ("FLYTHROUGH_SECRET_KEY", "STRIPE_SECRET_KEY",
              "STRIPE_WEBHOOK_SECRET", "FLYTHROUGH_SMTP_URL"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError) as e:
        config.load(dev=False)
    for k in ("FLYTHROUGH_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"):
        assert k in str(e.value)


def test_dev_mode_starts_without_secrets():
    assert config.load(dev=True).domain


def test_commission_terms_match_what_was_agreed():
    s = config.load(dev=True)
    assert s.commission_rate == 0.25 and s.commission_lifetime


def test_settings_never_expose_secrets_in_repr(monkeypatch):
    """Settings gets logged and rendered in error pages. It must not carry a
    live Stripe key into a traceback."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_TOPSECRET")
    s = config.load(dev=True)
    assert "TOPSECRET" not in repr(s), "secret leaks through repr()"


@pytest.fixture()
def db(tmp_path):
    return Database(tmp_path / "t.db")


def test_schema_applies_and_is_idempotent(tmp_path):
    p = tmp_path / "t.db"
    Database(p)
    Database(p)          # re-opening must not fail or duplicate
    with Database(p).tx() as c:
        names = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"orders", "uploads", "jobs", "commissions", "resellers",
            "processed_webhooks", "events"} <= names


def test_foreign_keys_are_enforced(db):
    """An order pointing at a customer that does not exist is a silent data
    corruption in every report built on top of it."""
    with pytest.raises(sqlite3.IntegrityError):
        with db.tx() as c:
            c.execute(
                "INSERT INTO orders(id, customer_id, sku, vertical, price_cents,"
                " status, created_at) VALUES(?,?,?,?,?,?,?)",
                (new_id("ord"), "cus_does_not_exist", "re-listing-pro", "rooms",
                 24900, "draft", now()))


def test_one_commission_per_order(db):
    """Stripe redelivers webhooks. Paying a reseller twice for one order is the
    expensive direction of that mistake, so the database refuses it outright."""
    with db.tx() as c:
        r, cu, o = new_id("res"), new_id("cus"), new_id("ord")
        c.execute("INSERT INTO resellers(id,email,name,code,rate,created_at)"
                  " VALUES(?,?,?,?,?,?)", (r, "r@x.com", "R", "CODE", 0.25, now()))
        c.execute("INSERT INTO customers(id,email,created_at) VALUES(?,?,?)",
                  (cu, "c@x.com", now()))
        c.execute("INSERT INTO orders(id,customer_id,sku,vertical,price_cents,"
                  "status,created_at) VALUES(?,?,?,?,?,?,?)",
                  (o, cu, "re-listing-pro", "rooms", 24900, "paid", now()))
        c.execute("INSERT INTO commissions(id,reseller_id,order_id,amount_cents,"
                  "rate,status,created_at) VALUES(?,?,?,?,?,?,?)",
                  (new_id("com"), r, o, 6225, 0.25, "accrued", now()))
    with pytest.raises(sqlite3.IntegrityError):
        with db.tx() as c:
            c.execute("INSERT INTO commissions(id,reseller_id,order_id,"
                      "amount_cents,rate,status,created_at) VALUES(?,?,?,?,?,?,?)",
                      (new_id("com"), r, o, 6225, 0.25, "accrued", now()))


def test_stripe_ref_is_unique(db):
    """The same checkout session must never produce two orders."""
    with db.tx() as c:
        cu = new_id("cus")
        c.execute("INSERT INTO customers(id,email,created_at) VALUES(?,?,?)",
                  (cu, "c@x.com", now()))
        for i in range(1):
            c.execute("INSERT INTO orders(id,customer_id,sku,vertical,price_cents,"
                      "status,stripe_ref,created_at) VALUES(?,?,?,?,?,?,?,?)",
                      (new_id("ord"), cu, "re-listing-pro", "rooms", 24900,
                       "paid", "cs_test_1", now()))
    with pytest.raises(sqlite3.IntegrityError):
        with db.tx() as c:
            c.execute("INSERT INTO orders(id,customer_id,sku,vertical,price_cents,"
                      "status,stripe_ref,created_at) VALUES(?,?,?,?,?,?,?,?)",
                      (new_id("ord"), cu, "re-listing-pro", "rooms", 24900,
                       "paid", "cs_test_1", now()))


def test_rollback_leaves_nothing_behind(db):
    with pytest.raises(ValueError):
        with db.tx() as c:
            c.execute("INSERT INTO customers(id,email,created_at) VALUES(?,?,?)",
                      (new_id("cus"), "ghost@x.com", now()))
            raise ValueError("boom")
    with db.tx() as c:
        assert c.execute("SELECT count(*) FROM customers").fetchone()[0] == 0


def test_ids_are_unguessable():
    """Order ids appear in delivery URLs. A sequential id is an enumeration of
    every customer's files."""
    ids = {new_id("ord") for _ in range(500)}
    assert len(ids) == 500
    assert all(len(i.split("_", 1)[1]) >= 20 for i in ids)


# ---------------------------------------------------------------------- storage

import io  # noqa: E402

from flythrough_service import (auth, catalog_bridge as cat, orders,  # noqa: E402
                                payments, queue as q, render, reseller)
from flythrough_service.storage import Store, UploadRejected, sniff  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 4096


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / "blobs")


def test_identical_uploads_share_one_blob(store):
    a = store.put(io.BytesIO(JPEG), max_bytes=10**7, allowed=frozenset({"image/jpeg"}))
    b = store.put(io.BytesIO(JPEG), max_bytes=10**7, allowed=frozenset({"image/jpeg"}))
    assert a.sha256 == b.sha256 and a.path == b.path


def test_originals_are_read_only_once_stored(store):
    """The compliance position is that the file on the originals page is the
    file the client sent. An editable original is that claim with a hole in it."""
    s = store.put(io.BytesIO(JPEG), max_bytes=10**7, allowed=frozenset({"image/jpeg"}))
    assert oct(s.path.stat().st_mode)[-3:] == "444"


@pytest.mark.parametrize("data,why", [
    (b"%PDF-1.4 not a photo", "wrong magic bytes"),
    (b"", "empty"),
    (b"GIF89a" + b"x" * 100, "unsupported type"),
])
def test_uploads_are_sniffed_not_trusted(store, data, why):
    """Content-Type is whatever the client says it is. Renaming invoice.pdf to
    photo.jpg is a two-second attack."""
    with pytest.raises(UploadRejected):
        store.put(io.BytesIO(data), max_bytes=10**7,
                  allowed=frozenset({"image/jpeg", "image/png"}))


def test_size_cap_stops_mid_stream(store):
    with pytest.raises(UploadRejected) as e:
        store.put(io.BytesIO(JPEG), max_bytes=512, allowed=frozenset({"image/jpeg"}))
    assert "0 MB" not in str(e.value)      # was a real copy bug


def test_sniff_recognises_every_type_we_accept():
    assert sniff(b"\xff\xd8\xff") == "image/jpeg"
    assert sniff(b"\x89PNG\r\n\x1a\n") == "image/png"
    assert sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff(b"\x00\x00\x00\x18ftypheic") == "image/heic"
    assert sniff(b"nothing") is None


# ------------------------------------------------------------------------- auth


def test_magic_link_is_single_use(db):
    t = auth.issue_login_token(db, "a@b.com", ttl_s=600)
    auth.redeem_login_token(db, t, session_ttl_s=60)
    with pytest.raises(auth.AuthError):
        auth.redeem_login_token(db, t, session_ttl_s=60)


def test_magic_link_expires(db):
    t = auth.issue_login_token(db, "a@b.com", ttl_s=-1)
    with pytest.raises(auth.AuthError):
        auth.redeem_login_token(db, t, session_ttl_s=60)


def test_requesting_a_new_link_kills_the_old_one(db):
    """A link left in a forwarded thread must stop working the moment the real
    owner asks for another."""
    first = auth.issue_login_token(db, "a@b.com", ttl_s=600)
    auth.issue_login_token(db, "a@b.com", ttl_s=600)
    with pytest.raises(auth.AuthError):
        auth.redeem_login_token(db, first, session_ttl_s=60)


def test_tokens_are_never_stored_in_the_clear(db):
    t = auth.issue_login_token(db, "a@b.com", ttl_s=600)
    s, _ = auth.redeem_login_token(db, t, session_ttl_s=60)
    raw = Path(db.path).read_bytes()
    assert t.encode() not in raw and s.encode() not in raw


def test_logout_invalidates_the_session(db):
    t = auth.issue_login_token(db, "a@b.com", ttl_s=600)
    s, _ = auth.redeem_login_token(db, t, session_ttl_s=600)
    assert auth.resolve_session(db, s)
    auth.end_session(db, s)
    assert auth.resolve_session(db, s) is None


def test_csrf_token_is_bound_to_the_session():
    a = auth.csrf_token("session-a", "secret")
    assert auth.csrf_ok("session-a", "secret", a)
    assert not auth.csrf_ok("session-b", "secret", a)
    assert not auth.csrf_ok("session-a", "secret", "")


@pytest.mark.parametrize("bad", ["", "nope", "a@b", "a b@c.com", "@x.com", "a@@b.com"])
def test_bad_addresses_are_refused(bad):
    with pytest.raises(auth.AuthError):
        auth.normalise_email(bad)


# ------------------------------------------------------- orders, money, ledger


@pytest.fixture()
def customer(db):
    from flythrough_service.db import new_id, now
    cid = new_id("cus")
    with db.tx() as c:
        c.execute("INSERT INTO customers(id,email,created_at) VALUES(?,?,?)",
                  (cid, "buyer@example.com", now()))
    return cid


def test_prices_come_from_the_model_not_the_service():
    """One number, one home. If these ever disagree the customer sees one price
    on the page and is charged another."""
    import catalog
    for s in catalog.CATALOG:
        assert cat.price_cents(s.id) == round(s.price * 100)


def test_price_conversion_rounds_rather_than_truncates():
    """int(24899.999...) is 24899 -- a cent short on every single order."""
    assert cat.price_cents("re-listing-pro") == 24900
    assert cat.price_cents("veh-walkaround-3") == 11700


def test_the_portal_never_asks_for_a_photo_link():
    """It takes the files directly. Asking for a Dropbox link is asking someone
    to solve a problem we already solved, and it is a field they abandon on."""
    for v in ("rooms", "vehicles", "products"):
        assert not [q for q in cat.intake_for(v) if q.startswith("Link to the photos")]


def test_a_fresh_order_is_not_ready(db, customer):
    """The requirement comes from the SKU, not a flat floor. Every shot is
    anchored between two photographs, so a 42-second film over 8 beats needs
    nine of them -- and asking before payment is the only cheap time to ask."""
    from flythrough_service import catalog_bridge as cat
    o = orders.create(db, customer, "re-listing-pro")
    r = orders.readiness(db, o)
    assert not r.ok and r.photos == 0
    assert r.required == cat.skus()["re-listing-pro"].beats + 1 == 9


def test_illegal_transitions_are_refused(db, customer):
    o = orders.create(db, customer, "re-listing-pro")
    with db.tx() as c:
        orders.transition(c, db, o, "awaiting_payment")
        orders.transition(c, db, o, "paid")
        with pytest.raises(orders.OrderError):
            orders.transition(c, db, o, "draft")


def test_transitions_are_idempotent(db, customer):
    """Webhook redelivery must not be an error."""
    o = orders.create(db, customer, "re-listing-pro")
    with db.tx() as c:
        orders.transition(c, db, o, "awaiting_payment")
        orders.transition(c, db, o, "paid")
        orders.transition(c, db, o, "paid")
    assert orders.get(db, o)["status"] == "paid"


def test_an_order_is_invisible_to_another_customer(db, customer):
    """Not found, not forbidden -- a 403 confirms the id exists."""
    o = orders.create(db, customer, "re-listing-pro")
    assert orders.get(db, o, customer_id="cus_someone_else") is None


# ------------------------------------------------------------------- webhooks

SECRET = "whsec_test"


def _event(eid, oid, amount=24900, status="paid",
           etype="checkout.session.completed"):
    return {"id": eid, "type": etype, "data": {"object": {
        "id": "cs_" + eid, "payment_status": status, "amount_total": amount,
        "client_reference_id": oid, "metadata": {"order_id": oid}}}}


def test_a_genuine_signature_verifies():
    body = b'{"id":"evt_1"}'
    assert payments.verify(body, payments.sign(body, SECRET), SECRET)["id"] == "evt_1"


@pytest.mark.parametrize("header", ["", "garbage", "t=abc,v1=x"])
def test_malformed_signatures_are_refused(header):
    with pytest.raises(payments.WebhookError):
        payments.verify(b"{}", header, SECRET)


def test_a_forged_signature_is_refused():
    body = b'{"id":"evt_1"}'
    with pytest.raises(payments.WebhookError):
        payments.verify(body, payments.sign(body, "not-the-secret"), SECRET)


def test_an_old_signature_is_refused():
    """Without a replay window a captured request is valid forever."""
    body = b'{"id":"evt_1"}'
    old = payments.sign(body, SECRET, timestamp=int(time.time()) - 99999)
    with pytest.raises(payments.WebhookError):
        payments.verify(body, old, SECRET)


def test_no_secret_configured_means_no_webhook_is_trusted():
    body = b"{}"
    with pytest.raises(payments.WebhookError):
        payments.verify(body, payments.sign(body, ""), "")


def test_payment_marks_paid_exactly_once(db, customer):
    o = orders.create(db, customer, "re-listing-pro")
    msg, paid = payments.handle(db, _event("evt_1", o))
    assert paid == o and orders.get(db, o)["status"] == "paid"
    msg, paid = payments.handle(db, _event("evt_1", o))
    assert paid is None and "already processed" in msg


def test_an_unpaid_session_is_not_treated_as_paid(db, customer):
    """An async method still clearing. Shipping on it means delivering before
    the money settles."""
    o = orders.create(db, customer, "re-listing-pro")
    payments.handle(db, _event("evt_1", o, status="unpaid"))
    assert orders.get(db, o)["status"] == "draft"


def test_a_wrong_amount_never_marks_paid(db, customer):
    """If the charge disagrees with the quote someone has edited a Payment
    Link, and we would be doing the work for whatever it happened to say."""
    o = orders.create(db, customer, "re-listing-pro")
    msg, paid = payments.handle(db, _event("evt_1", o, amount=100))
    assert paid is None and orders.get(db, o)["status"] == "draft"
    assert "mismatch" in msg


def test_unknown_event_types_are_acknowledged_not_retried(db):
    """A 500 makes Stripe retry forever on an event that will never succeed."""
    msg, paid = payments.handle(db, {"id": "evt_x", "type": "invoice.created",
                                     "data": {"object": {}}})
    assert paid is None and "ignored" in msg


# ------------------------------------------------------------------- reseller


def _enrol(db, name="Sam Partner", email="sam@partner.com"):
    rid = reseller.enrol(db, email, name, rate=0.25)
    with db.tx() as c:
        code = c.execute("SELECT code FROM resellers WHERE id=?", (rid,)).fetchone()["code"]
    return rid, code


def test_referral_codes_avoid_ambiguous_characters():
    """A code read off a business card or spoken down a phone. 0/O and 1/I/L
    mistyped is a commission that silently goes to nobody."""
    for _ in range(200):
        code = reseller.make_code("Olivia Lloyd")
        assert not (set(code) & set("O0I1L"))
        assert reseller.CODE_RE.match(code)


def test_commission_is_twenty_five_percent_lifetime(db, customer):
    rid, code = _enrol(db)
    assert reseller.attribute(db, customer, code)
    for i, sku in enumerate(["re-listing-pro", "re-listing-pro", "veh-launch"]):
        o = orders.create(db, customer, sku)
        payments.handle(db, _event(f"evt_{i}", o, amount=cat.price_cents(sku)))
    led = reseller.ledger(db, rid, payout_minimum_cents=5000)
    # 25% of 249 + 249 + 399
    assert led.lifetime_cents == round(0.25 * (24900 + 24900 + 39900))


def test_attribution_is_first_touch_and_permanent(db, customer):
    """Last-touch would let a second reseller steal an account with one link."""
    first, code1 = _enrol(db, "First", "one@x.com")
    second, code2 = _enrol(db, "Second", "two@x.com")
    assert reseller.attribute(db, customer, code1)
    assert not reseller.attribute(db, customer, code2)
    o = orders.create(db, customer, "re-listing-pro")
    payments.handle(db, _event("evt_1", o))
    assert reseller.ledger(db, first, payout_minimum_cents=0).lifetime_cents > 0
    assert reseller.ledger(db, second, payout_minimum_cents=0).lifetime_cents == 0


def test_an_unknown_code_attributes_nothing(db, customer):
    assert not reseller.attribute(db, customer, "NOTACODE")
    assert not reseller.attribute(db, customer, "")


def test_a_commission_is_never_paid_twice(db, customer):
    rid, code = _enrol(db)
    reseller.attribute(db, customer, code)
    o = orders.create(db, customer, "re-listing-pro")
    for i in range(5):
        payments.handle(db, _event(f"evt_{i}", o))    # redelivery storm
    assert reseller.ledger(db, rid, payout_minimum_cents=0).lifetime_cents == 6225


def test_a_refund_reverses_the_commission(db, customer):
    rid, code = _enrol(db)
    reseller.attribute(db, customer, code)
    o = orders.create(db, customer, "re-listing-pro")
    payments.handle(db, _event("evt_1", o))
    payments.handle(db, {"id": "evt_2", "type": "charge.refunded",
                         "data": {"object": {"metadata": {"order_id": o}}}})
    assert reseller.ledger(db, rid, payout_minimum_cents=0).lifetime_cents == 0
    assert orders.get(db, o)["status"] == "refunded"


def test_reversal_keeps_the_row(db, customer):
    """The ledger records what happened, including what un-happened."""
    rid, code = _enrol(db)
    reseller.attribute(db, customer, code)
    o = orders.create(db, customer, "re-listing-pro")
    payments.handle(db, _event("evt_1", o))
    payments.handle(db, {"id": "evt_2", "type": "charge.refunded",
                         "data": {"object": {"metadata": {"order_id": o}}}})
    with db.tx() as c:
        row = c.execute("SELECT status FROM commissions WHERE order_id=?", (o,)).fetchone()
    assert row["status"] == "reversed"


def test_payout_minimum_holds_small_balances(db, customer):
    rid, code = _enrol(db)
    reseller.attribute(db, customer, code)
    o = orders.create(db, customer, "veh-walkaround-3")     # $117 -> $29.25
    payments.handle(db, _event("evt_1", o, amount=11700))
    led = reseller.ledger(db, rid, payout_minimum_cents=5000)
    assert led.payable_cents == 0 and led.accrued_cents == 2925


def test_duplicate_enrolment_is_refused(db):
    _enrol(db)
    with pytest.raises(reseller.ResellerError):
        _enrol(db)


# ---------------------------------------------------------------- render queue


def _paid_order(db, sku="re-listing-pro",
                names=("01_front-elevation.jpg", "02_foyer.jpg", "03_kitchen.jpg",
                       "04_patio.jpg", "05_rear-aerial.jpg"), tmp=None):
    from flythrough_service.db import new_id, now
    cid = new_id("cus")
    with db.tx() as c:
        c.execute("INSERT INTO customers(id,email,created_at) VALUES(?,?,?)",
                  (cid, f"{new_id('e')}@x.com", now()))
    o = orders.create(db, cid, sku)
    src = (tmp or Path(db.path).parent) / "src"
    src.mkdir(parents=True, exist_ok=True)
    with db.tx() as c:
        for i, nm in enumerate(names, 1):
            f = src / nm
            f.write_bytes(JPEG)
            c.execute("INSERT INTO uploads(id,order_id,filename,mime,bytes,sha256,"
                      "path,position,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (new_id("upl"), o, nm, "image/jpeg", len(JPEG),
                       f"h{i}", str(f), i, now()))
        orders.transition(c, db, o, "awaiting_payment")
        orders.transition(c, db, o, "paid")
    return o


def _ok_renderer(*, out_dir, slug, **kw):
    m = Path(out_dir) / f"{slug}_master.mp4"
    m.write_bytes(b"video")
    return [("master", m)]


def test_a_paid_order_renders_and_delivers(db, tmp_path):
    o = _paid_order(db, tmp=tmp_path)
    w = q.Worker(db=db, data_dir=tmp_path, renderer=_ok_renderer)
    w.enqueue(o)
    w.run_one()
    assert orders.get(db, o)["status"] == "delivered"
    assert [d["kind"] for d in orders.deliverables(db, o)] == ["master"]


def test_one_render_per_order_ever(db, tmp_path):
    """Enqueueing twice must not spend the credits twice."""
    o = _paid_order(db, tmp=tmp_path)
    w = q.Worker(db=db, data_dir=tmp_path, renderer=_ok_renderer)
    assert w.enqueue(o) == w.enqueue(o) == w.enqueue(o)


def test_only_one_worker_claims_a_job(db, tmp_path):
    """The status guard on the UPDATE is the entire concurrency design. If two
    workers can claim one job, one order renders twice and bills twice."""
    import threading
    o = _paid_order(db, tmp=tmp_path)
    w = q.Worker(db=db, data_dir=tmp_path, renderer=_ok_renderer)
    w.enqueue(o)
    got = []
    threads = [threading.Thread(target=lambda: got.append(w.claim()))
               for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for g in got if g) == 1


def test_a_failing_render_retries_then_gives_up(db, tmp_path):
    def boom(**kw):
        raise RuntimeError("provider exploded")
    o = _paid_order(db, tmp=tmp_path)
    w = q.Worker(db=db, data_dir=tmp_path, renderer=boom)
    w.enqueue(o)
    for _ in range(q.MAX_ATTEMPTS + 1):
        w.run_one()
    assert w.stats().get("failed") == 1
    assert orders.get(db, o)["status"] == "failed"


def test_a_failed_order_is_not_auto_refunded(db, tmp_path):
    """A human decides re-cut or refund. Auto-refunding hides the failure and
    loses the chance to fix a job the customer still wants."""
    def boom(**kw):
        raise RuntimeError("nope")
    o = _paid_order(db, tmp=tmp_path)
    w = q.Worker(db=db, data_dir=tmp_path, renderer=boom)
    w.enqueue(o)
    for _ in range(q.MAX_ATTEMPTS + 1):
        w.run_one()
    assert orders.get(db, o)["status"] != "refunded"


def test_an_empty_queue_is_not_an_error(db, tmp_path):
    assert q.Worker(db=db, data_dir=tmp_path, renderer=_ok_renderer).run_one() is None


# ------------------------------------------------------------------- viewpoint


def test_the_different_house_pairing_is_caught():
    """The real failure from this project: a rear-framed patio shot cut to a
    front-framed aerial. The model has to cross the building and lands on what
    looks like another property."""
    p = render.prepare("rooms", [
        {"filename": "01_patio.jpg", "path": "/x", "room_key": "", "position": 1},
        {"filename": "02_drone-overhead.jpg", "path": "/x", "room_key": "", "position": 2}])
    assert p.warnings


def test_a_correctly_named_aerial_does_not_warn():
    """A check that fires on correct work trains people to ignore it."""
    p = render.prepare("rooms", [
        {"filename": "01_patio.jpg", "path": "/x", "room_key": "", "position": 1},
        {"filename": "02_rear-aerial.jpg", "path": "/x", "room_key": "", "position": 2}])
    assert not p.warnings


def test_real_estate_cannot_be_rendered_without_disclosure():
    assert render.placement_for("rooms") != "none"
    assert render.placement_for("vehicles") == "none"


def test_slugs_are_safe_and_unique_per_order():
    a = render.slug_for("ord_aaaaaaaaaaaa", {"Property address (as it appears on the listing)": "1420 Cedar Ridge Rd, Austin TX"})
    b = render.slug_for("ord_bbbbbbbbbbbb", {"Property address (as it appears on the listing)": "1420 Cedar Ridge Rd, Austin TX"})
    assert a != b
    assert all(ch.isalnum() or ch == "-" for ch in a)
    assert render.slug_for("ord_cccccccccccc", {}).startswith("job-")


def test_staging_copies_and_never_mutates_the_original(db, tmp_path):
    src = tmp_path / "blob"
    src.write_bytes(JPEG)
    photos = [{"path": str(src), "key": "kitchen", "position": 1,
               "filename": "kitchen.jpg"}]
    out = render.stage_originals(tmp_path, "ord_x", photos)
    staged = list(out.iterdir())
    assert len(staged) == 1 and staged[0].name == "01_kitchen.jpg"
    assert staged[0].read_bytes() == src.read_bytes()
    assert src.exists()          # copied, not moved


# --------------------------------------------------------------- outcomes


from flythrough_service import outcomes as oc  # noqa: E402


@pytest.mark.parametrize("reply,result,days", [
    ("Sold! took about 3 weeks", "sold", 21),
    ("under contract in 9 days", "sold", 9),
    ("still listed", "listed", None),
    ("nope, still on", "listed", None),
    ("we withdrew it", "withdrawn", None),
    ("cancelled", "withdrawn", None),
    ("off market", "withdrawn", None),
    ("dunno mate", "unknown", None),
    ("no idea", "unknown", None),
    ("", "unknown", None),
])
def test_replies_are_read_the_way_people_write_them(reply, result, days):
    assert oc.parse(reply) == (result, days)


def test_a_short_synonym_never_matches_inside_a_word():
    """A bare "no" matched as a substring lit up inside "dunno" and recorded an
    unparseable reply as a confident "still listed". Word boundaries, always."""
    assert oc.parse("dunno")[0] == "unknown"
    assert oc.parse("nothing happened")[0] == "unknown"
    assert oc.parse("nope")[0] == "listed"


def test_an_unparseable_reply_keeps_the_raw_text(db, customer):
    """Evidence they engaged, and worth a human reading."""
    o = orders.create(db, customer, "re-listing-pro")
    oc.record(db, o, "it's complicated, call me")
    with db.tx() as c:
        row = c.execute("SELECT * FROM outcomes WHERE order_id=?", (o,)).fetchone()
    assert row["result"] == "unknown" and "complicated" in row["note"]


def test_only_delivered_orders_old_enough_are_due(db, customer):
    from flythrough_service.db import now
    fresh = orders.create(db, customer, "re-listing-pro")
    old = orders.create(db, customer, "re-listing-pro")
    undelivered = orders.create(db, customer, "re-listing-pro")
    with db.tx() as c:
        for o in (fresh, old, undelivered):
            orders.transition(c, db, o, "awaiting_payment")
            orders.transition(c, db, o, "paid")
        for o in (fresh, old):
            orders.transition(c, db, o, "rendering")
            orders.transition(c, db, o, "delivered")
        c.execute("UPDATE orders SET delivered_at=? WHERE id=?",
                  (now() - 60 * 24 * 3600, old))
    due = oc.due(db)
    assert old in due
    assert fresh not in due and undelivered not in due


def test_we_never_ask_the_same_order_twice(db, customer):
    from flythrough_service.db import now
    o = orders.create(db, customer, "re-listing-pro")
    with db.tx() as c:
        orders.transition(c, db, o, "awaiting_payment")
        orders.transition(c, db, o, "paid")
        orders.transition(c, db, o, "rendering")
        orders.transition(c, db, o, "delivered")
        c.execute("UPDATE orders SET delivered_at=? WHERE id=?",
                  (now() - 60 * 24 * 3600, o))
    assert o in oc.due(db)
    oc.mark_asked(db, o)
    assert o not in oc.due(db)


def _sold(db, customer, style, days):
    from flythrough_service.db import now
    import json as _j
    o = orders.create(db, customer, "re-listing-pro")
    with db.tx() as c:
        c.execute("UPDATE orders SET brief=? WHERE id=?",
                  (_j.dumps({"Daylight, golden hour or twilight": style}), o))
        orders.transition(c, db, o, "awaiting_payment")
        orders.transition(c, db, o, "paid")
        orders.transition(c, db, o, "rendering")
        orders.transition(c, db, o, "delivered")
    oc.record(db, o, f"sold in {days} days")
    return o


def test_advice_says_nothing_until_there_is_enough_evidence(db, customer):
    """A finding from four listings is a coincidence. Saying nothing is free;
    saying something wrong costs the credibility the rest of this rests on."""
    for _ in range(4):
        _sold(db, customer, "golden hour", 10)
        _sold(db, customer, "daylight", 60)
    assert oc.best_advice(db, "Daylight") is None


def test_advice_appears_once_both_groups_clear_the_floor(db, customer):
    for _ in range(oc.MIN_SAMPLES):
        _sold(db, customer, "golden hour", 12)
        _sold(db, customer, "daylight", 45)
    line = oc.best_advice(db, "Daylight")
    assert line and "golden hour" in line.lower()
    assert "33 days sooner" in line


def test_a_small_difference_is_not_reported_as_a_finding(db, customer):
    """Two days apart is noise, and dressing it as advice is how you get
    ignored the first time it is wrong."""
    for _ in range(oc.MIN_SAMPLES):
        _sold(db, customer, "golden hour", 30)
        _sold(db, customer, "daylight", 32)
    assert oc.best_advice(db, "Daylight") is None


def test_medians_not_means(db, customer):
    """One listing that sat for two years would drag a mean somewhere useless
    and make the advice confidently wrong."""
    for _ in range(oc.MIN_SAMPLES - 1):
        _sold(db, customer, "twilight", 10)
    _sold(db, customer, "twilight", 700)
    got = [i for i in oc.by_dimension(db, "Daylight") if i.value == "twilight"][0]
    assert got.median_days == 10


def test_outcome_summary_counts_only_answers(db, customer):
    from flythrough_service.db import now
    o = orders.create(db, customer, "re-listing-pro")
    with db.tx() as c:
        orders.transition(c, db, o, "awaiting_payment")
        orders.transition(c, db, o, "paid")
        orders.transition(c, db, o, "rendering")
        orders.transition(c, db, o, "delivered")
    oc.mark_asked(db, o)
    assert oc.summary(db)["answered"] == 0
    oc.record(db, o, "sold in 14 days")
    s = oc.summary(db)
    assert s["answered"] == 1 and s["asked"] == 1 and s["response_rate"] == 1.0


# ---------------------------------------------------------------- payouts


def test_only_partners_over_the_minimum_appear(db, customer):
    rid, code = _enrol(db)
    reseller.attribute(db, customer, code)
    o = orders.create(db, customer, "veh-walkaround-3")      # $117 -> $29.25
    payments.handle(db, _event("e1", o, amount=11700))
    assert reseller.payable(db, payout_minimum_cents=5000) == []
    o2 = orders.create(db, customer, "re-signature")          # $399 -> $99.75
    payments.handle(db, _event("e2", o2, amount=39900))
    owed = reseller.payable(db, payout_minimum_cents=5000)
    assert len(owed) == 1 and owed[0]["owed"] == 2925 + 9975


def test_marking_paid_settles_everything_accrued(db, customer):
    rid, code = _enrol(db)
    reseller.attribute(db, customer, code)
    for i in range(3):
        o = orders.create(db, customer, "re-listing-pro")
        payments.handle(db, _event(f"e{i}", o))
    assert reseller.mark_paid(db, rid, reference="BACS 001") == 3 * 6225
    led = reseller.ledger(db, rid, payout_minimum_cents=0)
    assert led.paid_cents == 3 * 6225 and led.accrued_cents == 0


def test_paying_twice_pays_nothing_the_second_time(db, customer):
    rid, code = _enrol(db)
    reseller.attribute(db, customer, code)
    o = orders.create(db, customer, "re-listing-pro")
    payments.handle(db, _event("e1", o))
    assert reseller.mark_paid(db, rid) == 6225
    assert reseller.mark_paid(db, rid) == 0


def test_a_commission_accrued_after_a_payout_is_still_owed(db, customer):
    """The next payout must pick it up, not swallow it into the last one."""
    rid, code = _enrol(db)
    reseller.attribute(db, customer, code)
    o1 = orders.create(db, customer, "re-listing-pro")
    payments.handle(db, _event("e1", o1))
    reseller.mark_paid(db, rid)
    o2 = orders.create(db, customer, "re-listing-pro")
    payments.handle(db, _event("e2", o2))
    led = reseller.ledger(db, rid, payout_minimum_cents=0)
    assert led.accrued_cents == 0 and led.payable_cents == 6225
    assert led.paid_cents == 6225


def test_a_paid_commission_is_not_reversed_by_a_later_refund(db, customer):
    """Money already sent cannot be un-sent by a status change. It becomes a
    conversation, not a silent ledger edit."""
    rid, code = _enrol(db)
    reseller.attribute(db, customer, code)
    o = orders.create(db, customer, "re-listing-pro")
    payments.handle(db, _event("e1", o))
    reseller.mark_paid(db, rid)
    payments.handle(db, {"id": "e2", "type": "charge.refunded",
                         "data": {"object": {"metadata": {"order_id": o}}}})
    with db.tx() as c:
        row = c.execute("SELECT status FROM commissions WHERE order_id=?",
                        (o,)).fetchone()
    assert row["status"] == "paid"


def test_a_payout_is_recorded_in_the_audit_log(db, customer):
    rid, code = _enrol(db)
    reseller.attribute(db, customer, code)
    o = orders.create(db, customer, "re-listing-pro")
    payments.handle(db, _event("e1", o))
    reseller.mark_paid(db, rid, reference="BACS 12345")
    with db.tx() as c:
        row = c.execute("SELECT detail FROM events WHERE kind='commission.paid'"
                        " AND subject=?", (rid,)).fetchone()
    assert row and "BACS 12345" in row["detail"]


# ---------------------------------------------------------------- turnaround
def _order(db, customer, sku, *, paid=None, delivered=None, status="delivered"):
    from flythrough_service import orders
    oid = orders.create(db, customer, sku)
    with db.tx() as c:
        c.execute("UPDATE orders SET status=?, paid_at=?, delivered_at=?"
                  " WHERE id=?", (status, paid, delivered, oid))
    return oid


def test_turnaround_judges_each_order_against_its_own_promise(db, customer):
    """Not against a number picked for a dashboard. Every SKU carries a
    turnaround line because it is the sentence next to the money, and a 48-hour
    SKU delivered in 30 is on time while a 24-hour one delivered in 30 is not."""
    from flythrough_service import turnaround
    t0 = 1_700_000_000
    _order(db, customer, "re-listing-pro", paid=t0, delivered=t0 + 30 * 3600)
    _order(db, customer, "veh-launch", paid=t0, delivered=t0 + 30 * 3600)
    r = turnaround.measure(db, at=t0 + 40 * 3600)
    assert r.delivered == 2 and r.on_time == 1
    assert r.median_hours == 30.0


def test_a_weekly_batch_sku_is_not_late_at_hour_25(db, customer):
    """lot-25 was sold as a weekly batch. Judging it against 24 hours would
    report a bottleneck that does not exist and trigger a purchase decision on
    a promise nobody made."""
    from flythrough_service import turnaround
    t0 = 1_700_000_000
    _order(db, customer, "lot-25", paid=t0, delivered=t0 + 48 * 3600)
    assert turnaround.measure(db, at=t0 + 60 * 3600).on_time == 1


def test_turnaround_says_nothing_until_the_sample_is_big_enough(db, customer):
    """Three orders cannot tell you whether to buy a renderer. The page has to
    say so rather than print a confident 67%."""
    from flythrough_service import turnaround
    t0 = 1_700_000_000
    for i in range(3):
        _order(db, customer, "re-listing-pro", paid=t0, delivered=t0 + 40 * 3600)
    r = turnaround.measure(db, at=t0)
    assert not r.enough and not r.pressured
    assert "needed before the rate means anything" in r.headline


def test_a_sustained_miss_rate_trips_the_provider_switch_trigger(db, customer):
    """This is the whole reason the metric exists. business/12-render-provider.md
    says to buy an automatic renderer when the operator becomes the reason a
    delivery is late; the queue page is where that stops being a judgement."""
    from flythrough_service import turnaround
    t0 = 1_700_000_000
    for i in range(8):
        late = i < 3
        _order(db, customer, "re-listing-pro", paid=t0,
               delivered=t0 + (40 if late else 10) * 3600)
    r = turnaround.measure(db, at=t0)
    assert r.enough and r.pressured
    assert "12-render-provider" in r.headline

    # And the same volume delivered on time must not trip it.
    db2 = Database(Path(db.path).parent / "ok.db")
    with db2.tx() as c:
        c.execute("INSERT INTO customers(id,email,created_at) VALUES(?,?,?)",
                  ("cus_x", "b@example.com", t0))
    for i in range(8):
        _order(db2, "cus_x", "re-listing-pro", paid=t0, delivered=t0 + 10 * 3600)
    assert not turnaround.measure(db2, at=t0).pressured


def test_an_order_still_waiting_is_counted_as_overdue_not_delivered(db, customer):
    """An order that has blown its promise and is still sitting there is the
    one that matters most, and it has no delivered_at to be measured by."""
    from flythrough_service import turnaround
    t0 = 1_700_000_000
    _order(db, customer, "re-listing-pro", paid=t0, delivered=None,
           status="rendering")
    r = turnaround.measure(db, at=t0 + 30 * 3600)
    assert r.delivered == 0
    assert r.waiting == 1 and r.overdue_now == 1
    assert round(r.oldest_waiting_hours) == 30


def test_a_refunded_order_is_not_counted_as_waiting_forever(db, customer):
    """It was paid and never delivered, which is exactly the shape of a stuck
    order. Left in, every refund would permanently inflate the backlog."""
    from flythrough_service import turnaround
    t0 = 1_700_000_000
    _order(db, customer, "re-listing-pro", paid=t0, delivered=None,
           status="refunded")
    assert turnaround.measure(db, at=t0 + 99 * 3600).waiting == 0


def test_every_sku_asks_for_enough_photographs_to_keep_its_promise():
    """The runtime on the sales page is a promise: "one property, 42 seconds"
    sits next to the price. N photographs make N-1 anchored shots and there is
    no other way to reach a runtime, so the upload gate has to be derived from
    the SKU rather than a flat 4."""
    from flythrough_service import catalog_bridge as cat
    for s in cat.skus().values():
        assert cat.required_photos(s.id) >= s.beats + 1, s.id


def test_the_catalogue_tempo_reproduces_the_runtime_it_sells():
    """seconds and beats came from the pricing model; tempo was added later.
    If they disagree the catalogue is selling a film the planner cannot build,
    which is exactly the bug this whole change exists to close."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipeline"))
    from flythrough.moves import MOVES, at_tempo
    from flythrough_service import catalog_bridge as cat

    for s in cat.skus().values():
        lengths = {at_tempo(m, s.tempo).seconds for m in MOVES.values()}
        lo, hi = min(lengths) * s.beats, max(lengths) * s.beats
        assert lo <= s.seconds <= hi, (
            f"{s.id}: sold as {s.seconds}s over {s.beats} beats at {s.tempo} "
            f"tempo, which can only produce {lo}-{hi}s")
