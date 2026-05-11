"""Bar-close scanner. Iterates the whitelisted pairs, generates signals,
and on R:R-passed signals: persists to SQLite, renders chart-img, posts to
Telegram, and stamps the resulting message_id back onto the trade row.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from typing import Mapping

from .chart.chartimg import ChartImg
from .config import Config
from .execution.sizing import compute_lots
from .feed.client import CTraderClient
from .feed.pricing import now_utc, usd_per_quote
from .store.db import Store
from .strategy.signal import generate_signal
from .tg.bot import TelegramBroadcaster


log = logging.getLogger(__name__)


def _seconds_until_next_h1_close(now: datetime) -> float:
    nxt = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return max(5.0, (nxt - now).total_seconds())


class Scanner:
    def __init__(self, cfg: Config, store: Store, feed: CTraderClient,
                 bot: TelegramBroadcaster, chart: ChartImg) -> None:
        self.cfg = cfg
        self.store = store
        self.feed = feed
        self.bot = bot
        self.chart = chart
        self.pip_map: Mapping[str, float] = {p.instrument: p.pip for p in cfg.pairs}

    async def scan_pair(self, pair: str) -> None:
        if pair not in self.pip_map:
            log.debug("scan_pair: %s not in whitelist; skipping", pair)
            return
        if self.store.has_open_for_pair(pair):
            self.store.log_scan(now_utc(), pair, "H1", "skip_open")
            return
        if self.store.open_count() >= self.cfg.max_concurrent:
            self.store.log_scan(now_utc(), pair, "H1", "skip_max_concurrent")
            return

        result = generate_signal(self.feed, pair, min_rr=self.cfg.min_rr)
        if result is None:
            self.store.log_scan(now_utc(), pair, "H1", "no_setup")
            return
        sig, reason = result
        if sig is None:
            self.store.log_scan(now_utc(), pair, "H1", reason)
            return

        # Same-OB dedup: skip if (sweep, bos, ob_low, ob_high) matches the last
        # fire on this pair. Prevents the same Order Block re-firing every
        # H1 bar until the BOS staleness window expires.
        last_sig = self.store.get_last_ob_signature(pair)
        if last_sig is not None:
            current_sig = (sig.sweep_level, sig.bos_level, sig.ob_low, sig.ob_high)
            tolerance = 1e-5
            if all(abs(a - b) < tolerance for a, b in zip(last_sig, current_sig)):
                self.store.log_scan(now_utc(), pair, "H1", "dup_ob")
                log.info("dup_ob %s: signature unchanged from last fire; skip", pair)
                return

        # Missed-entry filter: abort if current market price has drifted past
        # the OB-midpoint entry by more than `missed_entry_threshold` x SL distance.
        # Prevents posting signals where price has already moved through the OB
        # and is likely heading straight to TP without a realistic re-entry.
        try:
            tick = self.feed.fetch_price(pair)
            ref_price = tick["mid"]
            sl_distance = abs(sig.entry - sig.stop_loss)
            if sig.direction == "long":
                drift = ref_price - sig.entry
            else:
                drift = sig.entry - ref_price
            if sl_distance > 0 and drift > self.cfg.missed_entry_threshold * sl_distance:
                self.store.log_scan(
                    now_utc(), pair, "H1", f"missed_entry:{drift:.5f}"
                )
                log.info(
                    "missed_entry %s: drift=%.5f exceeds %.1f x SL=%.5f; skip",
                    pair, drift, self.cfg.missed_entry_threshold, sl_distance,
                )
                return
        except Exception as e:
            log.warning("missed_entry check failed for %s: %s; continuing",
                        pair, e)

        # Daily kill-switch: skip new trades if today's R is already <= -cap.
        if self.cfg.enable_execution:
            now = now_utc()
            sod = datetime.combine(now.date(), time.min).replace(tzinfo=timezone.utc)
            daily_pnl_r = self.store.daily_pnl_r(sod)
            if daily_pnl_r <= -abs(self.cfg.daily_loss_r_cap):
                self.store.log_scan(now, pair, "H1", f"daily_kill:{daily_pnl_r:.1f}R")
                log.warning("daily kill-switch hit (%.1fR <= -%.1fR); skip %s",
                            daily_pnl_r, self.cfg.daily_loss_r_cap, pair)
                return

        trade_id = self.store.insert_trade(
            pair=sig.pair,
            direction=sig.direction,
            entry=sig.entry,
            stop_loss=sig.stop_loss,
            take_profit=sig.take_profit,
            rr=sig.rr,
            entry_time=sig.entry_time,
            thesis=sig.thesis,
            timeframe=sig.timeframe,
        )

        # Auto-execute on cTrader if enabled. Always falls through to chart
        # + Telegram afterwards so the user sees the signal regardless of
        # whether execution succeeded.
        if self.cfg.enable_execution:
            try:
                tick = self.feed.fetch_price(pair)
                balance = self.feed.fetch_balance_usd()
                rate = usd_per_quote(self.feed, pair, tick["mid"])
                sizing = compute_lots(
                    equity_usd=balance,
                    risk_pct=self.cfg.risk_pct,
                    entry=sig.entry,
                    stop_loss=sig.stop_loss,
                    pair=pair,
                    current_price=tick["mid"],
                    usd_per_quote_rate=rate,
                    max_lots=self.cfg.execution_max_lots,
                )
                if not sizing.ok:
                    log.info("sizing reject for %s: %s (signal-only)",
                             pair, sizing.reason)
                else:
                    pos_id = self.feed.place_market_order(
                        instrument=pair,
                        direction=sig.direction,
                        volume_units=sizing.volume_units,
                        sl_price=sig.stop_loss,
                        tp_price=sig.take_profit,
                        label=f"trade-{trade_id}",
                        comment="tsg",
                    )
                    self.store.update_lots_and_position(trade_id, sizing.lots, pos_id)
                    log.info("trade %s executed: %s %s lots=%.2f position=%s "
                             "balance=%.2f",
                             trade_id, pair, sig.direction, sizing.lots,
                             pos_id, balance)
            except Exception as e:
                log.error("execution failed for %s: %s (signal-only)", pair, e)

        try:
            png = self.chart.render(sig, status="OPEN", signal_id=trade_id)
        except Exception as e:
            log.error("chart-img render failed (%s): %s", pair, e)
            png = b""

        try:
            msg_map = await self.bot.send_signal(
                sig, png, pair_pip=self.pip_map[pair]
            )
            ts = now_utc()
            for ch, mid in msg_map.items():
                self.store.add_trade_message(trade_id, ch, mid, ts)
        except Exception as e:
            log.error("telegram send failed (%s): %s", pair, e)

        self.store.log_scan(now_utc(), pair, "H1", "fired")
        # Record OB signature so same setup won't re-fire on next bar.
        self.store.set_ob_signature(
            pair, sig.sweep_level, sig.bos_level, sig.ob_low, sig.ob_high,
            now_utc(),
        )

    async def scan_all(self) -> None:
        for pair_cfg in self.cfg.pairs:
            try:
                await self.scan_pair(pair_cfg.instrument)
            except Exception as e:
                log.exception("scan_pair %s error: %s", pair_cfg.instrument, e)

    async def run_forever(self) -> None:
        log.info("scanner started; %d pairs whitelisted", len(self.cfg.pairs))
        await self.scan_all()
        while True:
            sleep_s = _seconds_until_next_h1_close(now_utc())
            log.info("scanner sleeping %.0fs until next H1 close", sleep_s)
            await asyncio.sleep(sleep_s + 5)
            try:
                await self.scan_all()
            except Exception as e:
                log.exception("scan_all error: %s", e)
