"""SQLite storage. One file, no server, fully transactional.

SQLite is not a compromise here. The whole business is one operator and a queue
that renders two jobs at a time; the write rate is a few rows a minute at the
absolute peak. What actually matters at this size is that the data cannot get
lost or half-written, that a backup is `cp`, and that there is no second daemon
to keep alive at 3am. WAL mode plus a real transaction per state change gives
all of that.

Money lives in INTEGER CENTS. Never floats: 0.1 + 0.2 != 0.3, and a commission
ledger that disagrees with an invoice by a cent is a ledger nobody trusts.
"""

from __future__ import annotations

import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS customers (
  id           TEXT PRIMARY KEY,
  email        TEXT NOT NULL UNIQUE,
  name         TEXT NOT NULL DEFAULT '',
  referred_by  TEXT REFERENCES resellers(id),
  created_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS resellers (
  id           TEXT PRIMARY KEY,
  email        TEXT NOT NULL UNIQUE,
  name         TEXT NOT NULL DEFAULT '',
  code         TEXT NOT NULL UNIQUE,
  rate         REAL NOT NULL,
  lifetime     INTEGER NOT NULL DEFAULT 1,
  created_at   INTEGER NOT NULL
);

-- Bearer credentials are stored HASHED. A stolen database backup must not be a
-- stack of working login links.
CREATE TABLE IF NOT EXISTS login_tokens (
  token_hash   TEXT PRIMARY KEY,
  email        TEXT NOT NULL,
  expires_at   INTEGER NOT NULL,
  used_at      INTEGER
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash   TEXT PRIMARY KEY,
  customer_id  TEXT REFERENCES customers(id),
  reseller_id  TEXT REFERENCES resellers(id),
  expires_at   INTEGER NOT NULL,
  created_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
  id             TEXT PRIMARY KEY,
  customer_id    TEXT NOT NULL REFERENCES customers(id),
  sku            TEXT NOT NULL,
  vertical       TEXT NOT NULL,
  price_cents    INTEGER NOT NULL,
  status         TEXT NOT NULL,     -- draft|awaiting_payment|paid|rendering|delivered|failed|refunded
  brief          TEXT NOT NULL DEFAULT '{}',
  stripe_ref     TEXT UNIQUE,
  referred_by    TEXT REFERENCES resellers(id),
  created_at     INTEGER NOT NULL,
  paid_at        INTEGER,
  delivered_at   INTEGER
);
CREATE INDEX IF NOT EXISTS orders_by_customer ON orders(customer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS orders_by_status ON orders(status);

CREATE TABLE IF NOT EXISTS uploads (
  id          TEXT PRIMARY KEY,
  order_id    TEXT NOT NULL REFERENCES orders(id),
  filename    TEXT NOT NULL,
  mime        TEXT NOT NULL,
  bytes       INTEGER NOT NULL,
  sha256      TEXT NOT NULL,
  path        TEXT NOT NULL,
  room_key    TEXT NOT NULL DEFAULT '',
  position    INTEGER NOT NULL DEFAULT 0,
  created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS uploads_by_order ON uploads(order_id, position);

CREATE TABLE IF NOT EXISTS jobs (
  id           TEXT PRIMARY KEY,
  order_id     TEXT NOT NULL REFERENCES orders(id),
  status       TEXT NOT NULL,      -- queued|running|done|failed
  attempts     INTEGER NOT NULL DEFAULT 0,
  error        TEXT NOT NULL DEFAULT '',
  queued_at    INTEGER NOT NULL,
  started_at   INTEGER,
  finished_at  INTEGER
);
CREATE INDEX IF NOT EXISTS jobs_by_status ON jobs(status, queued_at);

CREATE TABLE IF NOT EXISTS deliverables (
  id          TEXT PRIMARY KEY,
  order_id    TEXT NOT NULL REFERENCES orders(id),
  kind        TEXT NOT NULL,       -- master|vertical|thumb|disclosure|originals
  path        TEXT NOT NULL,
  bytes       INTEGER NOT NULL,
  created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS deliverables_by_order ON deliverables(order_id);

CREATE TABLE IF NOT EXISTS commissions (
  id            TEXT PRIMARY KEY,
  reseller_id   TEXT NOT NULL REFERENCES resellers(id),
  order_id      TEXT NOT NULL REFERENCES orders(id) UNIQUE,
  amount_cents  INTEGER NOT NULL,
  rate          REAL NOT NULL,
  status        TEXT NOT NULL,     -- accrued|payable|paid|reversed
  created_at    INTEGER NOT NULL,
  paid_at       INTEGER
);
CREATE INDEX IF NOT EXISTS commissions_by_reseller ON commissions(reseller_id, status);

-- What happened AFTER we delivered. The point of the whole business, and the
-- one asset here a competitor cannot buy: after a couple of hundred rows, the
-- brief that produces a faster sale is knowable rather than guessable.
-- Nullable everywhere because most orders will never come back with an answer,
-- and an unanswered order must not look like a failed one.
CREATE TABLE IF NOT EXISTS outcomes (
  order_id     TEXT PRIMARY KEY REFERENCES orders(id),
  result       TEXT NOT NULL,          -- sold|listed|withdrawn|unknown
  days_to_sell INTEGER,
  note         TEXT NOT NULL DEFAULT '',
  asked_at     INTEGER,
  answered_at  INTEGER
);
CREATE INDEX IF NOT EXISTS outcomes_by_result ON outcomes(result);

-- Append-only. Every state change money depends on leaves a row here.
CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  at          INTEGER NOT NULL,
  kind        TEXT NOT NULL,
  subject     TEXT NOT NULL DEFAULT '',
  detail      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS events_by_subject ON events(subject, at DESC);

-- Stripe redelivers webhooks. Recording every event id we have already acted on
-- is what makes "charge once, render once, pay commission once" true.
CREATE TABLE IF NOT EXISTS processed_webhooks (
  event_id    TEXT PRIMARY KEY,
  at          INTEGER NOT NULL
);
"""


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(10)}"


def now() -> int:
    return int(time.time())


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA busy_timeout=30000")
        return c

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """One transaction. IMMEDIATE takes the write lock up front rather than
        on first write, which is what stops two workers from both reading a
        queued job and both rendering it."""
        c = self.connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
        finally:
            c.close()

    def log(self, conn: sqlite3.Connection, kind: str, subject: str = "",
            detail: str = "") -> None:
        conn.execute("INSERT INTO events(at, kind, subject, detail) VALUES(?,?,?,?)",
                     (now(), kind, subject, detail))
