"""Tracker behaviour: TP/SL detection, scratch flag, multi-channel outcome
posting (one quote-reply per recorded trade_message)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from tsg.config import Config, Pair
from tsg.store.db import Store
from tsg.tracker import tracker as tracker_mod
from tsg.tracker.tracker import Tracker


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
        tg_channel_ids=(-1001234567890, -1009876543210),
        chart_img_key="x",
        db_path=db_path,
        cache_dir=db_path.parent / "charts",
        log_level="WARNING",
        tracker_interval_seconds=60,
        max_concurrent=5,
        min_rr=3.0,
        pairs=(Pair("EUR_USD", 0.0001),),
        enable_execution=False,
        risk_pct=0.01,
        daily_loss_r_cap=3.0,
        allow_live=False,
        execution_max_lots=100.0,
    )


class _FakeChart:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def render(self, signal, status="OPEN", closed_at=None, signal_id=None):
        self.calls.append((signal.pair, status, signal_id))
        return b"\x89PNG\r\n\x1a\n"


class _FakeBot:
    def __init__(self, channel_ids=(-1001234567890, -1009876543210)) -> None:
        self.signals: list[Any] = []
        self.outcomes: list[Any] = []
        self.channel_ids = tuple(channel_ids)
        self._next_id = 1000

    async def send_signal(self, signal, png, pair_pip=0.0001) -> dict[int, int]:
        self.signals.append(signal)
        out: dict[int, int] = {}
        for ch in self.channel_ids:
            self._next_id += 1
            out[ch] = self._next_id
        return out

    async def reply_outcome(self, messages, trade, outcome, png, note,
                            pair_pip=0.0001):
        self.outcomes.append((trade.id, outcome, note,
                              [(m.channel_id, m.message_id) for m in messages]))


def _seed_messages(store: Store, trade_id: int, channel_ids) -> None:
    """Simulate scanner having posted to all channels."""
    ts = datetime(2026, 5, 8, 7, 0, 1, tzinfo=timezone.utc)
    for i, ch in enumerate(channel_ids, start=1):
        store.add_trade_message(trade_id, ch, 500 + i, ts)


@pytest.mark.asyncio
async def test_tracker_closes_long_on_tp(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path / "trades.db")
    store = Store(cfg.db_path)
    tid = store.insert_trade(
        pair="EUR_USD", direction="long",
        entry=1.0, stop_loss=0.99, take_profit=1.03, rr=3.0,
        entry_time=datetime(2026, 5, 8, 7, 0, tzinfo=timezone.utc),
        thesis="t", timeframe="H1",
    )
    _seed_messages(store, tid, cfg.tg_channel_ids)

    monkeypatch.setattr(tracker_mod, "fetch_pricing",
                        lambda c, i: {"bid": 1.04, "ask": 1.041, "mid": 1.0405,
                                      "time": datetime.now(timezone.utc)})

    bot = _FakeBot(cfg.tg_channel_ids)
    chart = _FakeChart()
    t = Tracker(cfg, store, feed=None, bot=bot, chart=chart)
    await t.run_once()

    assert bot.outcomes and bot.outcomes[0][1] == "TP"
    # Multi-channel: outcome should reference both channels
    posted = bot.outcomes[0][3]
    assert len(posted) == 2
    assert {p[0] for p in posted} == {str(c) for c in cfg.tg_channel_ids}
    assert store.get(tid).status == "TP"


@pytest.mark.asyncio
async def test_tracker_closes_short_on_sl(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path / "trades.db")
    store = Store(cfg.db_path)
    tid = store.insert_trade(
        pair="EUR_USD", direction="short",
        entry=1.0, stop_loss=1.01, take_profit=0.97, rr=3.0,
        entry_time=datetime(2026, 5, 8, 7, 0, tzinfo=timezone.utc),
        thesis="t", timeframe="H1",
    )
    _seed_messages(store, tid, cfg.tg_channel_ids)
    monkeypatch.setattr(tracker_mod, "fetch_pricing",
                        lambda c, i: {"bid": 1.012, "ask": 1.013, "mid": 1.0125,
                                      "time": datetime.now(timezone.utc)})

    bot = _FakeBot(cfg.tg_channel_ids)
    chart = _FakeChart()
    t = Tracker(cfg, store, feed=None, bot=bot, chart=chart)
    await t.run_once()

    assert bot.outcomes and bot.outcomes[0][1] == "SL"
    assert store.get(tid).status == "SL"


@pytest.mark.asyncio
async def test_tracker_handles_scratch(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path / "trades.db")
    store = Store(cfg.db_path)
    tid = store.insert_trade(
        pair="EUR_USD", direction="long",
        entry=1.0, stop_loss=0.99, take_profit=1.03, rr=3.0,
        entry_time=datetime(2026, 5, 8, 7, 0, tzinfo=timezone.utc),
        thesis="t", timeframe="H1",
    )
    _seed_messages(store, tid, cfg.tg_channel_ids)
    store.flag_scratch(tid)

    def _raise(*a, **k):
        raise AssertionError("fetch_pricing should not be called for scratch path")
    monkeypatch.setattr(tracker_mod, "fetch_pricing", _raise)

    bot = _FakeBot(cfg.tg_channel_ids)
    chart = _FakeChart()
    t = Tracker(cfg, store, feed=None, bot=bot, chart=chart)
    await t.run_once()

    assert bot.outcomes and bot.outcomes[0][1] == "SCRATCHED"
    assert store.get(tid).status == "SCRATCHED"


@pytest.mark.asyncio
async def test_tracker_no_op_when_price_inside_brackets(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path / "trades.db")
    store = Store(cfg.db_path)
    tid = store.insert_trade(
        pair="EUR_USD", direction="long",
        entry=1.0, stop_loss=0.99, take_profit=1.03, rr=3.0,
        entry_time=datetime(2026, 5, 8, 7, 0, tzinfo=timezone.utc),
        thesis="t", timeframe="H1",
    )
    _seed_messages(store, tid, cfg.tg_channel_ids)
    monkeypatch.setattr(tracker_mod, "fetch_pricing",
                        lambda c, i: {"bid": 1.005, "ask": 1.006, "mid": 1.0055,
                                      "time": datetime.now(timezone.utc)})

    bot = _FakeBot(cfg.tg_channel_ids)
    chart = _FakeChart()
    t = Tracker(cfg, store, feed=None, bot=bot, chart=chart)
    await t.run_once()

    assert not bot.outcomes
    assert store.get(tid).status == "OPEN"


def test_store_trade_messages_roundtrip(tmp_path):
    cfg = _build_cfg(tmp_path / "trades.db")
    store = Store(cfg.db_path)
    tid = store.insert_trade(
        pair="EUR_USD", direction="long",
        entry=1.0, stop_loss=0.99, take_profit=1.03, rr=3.0,
        entry_time=datetime(2026, 5, 8, 7, 0, tzinfo=timezone.utc),
        thesis="t", timeframe="H1",
    )
    ts = datetime(2026, 5, 8, 7, 0, 1, tzinfo=timezone.utc)
    store.add_trade_message(tid, -1001, 11, ts)
    store.add_trade_message(tid, -1002, 22, ts)
    msgs = store.messages_for_trade(tid)
    assert len(msgs) == 2
    assert {m.channel_id for m in msgs} == {"-1001", "-1002"}
    assert {m.message_id for m in msgs} == {11, 22}
