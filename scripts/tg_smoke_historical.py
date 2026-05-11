"""Smoke test — post a plausible historical SMC trade to the TEST channel.

Uses the production pipeline end-to-end:
  - tsg.strategy.signal.Signal  + tsg.strategy.signal._format_thesis
  - tsg.chart.chartimg.ChartImg.render()      (locked v13 4-pane composite)
  - tsg.tg.bot.format_signal_caption()        (locked caption convention)
  - Telethon TEST session (.tsg-test.session, @statosphere)
  - TEST channel `PTJ - 1 H` (id -1003928938607)

The production session (.tsg.session) and channel are NOT touched.

Synthesised trade:
  pair       EUR_USD
  direction  short
  entry      1.17500
  stop_loss  1.17800   (30 pips risk)
  take_profit 1.16600  (90 pips reward -> RR 1:3)
  entry_time 7 days ago at H1 close (UTC)
  thesis     SMC liquidity sweep at 1.17850 + BoS below 1.17400, 0.5 ATR buffer.
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

PARENT = Path("/Users/reddyshyamshankar/Documents/Code/Trade Signal Generator")
WORKTREE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKTREE / "src"))

load_dotenv(PARENT / ".env")

from tsg.strategy.signal import Signal, _format_thesis  # noqa: E402
from tsg.chart.chartimg import ChartImg  # noqa: E402
from tsg.tg.bot import format_signal_caption  # noqa: E402

# Telegram (TEST session + channel)
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
TEST_SESSION_PATH = PARENT / ".tsg-test.session"
TEST_CHANNEL_ID = -1003928938607  # PTJ - 1 H, owned by @statosphere

# chart-img + TV cookies
CHART_IMG_KEY = os.environ["CHART_IMG_API_KEY"]
TV_SESSION_ID = os.environ.get("TV_SESSION_ID")
TV_SESSION_ID_SIGN = os.environ.get("TV_SESSION_ID_SIGN")


def build_historical_signal() -> Signal:
    """Plausible EUR_USD short, anchored 7 days ago at the most recent H1
    close. Numbers chosen to give exactly RR 1:3 and stay close to the
    current EUR/USD range so the chart panes still show the levels.
    """
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    entry_time = now - timedelta(days=7)

    pair = "EUR_USD"
    direction = "short"
    entry = 1.17500
    stop_loss = 1.17800
    take_profit = 1.16600
    rr = round((entry - take_profit) / (stop_loss - entry), 2)  # 3.0

    sweep_level = 1.17850   # liquidity grab above the prior swing high
    bos_level = 1.17400     # H1 break of structure
    atr = 0.00060           # ~6 pips of ATR buffer

    thesis = _format_thesis(direction, "bearish", sweep_level, bos_level, atr)

    return Signal(
        pair=pair,
        direction=direction,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        rr=rr,
        entry_time=entry_time,
        thesis=thesis,
        timeframe="H1",
    )


async def main() -> int:
    if not TEST_SESSION_PATH.exists():
        print(f"ERROR: {TEST_SESSION_PATH} not found; run telegram_login_test.py first")
        return 1

    signal = build_historical_signal()
    print(
        f"signal built: {signal.pair} {signal.direction} entry={signal.entry} "
        f"SL={signal.stop_loss} TP={signal.take_profit} RR={signal.rr} "
        f"entry_time={signal.entry_time.isoformat()}"
    )

    print("rendering 4-pane chart via chart-img v2 advanced-chart x4 + Pillow stitch...")
    chart = ChartImg(
        api_key=CHART_IMG_KEY,
        cache_dir=PARENT / "data" / "charts",
        tv_session_id=TV_SESSION_ID,
        tv_session_id_sign=TV_SESSION_ID_SIGN,
    )
    png = chart.render(signal, status="OPEN", signal_id=None)
    print(f"chart rendered: {len(png)} bytes")

    caption = format_signal_caption(signal, pair_pip=0.0001)
    print("\n--- CAPTION ---")
    print(caption)
    print("--- END CAPTION ---\n")

    s = str(TEST_SESSION_PATH)
    if s.endswith(".session"):
        s = s[:-len(".session")]
    client = TelegramClient(s, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("ERROR: test session not authorized")
        await client.disconnect()
        return 1

    me = await client.get_me()
    print(f"connected as @{me.username or me.id}")

    await client.get_dialogs(limit=200)
    entity = await client.get_entity(TEST_CHANNEL_ID)
    print(f"target channel: {getattr(entity, 'title', TEST_CHANNEL_ID)} id={TEST_CHANNEL_ID}")

    buf = io.BytesIO(png)
    buf.name = f"{signal.pair}_{signal.direction}_smoke.png"
    msg = await client.send_file(
        entity,
        file=buf,
        caption=caption,
        force_document=False,
    )
    print(f"\nPOSTED message_id={msg.id} chars={len(caption)} png_bytes={len(png)}")

    await client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
