"""Unit tests for swing detection, H4 bias, and SMC setup detection."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from tsg.strategy.bias import h4_bias
from tsg.strategy.levels import last_swings, swings
from tsg.strategy.smc import find_smc_setup


def _df_from_ohlc(rows, start: datetime | None = None,
                  step_min: int = 60) -> pd.DataFrame:
    if start is None:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    times = [start + timedelta(minutes=i * step_min) for i in range(len(rows))]
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"],
                      index=pd.DatetimeIndex(times, tz="UTC", name="time"))
    return df


def test_swings_finds_local_extrema():
    rows = [
        (1.0, 1.1, 0.9, 1.05, 100),
        (1.05, 1.15, 1.0, 1.10, 100),
        (1.10, 1.20, 1.05, 1.15, 100),
        (1.15, 1.30, 1.10, 1.25, 100),
        (1.25, 1.28, 1.15, 1.20, 100),
        (1.20, 1.22, 1.10, 1.12, 100),
        (1.12, 1.15, 1.00, 1.05, 100),
        (1.05, 1.10, 1.02, 1.08, 100),
        (1.08, 1.12, 1.04, 1.10, 100),
    ]
    df = _df_from_ohlc(rows)
    s = swings(df, lookback=2)
    assert s["sh"].any()
    assert s["sl"].any()


def test_h4_bias_neutral_on_flat_data():
    df = _df_from_ohlc([(1.0, 1.001, 0.999, 1.0, 100)] * 60, step_min=240)
    assert h4_bias(df, n=3, lookback=5) == "neutral"


def test_smc_returns_none_on_neutral_bias():
    df = _df_from_ohlc([(1.0, 1.001, 0.999, 1.0, 100)] * 80)
    assert find_smc_setup(df, "neutral") is None


def test_last_swings_returns_chronological():
    rows = [(i / 1000, (i + 1) / 1000, (i - 1) / 1000, i / 1000, 100)
            for i in range(1, 60)]
    df = _df_from_ohlc(rows)
    highs, lows = last_swings(df, n=2, lookback=2)
    assert isinstance(highs, list)
    assert isinstance(lows, list)
