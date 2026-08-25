#!/usr/bin/env python3
"""Run the service.

    python3 service/run.py                 # dev, on :8000
    FLYTHROUGH_ENV=production python3 service/run.py

In dev, mail is written to service/data/outbox.jsonl instead of being sent, and
the render worker refuses to start unless a provider is configured -- so the
whole shop, dashboard and ledger are usable on a laptop with no credentials and
no risk of emailing a real person from a test.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from flythrough_service.app import create_app  # noqa: E402
from flythrough_service.config import load  # noqa: E402


def main() -> int:
    settings = load()
    app = create_app(settings, start_worker=bool(os.environ.get("FLYTHROUGH_PROVIDER")))
    print(f"  {settings.brand} on {settings.base_url}")
    print(f"  data     {settings.data_dir}")
    print(f"  mail     {'live' if settings.smtp_url else 'spooled to outbox.jsonl'}")
    print(f"  renders  {'worker running' if os.environ.get('FLYTHROUGH_PROVIDER') else 'worker off (no FLYTHROUGH_PROVIDER)'}")
    uvicorn.run(app, host="127.0.0.1" if settings.dev_mode else "0.0.0.0",
                port=int(os.environ.get("PORT", 8000)), log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
