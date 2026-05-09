#!/usr/bin/env python3
"""List Telegram channels you can post to.

Prereqs:
    Run scripts/telegram_login.py once first (creates .tsg.session).

Run:
    python scripts/telegram_list_chats.py

Iterates your Telegram dialogs, filters channels/super-groups where you have
admin or post-message rights, and prints lines like:

    -1001234567890   "My Signals Channel"   admin: True

Copy the IDs (with the leading minus sign) into your .env:

    TG_CHANNEL_IDS=-1001234567890,-1009876543210
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
    session = os.environ.get("TG_SESSION_PATH", ".tsg.session").strip()

    if not api_id or not api_hash:
        print("ERROR: TG_API_ID / TG_API_HASH not set in .env.", file=sys.stderr)
        return 2

    client = TelegramClient(session, int(api_id), api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        print("ERROR: session not authorised. Run scripts/telegram_login.py first.",
              file=sys.stderr)
        await client.disconnect()
        return 1

    header = f"{'channel_id':>20}   {'name':<40}  admin?  broadcast?"
    print(header)
    print("-" * len(header))
    posters: list[str] = []

    async for dialog in client.iter_dialogs(limit=None):
        ent = dialog.entity
        is_broadcast = getattr(ent, "broadcast", False)
        is_megagroup = getattr(ent, "megagroup", False)
        is_channel = is_broadcast or is_megagroup
        if not is_channel:
            continue

        admin_rights = getattr(ent, "admin_rights", None)
        creator = getattr(ent, "creator", False)
        is_admin = bool(creator or admin_rights)

        # Telegram Bot/User API peer-ID convention: both broadcast channels
        # and megagroups use the -100<peer_id> form.
        formatted_id = f"-100{ent.id}"

        # Post-permission rules:
        #   broadcast channel: creator OR admin_rights.post_messages
        #   megagroup:         any member may post unless restricted;
        #                      admins/creator always can
        if is_broadcast:
            can_post = bool(
                creator or (admin_rights and getattr(admin_rights, "post_messages", False))
            )
        else:
            can_post = True
        name = (dialog.title or "").strip()[:38]
        print(f"{formatted_id:>20}   {name:<40}  {str(is_admin):<6}  {str(is_broadcast):<6}")
        if can_post:
            posters.append(formatted_id)

    print()
    if posters:
        print("Suggested TG_CHANNEL_IDS line for .env:")
        print(f"  TG_CHANNEL_IDS={','.join(posters)}")
    else:
        print("No channels with post permission found for this account.")

    await client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
