"""One-shot smoke test: send 'hi' to the first configured Telegram channel
and quote-reply 'hi' to that same message. Uses the parent-dir .env +
.tsg.session (where the production credentials live)."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

# Production .env + session live one level above the worktree.
PARENT = Path("/Users/reddyshyamshankar/Documents/Code/Trade Signal Generator")
load_dotenv(PARENT / ".env")

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION_PATH = PARENT / os.environ.get("TG_SESSION_PATH", ".tsg.session")
RAW_CHANNEL_IDS = os.environ["TG_CHANNEL_IDS"]
CHANNEL_ID = int([t.strip() for t in RAW_CHANNEL_IDS.split(",") if t.strip()][0])


async def main() -> int:
    # Telethon expects the session basename without the `.session` suffix.
    session_str = str(SESSION_PATH)
    if session_str.endswith(".session"):
        session_str = session_str[:-len(".session")]
    client = TelegramClient(session_str, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("ERROR: session not authorized; run scripts/telegram_login.py first")
        return 1

    me = await client.get_me()
    print(f"connected as @{me.username or me.id}")

    # Force a dialog list refresh so Telethon caches the access_hash for any
    # channels created after the session file was last written.
    await client.get_dialogs(limit=200)

    entity = await client.get_entity(CHANNEL_ID)
    print(f"target channel: {getattr(entity, 'title', CHANNEL_ID)}  id={CHANNEL_ID}")

    msg1 = await client.send_message(entity, "hi")
    print(f"sent #1 message_id={msg1.id}")

    msg2 = await client.send_message(entity, "hi", reply_to=msg1.id)
    print(f"sent #2 (reply to {msg1.id}) message_id={msg2.id}")

    await client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
