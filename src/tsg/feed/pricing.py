"""Thin sync price-fetch facade. Delegates to CTraderClient.fetch_price."""
from __future__ import annotations

from datetime import datetime, timezone

from .client import CTraderClient


def fetch_pricing(client: CTraderClient, instrument: str) -> dict:
    """Returns {bid, ask, mid: float, time: datetime UTC}."""
    return client.fetch_price(instrument)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
