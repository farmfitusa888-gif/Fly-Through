"""Tests for the service layer."""

import sqlite3
import sys
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
