"""Scanner same-OB dedup: skip if (sweep, bos, ob_low, ob_high) matches the
last fire on this pair."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from tsg.config import Config, Pair
from tsg.scanner import Scanner
from tsg.store.db import Store
from tsg.strategy.signal import Signal


def _build_cfg(db_path: Path) -> Config:
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
        missed_entry_threshold=0.3,
    )


class _FakeFeed:
    def __init__(self, mid: float = 201.55) -> None:
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


def _signal_chf_jpy(
    sweep=201.555, bos=201.855, ob_low=201.553, ob_high=201.627,
) -> Signal:
    return Signal(
        pair="CHF_JPY", direction="long",
        entry=201.59, stop_loss=201.516, take_profit=201.813, rr=3.0,
        entry_time=datetime(2026, 5, 11, 7, 0, tzinfo=timezone.utc),
        thesis="t", timeframe="H1",
        sweep_level=sweep, bos_level=bos, ob_low=ob_low, ob_high=ob_high,
    )


def _patch_generate_signal(monkeypatch, sig: Signal) -> None:
    import tsg.scanner as scanner_mod
    monkeypatch.setattr(scanner_mod, "generate_signal",
                        lambda feed, pair, min_rr: (sig, "fired"))


@pytest.mark.asyncio
async def test_first_fire_records_signature(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path / "trades.db")
    store = Store(cfg.db_path)
    feed = _FakeFeed(mid=201.55)
    bot = _FakeBot()
    chart = _FakeChart()

    sig = _signal_chf_jpy()
    _patch_generate_signal(monkeypatch, sig)

    scanner = Scanner(cfg, store, feed, bot, chart)
    await scanner.scan_pair("CHF_JPY")

    assert len(bot.calls) == 1
    stored = store.get_last_ob_signature("CHF_JPY")
    assert stored is not None
    assert stored == (sig.sweep_level, sig.bos_level, sig.ob_low, sig.ob_high)


@pytest.mark.asyncio
async def test_dup_ob_blocks_second_fire(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path / "trades.db")
    store = Store(cfg.db_path)
    feed = _FakeFeed(mid=201.55)
    bot = _FakeBot()
    chart = _FakeChart()

    sig = _signal_chf_jpy()
    _patch_generate_signal(monkeypatch, sig)

    scanner = Scanner(cfg, store, feed, bot, chart)
    await scanner.scan_pair("CHF_JPY")
    open_trades = store.open_trades()
    assert len(open_trades) == 1
    store.close_trade(open_trades[0].id, "TP", 3.0,
                      datetime(2026, 5, 11, 8, 0, tzinfo=timezone.utc))

    await scanner.scan_pair("CHF_JPY")

    assert len(bot.calls) == 1
    import sqlite3
    conn = sqlite3.connect(cfg.db_path)
    trades_count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    dup_logs = conn.execute(
        "SELECT COUNT(*) FROM scan_runs WHERE pair='CHF_JPY' AND result='dup_ob'"
    ).fetchone()[0]
    conn.close()
    assert trades_count == 1
    assert dup_logs == 1


@pytest.mark.asyncio
async def test_new_ob_after_old_signature_allows_fire(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path / "trades.db")
    store = Store(cfg.db_path)
    feed = _FakeFeed(mid=201.55)
    bot = _FakeBot()
    chart = _FakeChart()

    sig1 = _signal_chf_jpy(sweep=201.555, bos=201.855, ob_low=201.553, ob_high=201.627)
    _patch_generate_signal(monkeypatch, sig1)
    scanner = Scanner(cfg, store, feed, bot, chart)
    await scanner.scan_pair("CHF_JPY")

    store.close_trade(store.open_trades()[0].id, "TP", 3.0,
                      datetime(2026, 5, 11, 8, 0, tzinfo=timezone.utc))

    sig2 = _signal_chf_jpy(sweep=201.700, bos=202.100, ob_low=201.700, ob_high=201.780)
    _patch_generate_signal(monkeypatch, sig2)
    await scanner.scan_pair("CHF_JPY")

    assert len(bot.calls) == 2
    stored = store.get_last_ob_signature("CHF_JPY")
    assert stored == (sig2.sweep_level, sig2.bos_level, sig2.ob_low, sig2.ob_high)


@pytest.mark.asyncio
async def test_tolerance_within_1e5_treats_as_same_ob(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path / "trades.db")
    store = Store(cfg.db_path)
    feed = _FakeFeed(mid=201.55)
    bot = _FakeBot()
    chart = _FakeChart()

    sig1 = _signal_chf_jpy(sweep=201.555, bos=201.855)
    _patch_generate_signal(monkeypatch, sig1)
    scanner = Scanner(cfg, store, feed, bot, chart)
    await scanner.scan_pair("CHF_JPY")
    store.close_trade(store.open_trades()[0].id, "TP", 3.0,
                      datetime(2026, 5, 11, 8, 0, tzinfo=timezone.utc))

    sig2 = _signal_chf_jpy(sweep=201.5550001, bos=201.8550001)
    _patch_generate_signal(monkeypatch, sig2)
    await scanner.scan_pair("CHF_JPY")

    assert len(bot.calls) == 1
