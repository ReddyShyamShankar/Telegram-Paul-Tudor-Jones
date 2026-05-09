"""Always-on tracker. Polls OANDA every N seconds, closes trades that hit SL/TP
or that the user manually scratched, and quote-replies the original Telegram
signal message with the outcome chart + note.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Mapping

from ..chart.chartimg import ChartImg
from ..config import Config
from ..feed.client import CTraderClient
from ..feed.pricing import fetch_pricing, now_utc
from ..post_trade.notes import generate_note
from ..store.db import Store, TradeRow
from ..strategy.signal import Signal
from ..tg.bot import TelegramBroadcaster


log = logging.getLogger(__name__)


class Tracker:
    def __init__(self, cfg: Config, store: Store, feed: CTraderClient,
                 bot: TelegramBroadcaster, chart: ChartImg) -> None:
        self.cfg = cfg
        self.store = store
        self.feed = feed
        self.bot = bot
        self.chart = chart
        self.pip_map: Mapping[str, float] = {p.instrument: p.pip for p in cfg.pairs}

    @staticmethod
    def _hit(direction: str, bid: float, ask: float,
             entry: float, sl: float, tp: float) -> str | None:
        """Return 'TP' / 'SL' / None for a price tick.
        Conservative: if both sides crossed in same tick, prefer SL.
        For long: bid is the price we close at.
        For short: ask is the price we close at.
        """
        if direction == "long":
            if bid <= sl:
                return "SL"
            if bid >= tp:
                return "TP"
        else:
            if ask >= sl:
                return "SL"
            if ask <= tp:
                return "TP"
        return None

    def _pnl_r(self, trade: TradeRow, status: str) -> float:
        if status == "TP":
            return float(trade.rr)
        if status == "SL":
            return -1.0
        return 0.0

    async def _process_trade(self, trade: TradeRow) -> None:
        if trade.scratch_requested:
            await self._close_and_post(trade, "SCRATCHED")
            return

        try:
            tick = fetch_pricing(self.feed, trade.pair)
        except Exception as e:
            log.warning("pricing fetch failed for %s: %s", trade.pair, e)
            return

        bid, ask = tick["bid"], tick["ask"]
        self.store.update_extremes(trade.id, high=max(bid, ask), low=min(bid, ask))

        outcome = self._hit(trade.direction, bid, ask,
                            trade.entry, trade.stop_loss, trade.take_profit)
        if outcome is not None:
            await self._close_and_post(trade, outcome)

    async def _close_and_post(self, trade: TradeRow, status: str) -> None:
        ts = now_utc()
        pnl = self._pnl_r(trade, status)
        self.store.close_trade(trade.id, status, pnl, ts)

        fresh = self.store.get(trade.id)
        if fresh is None:
            return
        note = generate_note(fresh, status)

        sig = Signal(
            pair=trade.pair,
            direction=trade.direction,
            entry=trade.entry,
            stop_loss=trade.stop_loss,
            take_profit=trade.take_profit,
            rr=trade.rr,
            entry_time=datetime.fromisoformat(trade.entry_time),
            thesis=trade.thesis or "",
            timeframe=trade.timeframe or "H1",
        )
        try:
            png = self.chart.render(sig, status="CLOSED",
                                    closed_at=ts, signal_id=trade.id)
        except Exception as e:
            log.error("chart render failed for trade %s: %s", trade.id, e)
            png = b""

        messages = self.store.messages_for_trade(trade.id)
        if not messages:
            log.warning("no telegram messages recorded for trade %s; "
                        "outcome will not be quote-replied", trade.id)
        try:
            await self.bot.reply_outcome(
                messages, fresh, status, png, note,
                pair_pip=self.pip_map.get(trade.pair, 0.0001),
            )
        except Exception as e:
            log.error("telegram reply failed for trade %s: %s", trade.id, e)

    async def run_once(self) -> None:
        for trade in self.store.open_trades():
            await self._process_trade(trade)

    async def run_forever(self) -> None:
        log.info("tracker starting; poll interval = %ss", self.cfg.tracker_interval_seconds)
        while True:
            try:
                await self.run_once()
            except Exception as e:
                log.exception("tracker tick error: %s", e)
            await asyncio.sleep(self.cfg.tracker_interval_seconds)
