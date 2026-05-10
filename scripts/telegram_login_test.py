"""Two-phase Telegram User-API login for the SECOND (test) account.

Phase 1 (no args):  send SMS code to TEST_PHONE, persist phone_code_hash.
Phase 2 (--code <X>): sign in with the code, save session to .tsg-test.session.

Reads `.env` for TG_API_ID / TG_API_HASH. TEST_PHONE is hard-coded (the +91
test account); change here if the test number changes. Production session
(.tsg.session) is untouched.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
)


PARENT = Path("/Users/reddyshyamshankar/Documents/Code/Trade Signal Generator")
load_dotenv(PARENT / ".env")

TEST_PHONE = "+919966522084"
SESSION_PATH = PARENT / ".tsg-test.session"
HASH_PATH = Path("/tmp/tsg_test_phone_code_hash.json")


async def phase1_send_code() -> int:
    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    s = str(SESSION_PATH)
    if s.endswith(".session"):
        s = s[:-len(".session")]
    client = TelegramClient(s, api_id, api_hash)
    await client.connect()
    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"already authorized as {me.first_name} (@{me.username}) id={me.id}")
        await client.disconnect()
        return 0
    sent = await client.send_code_request(TEST_PHONE)
    HASH_PATH.write_text(json.dumps({
        "phone": TEST_PHONE,
        "phone_code_hash": sent.phone_code_hash,
    }))
    print(f"SMS code sent to {TEST_PHONE}")
    print(f"saved phone_code_hash to {HASH_PATH}")
    print(f"now run: python scripts/telegram_login_test.py --code <CODE>")
    await client.disconnect()
    return 0


async def phase2_sign_in(code: str, password: str | None) -> int:
    if not HASH_PATH.exists():
        print(f"ERROR: {HASH_PATH} not found; run phase 1 first", file=sys.stderr)
        return 2
    state = json.loads(HASH_PATH.read_text())
    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    s = str(SESSION_PATH)
    if s.endswith(".session"):
        s = s[:-len(".session")]
    client = TelegramClient(s, api_id, api_hash)
    await client.connect()
    try:
        await client.sign_in(
            phone=state["phone"],
            code=code,
            phone_code_hash=state["phone_code_hash"],
        )
    except SessionPasswordNeededError:
        if not password:
            import getpass
            print("Telegram 2FA enabled. Enter cloud password (input hidden):")
            password = getpass.getpass(prompt="> ")
        await client.sign_in(password=password)
    except PhoneCodeInvalidError:
        print("ERROR: code invalid", file=sys.stderr)
        await client.disconnect()
        return 4
    except PhoneCodeExpiredError:
        print("ERROR: code expired; re-run phase 1", file=sys.stderr)
        await client.disconnect()
        return 5
    me = await client.get_me()
    print(
        f"logged in as {me.first_name}"
        + (f" (@{me.username})" if me.username else "")
        + f" id={me.id}"
    )
    print(f"session saved to {SESSION_PATH}")
    HASH_PATH.unlink(missing_ok=True)
    await client.disconnect()
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--code", help="SMS code received on test phone")
    p.add_argument("--password", help="optional 2FA password if account uses one")
    args = p.parse_args()
    if args.code:
        return asyncio.run(phase2_sign_in(args.code, args.password))
    return asyncio.run(phase1_send_code())


if __name__ == "__main__":
    raise SystemExit(main())
