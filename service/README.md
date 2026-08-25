# FlyThrough service

The V2 self-serve product: a customer uploads photographs, pays, and the
existing pipeline renders and delivers the film without an email round-trip.

**Status: in progress.** This directory is being built now. What is here so far:

| File | State | What it does |
|---|---|---|
| `config.py` | done | One settings object, read from `site/config.json` so a domain or price cannot disagree with the marketing site. Secrets come from the environment only. Refuses to start in production if any of the four are missing. |
| `db.py` | done | SQLite schema, 11 tables, WAL, foreign keys on. Money in integer cents. Bearer tokens stored hashed. Append-only event log. Webhook de-duplication table. |

Still to build: storage, magic-link auth, upload validation, order + Stripe
webhook handling, the render queue, delivery pages, the customer dashboard, and
the reseller ledger.

## Why SQLite

The write rate at this size is a few rows a minute. What matters is that data
cannot get half-written, that a backup is `cp service/data`, and that there is
no second daemon to keep alive. WAL plus a real transaction per state change
gives all three.

## Running

Not yet runnable. When it is, this section will say how.
