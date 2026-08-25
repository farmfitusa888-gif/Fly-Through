"""Service configuration. Everything the service needs to know, in one place.

Reads the same site/config.json the static site does, so a domain or a price
never disagrees between the marketing page and the thing taking the money.

Secrets come from the environment and are never written to disk, never logged,
and never rendered into a page. There are exactly four, and the service refuses
to start in production without them.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"


def _load(name: str) -> dict:
    return json.loads((SITE / name).read_text())


@dataclass(frozen=True)
class Settings:
    # --- identity -----------------------------------------------------------
    brand: str
    domain: str
    short_domain: str
    contact_email: str

    # --- storage ------------------------------------------------------------
    data_dir: Path
    upload_max_bytes: int = 60 * 1024 * 1024      # per file
    upload_max_files: int = 40                     # per order
    order_max_bytes: int = 400 * 1024 * 1024       # all files in one order

    # --- security -----------------------------------------------------------
    # repr=False on every one of these. Settings gets logged, and FastAPI puts
    # local variables in tracebacks -- without this a live Stripe key rides into
    # the error log the first time anything raises near it.
    secret_key: str = field(default="", repr=False)
    stripe_secret: str = field(default="", repr=False)
    stripe_webhook_secret: str = field(default="", repr=False)
    smtp_url: str = field(default="", repr=False)      # carries SMTP credentials

    # A magic link is a bearer credential in an email. Short-lived by default:
    # long enough to walk to a laptop, short enough that a forwarded thread or a
    # shared inbox is not a standing key to someone's orders.
    login_link_ttl_s: int = 20 * 60
    session_ttl_s: int = 30 * 24 * 3600
    download_ttl_s: int = 7 * 24 * 3600

    # --- reseller -----------------------------------------------------------
    # CONFIRMED by the account holder: 25% of everything a referred customer
    # ever spends, for as long as they spend it.
    commission_rate: float = 0.25
    commission_lifetime: bool = True
    payout_minimum_usd: float = 50.0

    # --- pipeline -----------------------------------------------------------
    render_concurrency: int = 2        # OpenArt caps parallel jobs at 4; leave headroom
    dev_mode: bool = True

    allowed_upload_types: frozenset[str] = field(default_factory=lambda: frozenset({
        "image/jpeg", "image/png", "image/webp", "image/heic", "image/heif",
    }))

    @property
    def base_url(self) -> str:
        return f"http://localhost:8000" if self.dev_mode else f"https://{self.domain}"


def load(data_dir: Path | None = None, *, dev: bool | None = None) -> Settings:
    cfg = _load("config.json")
    dev_mode = os.environ.get("FLYTHROUGH_ENV", "dev") != "production" if dev is None else dev
    s = Settings(
        brand=cfg["brand"],
        domain=cfg["domain"],
        short_domain=cfg["short_domain"],
        contact_email=cfg["contact_email"],
        data_dir=Path(data_dir or os.environ.get("FLYTHROUGH_DATA", ROOT / "service" / "data")),
        secret_key=os.environ.get("FLYTHROUGH_SECRET_KEY", ""),
        stripe_secret=os.environ.get("STRIPE_SECRET_KEY", ""),
        stripe_webhook_secret=os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
        smtp_url=os.environ.get("FLYTHROUGH_SMTP_URL", ""),
        dev_mode=dev_mode,
    )
    if not dev_mode:
        missing = [n for n, v in (
            ("FLYTHROUGH_SECRET_KEY", s.secret_key),
            ("STRIPE_SECRET_KEY", s.stripe_secret),
            ("STRIPE_WEBHOOK_SECRET", s.stripe_webhook_secret),
            ("FLYTHROUGH_SMTP_URL", s.smtp_url),
        ) if not v]
        if missing:
            # Refuse rather than degrade. A production service that silently
            # runs without a webhook secret accepts forged payment events.
            raise RuntimeError(
                "refusing to start in production without: " + ", ".join(missing))
    return s
