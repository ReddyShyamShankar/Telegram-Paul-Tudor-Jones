"""Validate the chart-img payload shape and entry-time anchoring."""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace

from tsg.chart.chartimg import build_payload
from tsg.strategy.signal import Signal


def _signal(direction: str = "long") -> Signal:
    return Signal(
        pair="EUR_USD",
        direction=direction,
        entry=1.0850,
        stop_loss=1.0820,
        take_profit=1.0940,
        rr=3.0,
        entry_time=datetime(2026, 5, 8, 7, 0, 0, tzinfo=timezone.utc),
        thesis="test",
        timeframe="H1",
    )


def test_payload_long_position_shape():
    p = build_payload(_signal("long"))
    assert p["symbol"] == "OANDA:EURUSD"
    assert p["interval"] == "1h"
    assert len(p["drawings"]) == 1
    d = p["drawings"][0]
    assert d["name"] == "Long Position"
    assert d["input"]["entryPrice"] == 1.0850
    assert d["input"]["stopLoss"] == 1.0820
    assert d["input"]["profitLevel"] == 1.0940
    expected = int(datetime(2026, 5, 8, 7, 0, 0, tzinfo=timezone.utc).timestamp())
    assert d["input"]["time"] == expected


def test_payload_short_position_shape():
    p = build_payload(_signal("short"))
    assert p["drawings"][0]["name"] == "Short Position"


def test_payload_h4_interval():
    sig = replace(_signal("long"), timeframe="H4")
    p = build_payload(sig)
    assert p["interval"] == "4h"
