"""Thin sync price-fetch facade. Delegates to CTraderClient.fetch_price."""
from __future__ import annotations

from datetime import datetime, timezone

from .client import CTraderClient


def fetch_pricing(client: CTraderClient, instrument: str) -> dict:
    """Returns {bid, ask, mid: float, time: datetime UTC}."""
    return client.fetch_price(instrument)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def usd_per_quote(client: CTraderClient, pair: str,
                  pair_current_price: float) -> float | None:
    """Return how many USD 1 unit of the pair's QUOTE currency is worth.

    Used by sizing.compute_lots() to convert per-lot loss (denominated in the
    pair's quote currency) into USD account terms.

    Resolution rules for pair X_Y:
        - Y == USD             -> 1.0
        - X == USD             -> 1 / pair_current_price (USD/Y rate)
        - cross, USD_Y feed    -> 1 / fetch_price(USD_Y).mid
        - cross, Y_USD feed    -> fetch_price(Y_USD).mid
        - none of the above    -> None (caller treats as unsupported)
    """
    parts = pair.split("_")
    if len(parts) != 2:
        return None
    base, quote = parts
    if quote == "USD":
        return 1.0
    if base == "USD":
        if pair_current_price <= 0:
            return None
        return 1.0 / pair_current_price
    # Cross pair: try USD_Y direct then Y_USD inverse.
    for candidate, invert in ((f"USD_{quote}", True), (f"{quote}_USD", False)):
        try:
            tick = client.fetch_price(candidate)
            rate = float(tick["mid"])
            if rate <= 0:
                continue
            return 1.0 / rate if invert else rate
        except Exception:
            continue
    return None
