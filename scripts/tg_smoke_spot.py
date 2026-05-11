"""Smoke test — post an SMC-shaped trade anchored at the *current* EUR/USD
spot price, just to see how the RR diagram lays out at live market levels.

The strategy gates (H4 bias / H1 SMC setup / 1:3 RR) are NOT being run —
this is a visual smoke for the chart + caption pipeline only.

Pipeline (same as production):
  - tsg.strategy.signal.Signal  + tsg.strategy.signal._format_thesis
  - tsg.chart.chartimg.ChartImg.render()      (locked v13 4-pane composite)
  - tsg.tg.bot.format_signal_caption()        (locked caption convention)
  - Telethon TEST session (.tsg-test.session, @statosphere)
  - TEST channel `PTJ - 1 H` (id -1003928938607)

Spot source: Yahoo Finance EURUSD=X 1-minute candle close (free, no auth,
~15min max delay). Sufficient for a visual smoke.

Trade construction (no real setup logic — pure RR geometry):
  direction   long
  entry       last 1m close from Yahoo, rounded to 5 decimals
  stop_loss   entry - 0.00300  (30 pips risk)
  take_profit entry + 0.00900  (90 pips reward -> RR 1:3)
  entry_time  now, aligned to the current H1 candle (minute=0)
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
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

PAIR = "EUR_USD"
DIRECTION = "long"
SL_PIPS = 30
TP_PIPS = 90
PIP = 0.0001


def fetch_eurusd_spot() -> float:
    """Return the latest non-null 1-minute close for EURUSD=X from
    Yahoo Finance. ~15 min delayed for retail-grade data; fine for
    visual smoke purposes.
    """
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X"
        "?interval=1m&range=1d"
    )
    headers = {"user-agent": "Mozilla/5.0 tsg-smoke"}
    with httpx.Client(timeout=15.0, headers=headers) as c:
        r = c.get(url)
        r.raise_for_status()
        data = r.json()
    closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
    # Walk back from the end skipping Nones (Yahoo pads the array with
    # nulls for minutes the market hasn't ticked yet).
    for v in reversed(closes):
        if v is not None:
            return float(v)
    raise RuntimeError("no valid spot found in Yahoo response")


def build_spot_signal(spot: float) -> Signal:
    """Construct a synthetic 1:3 RR long anchored at the current spot.
    Risk = 30 pips, reward = 90 pips. Numbers exist only to draw the
    RR diagram on a live chart; no actual SMC criteria are checked.
    """
    entry = round(spot, 5)
    stop_loss = round(entry - SL_PIPS * PIP, 5)
    take_profit = round(entry + TP_PIPS * PIP, 5)
    rr = round((take_profit - entry) / (entry - stop_loss), 2)  # 3.0

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    sweep_level = round(entry - 0.00050, 5)  # synthetic prior-low sweep
    bos_level = round(entry + 0.00040, 5)    # synthetic H1 BoS
    atr = 0.00060

    thesis = _format_thesis(DIRECTION, "bullish", sweep_level, bos_level, atr)

    return Signal(
        pair=PAIR,
        direction=DIRECTION,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        rr=rr,
        entry_time=now,
        thesis=thesis,
        timeframe="H1",
    )


async def main() -> int:
    if not TEST_SESSION_PATH.exists():
        print(f"ERROR: {TEST_SESSION_PATH} not found; run telegram_login_test.py first")
        return 1

    print("fetching EUR/USD spot from Yahoo...")
    spot = fetch_eurusd_spot()
    print(f"spot: {spot:.5f}")

    signal = build_spot_signal(spot)
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

    caption = format_signal_caption(signal, pair_pip=PIP)
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
    buf.name = f"{signal.pair}_{signal.direction}_spot_smoke.png"
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
