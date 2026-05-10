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

from datetime import datetime

from ..store.db import TradeMessage, TradeRow
from ..strategy.signal import Signal
from .captions import entry_closer, tp_closer, sl_closer


log = logging.getLogger(__name__)


def _pip_distance(pair_pip: float, a: float, b: float) -> int:
    return int(round(abs(a - b) / pair_pip))


def _format_rr(rr: float) -> str:
    """Render RR as `1:N` with integer N when whole, else `1:N.x`."""
    if abs(rr - round(rr)) < 1e-6:
        return f"1:{int(round(rr))}"
    return f"1:{rr:.1f}"


def _parse_iso(ts) -> datetime:
    return ts if isinstance(ts, datetime) else datetime.fromisoformat(ts)


def _fmt_price(price: float, pair_pip: float) -> str:
    """JPY pairs (pip=0.01) → 2 decimals (e.g. 155.90).
    Non-JPY pairs (pip=0.0001) → 5 decimals (e.g. 1.17500)."""
    return f"{price:.2f}" if pair_pip >= 0.01 else f"{price:.5f}"


def format_signal_caption(signal: Signal, pair_pip: float = 0.0001) -> str:
    """Entry post caption.
    Bold direction header, levels at pair-aware precision (2 decimals
    for JPY pairs, 5 for everything else), short SMC thesis, then a
    direct-voice psychology line rotated per-trade. No emojis, no
    em-dashes, no parenthetical glosses.
    """
    head_dir = "**LONG**" if signal.direction == "long" else "**SHORT**"
    pair = signal.pair.replace("_", "/")
    rr = _format_rr(signal.rr)
    closer = entry_closer(signal.entry_time)
    return (
        f"{head_dir} {pair} · {signal.timeframe}\n"
        f"Entry: {_fmt_price(signal.entry, pair_pip)}\n"
        f"Stop Loss: {_fmt_price(signal.stop_loss, pair_pip)}\n"
        f"Take Profit: {_fmt_price(signal.take_profit, pair_pip)}\n"
        f"RR: {rr}\n\n"
        f"{signal.thesis}\n\n"
        f"{closer}"
    )


def format_outcome_caption(trade: TradeRow, outcome: str, note: str,
                           pair_pip: float = 0.0001) -> str:
    """Exit post caption (quote-reply to entry).
    No emojis, no em-dashes, direct voice.
    """
    pair = trade.pair.replace("_", "/")
    et = _parse_iso(trade.entry_time)

    if outcome == "TP":
        pips = _pip_distance(pair_pip, trade.entry, trade.take_profit)
        rr = _format_rr(trade.rr)
        head = f"**TP HIT** {pair} · +{pips} pips · {rr}"
        closer = tp_closer(et)
    elif outcome == "SL":
        pips = _pip_distance(pair_pip, trade.entry, trade.stop_loss)
        head = f"**SL HIT** {pair} · -{pips} pips · 1:1"
        closer = sl_closer(et)
    else:
        head = f"**SCRATCHED** {pair} · 0R"
        closer = sl_closer(et)

    body = note.strip() if note and note.strip() else ""
    parts = [head]
    if body:
        parts.append(body)
    parts.append(closer)
    return "\n\n".join(parts)


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
