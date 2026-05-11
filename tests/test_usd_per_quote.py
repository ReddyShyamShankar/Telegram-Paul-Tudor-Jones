"""usd_per_quote helper resolves the USD-per-quote-currency rate for any pair
in the whitelist, using direct USD/Y lookup or Y/USD inverse fallback."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tsg.feed.pricing import usd_per_quote


class _FakeClient:
    def __init__(self, prices: dict[str, float]) -> None:
        self.prices = prices
        self.calls: list[str] = []

    def fetch_price(self, pair: str) -> dict:
        self.calls.append(pair)
        if pair not in self.prices:
            raise RuntimeError(f"no price for {pair}")
        return {"bid": self.prices[pair] - 0.0001,
                "ask": self.prices[pair] + 0.0001,
                "mid": self.prices[pair],
                "time": datetime.now(timezone.utc)}


def test_quote_is_usd_returns_one():
    c = _FakeClient({})
    assert usd_per_quote(c, "EUR_USD", 1.0850) == 1.0


def test_base_is_usd_returns_inverse_of_current_price():
    c = _FakeClient({})
    rate = usd_per_quote(c, "USD_JPY", 150.0)
    assert rate is not None
    assert abs(rate - 1.0 / 150.0) < 1e-9


def test_cross_pair_uses_usd_direct_when_available():
    """CHF_JPY: quote=JPY. USD_JPY = 150 -> rate = 1/150."""
    c = _FakeClient({"USD_JPY": 150.0})
    rate = usd_per_quote(c, "CHF_JPY", 201.59)
    assert rate is not None
    assert abs(rate - 1.0 / 150.0) < 1e-9
    assert c.calls == ["USD_JPY"]


def test_cross_pair_falls_back_to_y_usd_inverse():
    """EUR_AUD: quote=AUD. USD_AUD not in feed -> fall through to AUD_USD = 0.66.
    rate = 0.66 directly."""
    c = _FakeClient({"AUD_USD": 0.66})
    rate = usd_per_quote(c, "EUR_AUD", 1.65)
    assert rate is not None
    assert abs(rate - 0.66) < 1e-9
    assert c.calls == ["USD_AUD", "AUD_USD"]


def test_cross_pair_returns_none_when_no_usd_rate_available():
    c = _FakeClient({})
    assert usd_per_quote(c, "EUR_AUD", 1.65) is None


def test_malformed_pair_returns_none():
    c = _FakeClient({})
    assert usd_per_quote(c, "EURUSD", 1.085) is None
    assert usd_per_quote(c, "EUR_USD_JPY", 1.0) is None


def test_base_is_usd_with_zero_price_returns_none():
    c = _FakeClient({})
    assert usd_per_quote(c, "USD_JPY", 0.0) is None
    assert usd_per_quote(c, "USD_JPY", -1.0) is None
