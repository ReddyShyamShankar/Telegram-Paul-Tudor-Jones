"""Telegram broadcaster — Telethon User API.

Logs in once as the user (phone + SMS code, via scripts/telegram_login.py),
then posts to every channel ID configured in TG_CHANNEL_IDS.

Lifecycle (mirrors what scanner / tracker / main expect):
    await bot.start()
    await bot.send_signal(signal, png)            -> {channel_id: message_id}
    await bot.reply_outcome(messages, trade, outcome, png, note)
    await bot.stop()

`messages` is a list of `TradeMessage` rows (one per channel) so the tracker
can quote-reply on each original message individually.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Iterable

from telethon import TelegramClient

from ..store.db import TradeMessage, TradeRow
from ..strategy.signal import Signal


log = logging.getLogger(__name__)


def _pip_distance(pair_pip: float, a: float, b: float) -> int:
    return int(round(abs(a - b) / pair_pip))


def format_signal_caption(signal: Signal, pair_pip: float = 0.0001) -> str:
    arrow = "🟢 LONG" if signal.direction == "long" else "🔴 SHORT"
    sl_pips = _pip_distance(pair_pip, signal.entry, signal.stop_loss)
    tp_pips = _pip_distance(pair_pip, signal.entry, signal.take_profit)
    return (
        f"{arrow}  {signal.pair.replace('_','/')}  {signal.timeframe}\n"
        f"Entry:  {signal.entry:.5f}\n"
        f"SL:     {signal.stop_loss:.5f}   ({sl_pips} pips)\n"
        f"TP:     {signal.take_profit:.5f}   ({tp_pips} pips)\n"
        f"R:R:    1:{signal.rr:.1f}\n\n"
        f"Thesis: {signal.thesis}"
    )


def format_outcome_caption(trade: TradeRow, outcome: str, note: str,
                           pair_pip: float = 0.0001) -> str:
    if outcome == "TP":
        pips = _pip_distance(pair_pip, trade.entry, trade.take_profit)
        head = f"✅ TP HIT  {trade.pair.replace('_','/')}  +{pips} pips  ({trade.rr:.1f}R)"
    elif outcome == "SL":
        pips = _pip_distance(pair_pip, trade.entry, trade.stop_loss)
        head = f"❌ SL HIT  {trade.pair.replace('_','/')}  -{pips} pips  (-1.0R)"
    else:
        head = f"🟡 SCRATCHED  {trade.pair.replace('_','/')}  0R"
    return f"{head}\nNote: {note}"


class TelegramBroadcaster:
    def __init__(self, api_id: int, api_hash: str, phone: str,
                 session_path: Path, channel_ids: Iterable[int]) -> None:
        self.api_id = int(api_id)
        self.api_hash = api_hash
        self.phone = phone
        self.session_path = str(session_path)
        self.channel_ids: tuple[int, ...] = tuple(channel_ids)
        self._client: TelegramClient | None = None

    async def start(self) -> None:
        """Connect using the existing .session file. Does NOT prompt for SMS;
        the user must have run scripts/telegram_login.py at least once.
        Fails fast if not authorised.
        """
        self._client = TelegramClient(
            self.session_path, self.api_id, self.api_hash,
        )
        await self._client.connect()
        if not await self._client.is_user_authorized():
            await self._client.disconnect()
            raise RuntimeError(
                "Telegram session not authorised. "
                "Run: python scripts/telegram_login.py"
            )
        me = await self._client.get_me()
        log.info(
            "Telegram authorised as %s (id=%s); broadcasting to %d channels",
            getattr(me, "username", None) or me.first_name,
            me.id, len(self.channel_ids),
        )

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None

    async def send_signal(self, signal: Signal, png: bytes,
                          pair_pip: float = 0.0001) -> dict[int, int]:
        if self._client is None:
            raise RuntimeError("TelegramBroadcaster.start() not called")
        caption = format_signal_caption(signal, pair_pip=pair_pip)
        out: dict[int, int] = {}
        for ch in self.channel_ids:
            try:
                msg = await self._client.send_file(
                    ch,
                    file=io.BytesIO(png) if png else None,
                    caption=caption,
                    force_document=False,
                )
                out[ch] = msg.id
            except Exception as e:
                log.error("telegram send failed for channel %s: %s", ch, e)
        return out

    async def reply_outcome(self, messages: list[TradeMessage],
                            trade: TradeRow, outcome: str,
                            png: bytes, note: str,
                            pair_pip: float = 0.0001) -> None:
        if self._client is None:
            raise RuntimeError("TelegramBroadcaster.start() not called")
        caption = format_outcome_caption(trade, outcome, note, pair_pip=pair_pip)
        for tm in messages:
            try:
                ch = int(tm.channel_id)
                await self._client.send_file(
                    ch,
                    file=io.BytesIO(png) if png else None,
                    caption=caption,
                    reply_to=tm.message_id,
                    force_document=False,
                )
            except Exception as e:
                log.error("telegram reply failed for channel %s msg %s: %s",
                          tm.channel_id, tm.message_id, e)
