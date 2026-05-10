"""One-shot smoke test: render the user's saved TradingView layout
`gm7qCQc5` pixel-exact via chart-img v2 `layout-chart` endpoint and post
the PNG to the first configured Telegram channel.

The TradingView layout MUST be shared (not private). Otherwise set
`TV_SESSION_ID` and `TV_SESSION_ID_SIGN` in `.env`.
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

PARENT = Path("/Users/reddyshyamshankar/Documents/Code/Trade Signal Generator")
WORKTREE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKTREE / "src"))

load_dotenv(PARENT / ".env")

from tsg.chart.chartimg import ChartImg  # noqa: E402

# Telegram
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION_PATH = PARENT / os.environ.get("TG_SESSION_PATH", ".tsg.session")
CHANNEL_ID = int(
    [t.strip() for t in os.environ["TG_CHANNEL_IDS"].split(",") if t.strip()][0]
)

# chart-img
CHART_IMG_KEY = os.environ["CHART_IMG_API_KEY"]
TV_SESSION_ID = os.environ.get("TV_SESSION_ID") or None
TV_SESSION_ID_SIGN = os.environ.get("TV_SESSION_ID_SIGN") or None

LAYOUT_ID = "gm7qCQc5"
SYMBOL = "OANDA:EURUSD"
INTERVAL = "15m"


async def main() -> int:
    print(f"rendering TV layout {LAYOUT_ID} via chart-img layout-chart …")
    chart = ChartImg(api_key=CHART_IMG_KEY, cache_dir=Path("/tmp"))
    png = chart.render_layout(
        LAYOUT_ID,
        symbol=SYMBOL,
        interval=INTERVAL,
        tv_session_id=TV_SESSION_ID,
        tv_session_id_sign=TV_SESSION_ID_SIGN,
    )
    print(f"got {len(png)} bytes")

    session_str = str(SESSION_PATH)
    if session_str.endswith(".session"):
        session_str = session_str[:-len(".session")]
    client = TelegramClient(session_str, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("ERROR: session not authorized")
        return 1

    await client.get_dialogs(limit=200)
    entity = await client.get_entity(CHANNEL_ID)
    print(f"target channel: {getattr(entity, 'title', CHANNEL_ID)}  id={CHANNEL_ID}")

    buf = io.BytesIO(png)
    buf.name = f"layout_{LAYOUT_ID}.png"
    caption = (
        f"TV layout `{LAYOUT_ID}` snapshot\n"
        f"override: symbol={SYMBOL}  interval={INTERVAL}"
    )
    msg = await client.send_file(
        entity, file=buf, caption=caption, force_document=False
    )
    print(f"sent message_id={msg.id}")
    await client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
