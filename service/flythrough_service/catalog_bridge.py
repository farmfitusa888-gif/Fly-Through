"""The service's view of the catalogue.

Imports model/catalog.py rather than re-declaring anything. There is exactly one
place a price is defined, and this is not it -- if the two ever disagree, the
customer sees one number on the page and is charged another, which is the single
worst bug this system could have.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT / "model", ROOT / "pipeline"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from catalog import CATALOG, intake  # noqa: E402


class UnknownSku(KeyError):
    pass


@lru_cache(maxsize=1)
def skus() -> dict:
    return {s.id: s for s in CATALOG}


def get(sku_id: str):
    s = skus().get(sku_id)
    if s is None:
        raise UnknownSku(sku_id)
    return s


def price_cents(sku_id: str) -> int:
    """Cents, from the model's dollars. round() not int(): int(24899.999...)
    truncates to 24899 and undercharges by a cent forever."""
    return round(get(sku_id).price * 100)


def intake_for(vertical: str) -> list[str]:
    """The portal uploads files directly, so it never asks for a photo link."""
    return intake(vertical, uploads_inline=True)


def required_photos(sku_id: str) -> int:
    """Floor below which the pipeline cannot build a watchable film. Mirrors the
    planner's own audit so a customer is told at UPLOAD time, not after paying."""
    return 4 if get(sku_id).vertical == "rooms" else 3
