"""Combined smoke test using the +91 TEST session (.tsg-test.session) ->
target channel `PTJ - 1 H` (id -1003928938607). Runs all three artifacts
in sequence: hi+reply, EUR/USD 15m RR chart with TV-layout colors, and
exact-replica TV-layout snapshot. Production session (.tsg.session) is
NOT touched.
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from telethon import TelegramClient

PARENT = Path("/Users/reddyshyamshankar/Documents/Code/Trade Signal Generator")
WORKTREE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKTREE / "src"))

load_dotenv(PARENT / ".env")

from tsg.chart.chartimg import ChartImg  # noqa: E402

# Telegram (TEST session)
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
TEST_SESSION_PATH = PARENT / ".tsg-test.session"
TEST_CHANNEL_ID = -1003928938607  # PTJ - 1 H, owned by @statosphere

# chart-img
CHART_IMG_KEY = os.environ["CHART_IMG_API_KEY"]
CHART_IMG_URL = "https://api.chart-img.com/v2/tradingview/advanced-chart"

# Synthetic Long Position around current EUR/USD spot.
ENTRY = 1.17900
STOP_LOSS = 1.17600
TAKE_PROFIT = 1.18800

LAYOUT_ID = "gm7qCQc5"


def fetch_rr_chart_png() -> bytes:
    start_dt = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
    payload = {
        "symbol": "OANDA:EURUSD",
        "interval": "15m",
        "theme": "light",
        "width": 1280,
        "height": 720,
        "studies": [{"name": "Volume"}],
        "range": "1D",
        "drawings": [{
            "name": "Long Position",
            "input": {
                "startDatetime": start_dt,
                "entryPrice": ENTRY,
                "stopPrice": STOP_LOSS,
                "targetPrice": TAKE_PROFIT,
            },
            "override": {
                "lineWidth": 1,
                "lineColor": "rgba(82,136,240,1)",
                "profitZoneColor": "rgba(34,197,94,1)",
                "profitZoneTransparency": 70,
                "stopZoneColor": "rgba(158,158,158,1)",
                "stopZoneTransparency": 80,
                "showLabel": True,
                "showStats": True,
            },
        }],
    }
    headers = {"x-api-key": CHART_IMG_KEY, "content-type": "application/json"}
    with httpx.Client(timeout=30.0) as c:
        r = c.post(CHART_IMG_URL, json=payload, headers=headers)
        r.raise_for_status()
        return r.content


async def main() -> int:
    if not TEST_SESSION_PATH.exists():
        print(f"ERROR: {TEST_SESSION_PATH} not found; run telegram_login_test.py first")
        return 1
    s = str(TEST_SESSION_PATH)
    if s.endswith(".session"):
        s = s[:-len(".session")]
    client = TelegramClient(s, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("ERROR: test session not authorized")
        return 1

    me = await client.get_me()
    print(f"connected as @{me.username or me.id}")

    await client.get_dialogs(limit=200)
    entity = await client.get_entity(TEST_CHANNEL_ID)
    print(f"target channel: {getattr(entity, 'title', TEST_CHANNEL_ID)}  id={TEST_CHANNEL_ID}")

    # 1) hi + threaded reply
    msg1 = await client.send_message(entity, "hi")
    print(f"[1/3] sent #1 message_id={msg1.id}")
    msg2 = await client.send_message(entity, "hi", reply_to=msg1.id)
    print(f"[1/3] sent #2 (reply to {msg1.id}) message_id={msg2.id}")

    # 2) EUR/USD 15m RR chart
    print("[2/3] fetching RR chart …")
    png_rr = fetch_rr_chart_png()
    buf = io.BytesIO(png_rr)
    buf.name = "EURUSD_15m_RR.png"
    msg3 = await client.send_file(
        entity, file=buf,
        caption=(
            f"EUR/USD 15m  ·  long demo\n"
            f"entry {ENTRY:.5f}  ·  SL {STOP_LOSS:.5f}  ·  TP {TAKE_PROFIT:.5f}  ·  RR 1:3"
        ),
        force_document=False,
    )
    print(f"[2/3] sent message_id={msg3.id}  ({len(png_rr)} bytes)")

    # 3) TV layout exact replica — NO symbol/interval overrides so the saved
    # 4-pane multi-timeframe arrangement (1D / 4H / 1H / 15m, with RR boxes)
    # renders as-is. Overrides in layout-chart apply globally and collapse
    # the multi-pane structure.
    print(f"[3/3] rendering TV layout {LAYOUT_ID} via layout-chart (no overrides) …")
    chart = ChartImg(api_key=CHART_IMG_KEY, cache_dir=Path("/tmp"))
    png_layout = chart.render_layout(LAYOUT_ID, width=1600, height=900)
    buf2 = io.BytesIO(png_layout)
    buf2.name = f"layout_{LAYOUT_ID}.png"
    msg4 = await client.send_file(
        entity, file=buf2,
        caption=f"TV layout `{LAYOUT_ID}`  ·  4-pane: 1D / 4H / 1H / 15m  ·  RR boxes preserved",
        force_document=False,
    )
    print(f"[3/3] sent message_id={msg4.id}  ({len(png_layout)} bytes)")

    await client.disconnect()
    print("\nALL TESTS POSTED to PTJ - 1 H from @statosphere")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
