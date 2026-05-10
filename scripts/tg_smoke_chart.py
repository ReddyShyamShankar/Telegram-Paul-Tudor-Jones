"""One-shot smoke test: fetch EUR/USD 15m chart from chart-img v2 and post
it (no drawings, no overlay) to the first configured Telegram channel."""
from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from telethon import TelegramClient

PARENT = Path("/Users/reddyshyamshankar/Documents/Code/Trade Signal Generator")
load_dotenv(PARENT / ".env")

# Telegram
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION_PATH = PARENT / os.environ.get("TG_SESSION_PATH", ".tsg.session")
CHANNEL_ID = int(
    [t.strip() for t in os.environ["TG_CHANNEL_IDS"].split(",") if t.strip()][0]
)

# chart-img
CHART_IMG_KEY = os.environ["CHART_IMG_API_KEY"]
CHART_IMG_URL = "https://api.chart-img.com/v2/tradingview/advanced-chart"


def fetch_eurusd_15m_png() -> bytes:
    payload = {
        "symbol": "OANDA:EURUSD",
        "interval": "15m",
        "theme": "dark",
        "width": 1280,
        "height": 720,
        "studies": [{"name": "Volume"}],
        "range": "1D",
    }
    headers = {"x-api-key": CHART_IMG_KEY, "content-type": "application/json"}
    with httpx.Client(timeout=20.0) as c:
        r = c.post(CHART_IMG_URL, json=payload, headers=headers)
        r.raise_for_status()
        return r.content


async def main() -> int:
    print("fetching EURUSD 15m chart from chart-img …")
    png = fetch_eurusd_15m_png()
    print(f"got {len(png)} bytes")

    session_str = str(SESSION_PATH)
    if session_str.endswith(".session"):
        session_str = session_str[:-len(".session")]
    client = TelegramClient(session_str, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("ERROR: session not authorized")
        return 1

    entity = await client.get_entity(CHANNEL_ID)
    print(f"target channel: {getattr(entity, 'title', CHANNEL_ID)}  id={CHANNEL_ID}")

    buf = io.BytesIO(png)
    buf.name = "EURUSD_15m.png"
    msg = await client.send_file(
        entity,
        file=buf,
        caption="EUR/USD 15m — smoke test",
        force_document=False,
    )
    print(f"sent message_id={msg.id}")
    await client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
