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
    assert p["theme"] == "light"
    assert len(p["drawings"]) == 1
    d = p["drawings"][0]
    assert d["name"] == "Long Position"
    # chart-img v2 schema: entryPrice / stopPrice / targetPrice / startDatetime
    assert d["input"]["entryPrice"] == 1.0850
    assert d["input"]["stopPrice"] == 1.0820
    assert d["input"]["targetPrice"] == 1.0940
    assert d["input"]["startDatetime"] == "2026-05-08T07:00:00+00:00"
    # Override keys: profit uses docs-sanctioned `profitZoneColor`,
    # stop uses legacy `stopBackground` (only key chart-img actually paints
    # for the stop zone — see data/probe_*.png).
    o = d["override"]
    assert o["profitZoneColor"].startswith("rgba(")
    assert o["stopBackground"].startswith("rgba(")
    assert 0 <= o["profitZoneTransparency"] <= 100
    assert 0 <= o["stopBackgroundTransparency"] <= 100
    assert o["lineColor"].startswith("rgba(")
    # text overlays explicitly disabled — caption carries the numbers
    assert o["showLabel"] is False
    assert o["showStats"] is False


def test_payload_short_position_shape():
    p = build_payload(_signal("short"))
    d = p["drawings"][0]
    assert d["name"] == "Short Position"
    assert d["input"]["entryPrice"] == 1.0850
    assert d["input"]["stopPrice"] == 1.0820
    assert d["input"]["targetPrice"] == 1.0940
    assert "startDatetime" in d["input"]


def test_payload_h4_interval():
    sig = replace(_signal("long"), timeframe="H4")
    p = build_payload(sig)
    assert p["interval"] == "4h"


def test_payload_explicit_interval_override():
    """Composite renderer passes interval per pane (1D / 4h / 1h / 15m)."""
    for iv in ("1D", "4h", "1h", "15m"):
        p = build_payload(_signal("long"), interval=iv)
        assert p["interval"] == iv
        assert p["theme"] == "light"
        # chart-img only accepts these fixed ranges
        assert p["range"] in ("1D", "5D", "1M", "3M", "6M", "1Y")


def test_payload_per_pane_dimensions():
    p = build_payload(_signal("long"), interval="15m", width=800, height=450)
    assert p["width"] == 800
    assert p["height"] == 450


def test_payload_no_legacy_field_names():
    """Regression: chart-img v2 returns 422 if it sees these legacy keys.

    Note: `profitBackground` / `stopBackground` are intentionally re-added
    alongside the docs-sanctioned `profitZoneColor` / `stopZoneColor` because
    the API silently picks one or the other per the color probe (see
    data/probe_*.png). We send both. Lowercase-l keys remain forbidden.
    """
    p = build_payload(_signal("long"))
    inp = p["drawings"][0]["input"]
    assert "stopLoss" not in inp
    assert "profitLevel" not in inp
    assert "time" not in inp
    o = p["drawings"][0]["override"]
    assert "linecolor" not in o
    assert "linewidth" not in o
    # profit uses docs-sanctioned key, stop uses legacy key (per probe results)
    assert "profitZoneColor" in o
    assert "stopBackground" in o
    assert "profitBackground" not in o
    assert "stopZoneColor" not in o
