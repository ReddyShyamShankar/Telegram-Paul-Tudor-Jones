"""One-shot smoke test: render EUR/USD 15m chart with a Long Position
RR-box drawing using the user's TV-layout colors (mint-green profit zone,
neutral light-gray stop zone, light theme — matches the TV layout
`gm7qCQc5`). Posts to the first configured Telegram channel."""
from __future__ import annotations

import asyncio
import io
import os
from datetime import datetime, timedelta, timezone
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

# Synthetic Long Position around current EUR/USD spot (~1.17897 last close).
# Risk = 30 pips; reward = 90 pips → 1:3 RR.
ENTRY = 1.17900
STOP_LOSS = 1.17600
TAKE_PROFIT = 1.18800

# Colors sampled from TV layout `gm7qCQc5`:
#  - profit zone displayed pale mint ≈ #BFF5CF on white → source rgb(34,197,94) @ ~70% transparency
#  - stop zone displayed near-neutral light gray ≈ #E8E8E8 → source rgb(158,158,158) @ ~80% transparency
PROFIT_COLOR = "rgba(34,197,94,1)"
PROFIT_TRANSPARENCY = 70
STOP_COLOR = "rgba(158,158,158,1)"
STOP_TRANSPARENCY = 80
LINE_COLOR = "rgba(82,136,240,1)"


def fetch_chart_png() -> bytes:
    start_dt = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
    payload = {
        "symbol": "OANDA:EURUSD",
        "interval": "15m",
        "theme": "light",
        "width": 1280,
        "height": 720,
        "studies": [{"name": "Volume"}],
        "range": "1D",
        "drawings": [
            {
                "name": "Long Position",
                "input": {
                    "startDatetime": start_dt,
                    "entryPrice": ENTRY,
                    "stopPrice": STOP_LOSS,
                    "targetPrice": TAKE_PROFIT,
                },
                "override": {
                    "linewidth": 1,
                    "linecolor": LINE_COLOR,
                    "profitBackground": PROFIT_COLOR,
                    "profitBackgroundTransparency": PROFIT_TRANSPARENCY,
                    "stopBackground": STOP_COLOR,
                    "stopBackgroundTransparency": STOP_TRANSPARENCY,
                },
            }
        ],
    }
    headers = {"x-api-key": CHART_IMG_KEY, "content-type": "application/json"}
    with httpx.Client(timeout=20.0) as c:
        r = c.post(CHART_IMG_URL, json=payload, headers=headers)
        if r.status_code != 200:
            print(f"chart-img status={r.status_code}  body={r.text[:500]}")
            r.raise_for_status()
        return r.content


async def main() -> int:
    print("rendering EURUSD 15m with custom RR colors …")
    png = fetch_chart_png()
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
    buf.name = "EURUSD_15m_RR.png"
    caption = (
        f"EUR/USD 15m  ·  long demo\n"
        f"entry {ENTRY:.5f}  ·  SL {STOP_LOSS:.5f}  ·  TP {TAKE_PROFIT:.5f}  ·  RR 1:3"
    )
    msg = await client.send_file(
        entity, file=buf, caption=caption, force_document=False
    )
    print(f"sent message_id={msg.id}")
    await client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
