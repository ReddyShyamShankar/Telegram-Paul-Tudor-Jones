"""R:R gate tests: enforces 1:3 minimum and rejects opposing-barrier setups."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from tsg.strategy.rr import compute_rr
from tsg.strategy.smc import SMCSetup


def _flat_df(n: int = 60) -> pd.DataFrame:
    times = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {"open": 1.0, "high": 1.001, "low": 0.999, "close": 1.0, "volume": 100},
        index=times,
    )


def _setup_long(entry=1.0, ob_low=0.998, ob_high=1.001, atr=0.0010,
                sweep=0.99, bos=1.005) -> SMCSetup:
    return SMCSetup(
        direction="long", entry=entry, ob_low=ob_low, ob_high=ob_high,
        atr=atr,
        entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        sweep_level=sweep, bos_level=bos,
    )


def test_rr_long_accepts_three_to_one():
    setup = _setup_long(entry=1.0, ob_low=0.998, atr=0.0)
    df = _flat_df()
    r = compute_rr(setup, df, min_rr=3.0, atr_buf=0.0)
    assert r.ok
    assert abs(r.entry - 1.0) < 1e-9
    assert abs(r.stop_loss - 0.998) < 1e-9
    assert abs(r.take_profit - 1.006) < 1e-9
    assert r.rr == 3.0


def test_rr_long_rejects_zero_risk():
    setup = _setup_long(entry=1.0, ob_low=1.0, atr=0.0)
    r = compute_rr(setup, _flat_df(), min_rr=3.0, atr_buf=0.0)
    assert not r.ok
    assert "risk" in r.reason


def test_rr_short_symmetric():
    setup = SMCSetup(
        direction="short", entry=1.0, ob_low=0.999, ob_high=1.002,
        atr=0.0,
        entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        sweep_level=1.005, bos_level=0.995,
    )
    r = compute_rr(setup, _flat_df(), min_rr=3.0, atr_buf=0.0)
    assert r.ok
    assert abs(r.stop_loss - 1.002) < 1e-9
    assert abs(r.take_profit - 0.994) < 1e-9
