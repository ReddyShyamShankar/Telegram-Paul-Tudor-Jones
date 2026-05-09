#!/usr/bin/env python3
"""One-time Telegram User-API login.

Prereqs:
    1. Fill TG_API_ID, TG_API_HASH, TG_PHONE in .env.
       Get api_id + api_hash from https://my.telegram.org/apps.

Run:
    python scripts/telegram_login.py

The script connects to Telegram, sends an SMS to your phone, prompts for the
code (and 2FA password if you have one), and saves the session at the path
in TG_SESSION_PATH (default `.tsg.session`). Run once. Future bot runs reuse
the session silently.
"""
from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv
from telethon import TelegramClient


async def main() -> int:
    load_dotenv()
    api_id = os.environ.get("TG_API_ID", "").strip()
    api_hash = os.environ.get("TG_API_HASH", "").strip()
    phone = os.environ.get("TG_PHONE", "").strip()
    session = os.environ.get("TG_SESSION_PATH", ".tsg.session").strip()

    if not api_id or not api_hash or not phone:
        print("ERROR: set TG_API_ID, TG_API_HASH, TG_PHONE in .env first.",
              file=sys.stderr)
        return 2
    try:
        api_id_int = int(api_id)
    except ValueError:
        print(f"ERROR: TG_API_ID must be numeric (got {api_id!r}).",
              file=sys.stderr)
        return 2

    print(f"Logging in as {phone} ; session file = {session}")
    client = TelegramClient(session, api_id_int, api_hash)
    await client.start(phone=phone)
    me = await client.get_me()
    print(
        f"\nLogged in as: {me.first_name}"
        + (f" (@{me.username})" if me.username else "")
        + f"  id={me.id}"
    )
    print("Session saved. You can now run:")
    print("  python scripts/telegram_list_chats.py")
    await client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
