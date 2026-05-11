"""Scanner missed-entry filter: abort if current market price has drifted past
the OB-midpoint entry by more than threshold x SL distance."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from tsg.config import Config, Pair
from tsg.scanner import Scanner
from tsg.store.db import Store
from tsg.strategy.signal import Signal


def _build_cfg(db_path: Path, missed_entry_threshold: float = 0.3) -> Config:
    return Config(
        ctrader_client_id="x",
        ctrader_client_secret="x",
        ctrader_refresh_token="x",
        ctrader_account_id=12345678,
        ctrader_env="demo",
        ctrader_host="demo.ctraderapi.com",
        ctrader_port=5035,
        tg_api_id=1,
        tg_api_hash="x",
        tg_phone="+15551234567",
        tg_session_path=db_path.parent / "tsg.session",
        tg_channel_ids=(-1001234567890,),
        chart_img_key="x",
        db_path=db_path,
        cache_dir=db_path.parent / "charts",
        log_level="WARNING",
        tracker_interval_seconds=60,
        max_concurrent=5,
        min_rr=3.0,
        pairs=(Pair("CHF_JPY", 0.01),),
        enable_execution=False,
        risk_pct=0.01,
        daily_loss_r_cap=3.0,
        allow_live=False,
        execution_max_lots=100.0,
        missed_entry_threshold=missed_entry_threshold,
    )


class _FakeFeed:
    def __init__(self, mid: float) -> None:
        self.mid = mid

    def fetch_price(self, pair: str) -> dict:
        return {"bid": self.mid - 0.0005, "ask": self.mid + 0.0005, "mid": self.mid,
                "time": datetime.now(timezone.utc)}


class _FakeBot:
    def __init__(self) -> None:
        self.calls: list[Any] = []
        self.channel_ids = (-1001234567890,)

    async def send_signal(self, signal, png, pair_pip=0.0001):
        self.calls.append(signal)
        return {self.channel_ids[0]: 1234}


class _FakeChart:
    def render(self, signal, status="OPEN", closed_at=None, signal_id=None):
        return b"\x89PNG\r\n\x1a\n"


def _signal_long(entry=201.59, sl=201.516, tp=201.813) -> Signal:
    return Signal(
        pair="CHF_JPY", direction="long",
        entry=entry, stop_loss=sl, take_profit=tp, rr=3.0,
        entry_time=datetime(2026, 5, 11, 7, 0, tzinfo=timezone.utc),
        thesis="t", timeframe="H1",
    )


def _signal_short(entry=1.10, sl=1.105, tp=1.085) -> Signal:
    return Signal(
        pair="CHF_JPY", direction="short",
        entry=entry, stop_loss=sl, take_profit=tp, rr=3.0,
        entry_time=datetime(2026, 5, 11, 7, 0, tzinfo=timezone.utc),
        thesis="t", timeframe="H1",
    )


def _patch_generate_signal(monkeypatch, sig: Signal) -> None:
    import tsg.scanner as scanner_mod
    monkeypatch.setattr(scanner_mod, "generate_signal",
                        lambda feed, pair, min_rr: (sig, "fired"))


@pytest.mark.asyncio
async def test_missed_entry_rejects_long_when_price_far_above_entry(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path / "trades.db", missed_entry_threshold=0.3)
    store = Store(cfg.db_path)
    feed = _FakeFeed(mid=201.70)
    bot = _FakeBot()
    chart = _FakeChart()

    _patch_generate_signal(monkeypatch, _signal_long())

    scanner = Scanner(cfg, store, feed, bot, chart)
    await scanner.scan_pair("CHF_JPY")

    assert bot.calls == []
    assert store.open_trades() == []
    import sqlite3
    conn = sqlite3.connect(cfg.db_path)
    rows = conn.execute("SELECT result FROM scan_runs WHERE pair='CHF_JPY'").fetchall()
    conn.close()
    assert any(r[0].startswith("missed_entry:") for r in rows)


@pytest.mark.asyncio
async def test_missed_entry_allows_long_when_price_near_entry(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path / "trades.db", missed_entry_threshold=0.3)
    store = Store(cfg.db_path)
    feed = _FakeFeed(mid=201.60)
    bot = _FakeBot()
    chart = _FakeChart()

    _patch_generate_signal(monkeypatch, _signal_long())

    scanner = Scanner(cfg, store, feed, bot, chart)
    await scanner.scan_pair("CHF_JPY")

    assert len(bot.calls) == 1
    assert len(store.open_trades()) == 1


@pytest.mark.asyncio
async def test_missed_entry_allows_long_when_price_below_entry(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path / "trades.db", missed_entry_threshold=0.3)
    store = Store(cfg.db_path)
    feed = _FakeFeed(mid=201.55)
    bot = _FakeBot()
    chart = _FakeChart()

    _patch_generate_signal(monkeypatch, _signal_long())

    scanner = Scanner(cfg, store, feed, bot, chart)
    await scanner.scan_pair("CHF_JPY")

    assert len(bot.calls) == 1
    assert len(store.open_trades()) == 1


@pytest.mark.asyncio
async def test_missed_entry_rejects_short_when_price_far_below_entry(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path / "trades.db", missed_entry_threshold=0.3)
    store = Store(cfg.db_path)
    feed = _FakeFeed(mid=1.094)
    bot = _FakeBot()
    chart = _FakeChart()

    _patch_generate_signal(monkeypatch, _signal_short())

    scanner = Scanner(cfg, store, feed, bot, chart)
    await scanner.scan_pair("CHF_JPY")

    assert bot.calls == []
    assert store.open_trades() == []


@pytest.mark.asyncio
async def test_missed_entry_falls_through_on_feed_error(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path / "trades.db", missed_entry_threshold=0.3)
    store = Store(cfg.db_path)

    class _BrokenFeed:
        def fetch_price(self, pair):
            raise RuntimeError("temporary feed glitch")

    bot = _FakeBot()
    chart = _FakeChart()

    _patch_generate_signal(monkeypatch, _signal_long())

    scanner = Scanner(cfg, store, _BrokenFeed(), bot, chart)
    await scanner.scan_pair("CHF_JPY")

    assert len(bot.calls) == 1
    assert len(store.open_trades()) == 1
