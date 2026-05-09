#!/usr/bin/env python3
"""List cTrader trading accounts visible to your OAuth grant.

Why this exists: cTrader has changed its REST account-listing URL several
times and currently returns 404 on the documented one. The protobuf
ProtoOAGetAccountListByAccessTokenReq is the canonical, stable path.

Prereqs:
    .env contains CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET, CTRADER_REFRESH_TOKEN.
    (Run scripts/ctrader_oauth.py first.)

Run:
    python scripts/ctrader_list_accounts.py

Prints lines like:

    ctidTraderAccountId=12345678   isLive=False

Pick the demo account you want, then paste these into .env:

    CTRADER_ACCOUNT_ID=<ctidTraderAccountId from above>
    CTRADER_ENVIRONMENT=demo            # or 'live'
"""
from __future__ import annotations

import os
import sys
import threading

import requests
from dotenv import load_dotenv


TOKEN_URL = "https://openapi.ctrader.com/apps/token"
DEMO_HOST = "demo.ctraderapi.com"
LIVE_HOST = "live.ctraderapi.com"
PORT = 5035


def _refresh_access(refresh: str, cid: str, csec: str) -> str:
    r = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": cid,
            "client_secret": csec,
        },
        timeout=20,
    )
    r.raise_for_status()
    body = r.json()
    access = body.get("accessToken") or body.get("access_token")
    if not access:
        raise RuntimeError(f"unexpected refresh response: {body}")
    return access


def main() -> int:
    load_dotenv()
    cid = os.environ.get("CTRADER_CLIENT_ID", "").strip()
    csec = os.environ.get("CTRADER_CLIENT_SECRET", "").strip()
    refresh = os.environ.get("CTRADER_REFRESH_TOKEN", "").strip()
    if not cid or not csec or not refresh:
        print("ERROR: set CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET, "
              "CTRADER_REFRESH_TOKEN in .env first "
              "(run scripts/ctrader_oauth.py).", file=sys.stderr)
        return 2

    print("Exchanging refresh token for access token ...")
    access = _refresh_access(refresh, cid, csec)
    print(f"  access_token: {access[:12]}...{access[-6:]}")

    from ctrader_open_api import Client, Protobuf, TcpProtocol  # type: ignore
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (  # type: ignore
        ProtoOAApplicationAuthReq,
        ProtoOAApplicationAuthRes,
        ProtoOAGetAccountListByAccessTokenReq,
        ProtoOAGetAccountListByAccessTokenRes,
    )
    from twisted.internet import reactor

    result_holder: dict = {"accounts": None, "error": None}
    done = threading.Event()

    client = Client(DEMO_HOST, PORT, TcpProtocol)

    def on_message(_client, msg):
        try:
            payload = Protobuf.extract(msg)
        except Exception as e:
            result_holder["error"] = e
            done.set()
            return
        if isinstance(payload, ProtoOAApplicationAuthRes):
            req = ProtoOAGetAccountListByAccessTokenReq()
            req.accessToken = access
            client.send(req)
        elif isinstance(payload, ProtoOAGetAccountListByAccessTokenRes):
            result_holder["accounts"] = list(payload.ctidTraderAccount)
            done.set()

    def on_connected(_client):
        req = ProtoOAApplicationAuthReq()
        req.clientId = cid
        req.clientSecret = csec
        client.send(req)

    def on_disconnected(_client, reason):
        if not done.is_set():
            result_holder["error"] = reason
            done.set()

    client.setMessageReceivedCallback(on_message)
    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.startService()

    reactor_thread = threading.Thread(
        target=reactor.run,
        kwargs={"installSignalHandlers": False},
        daemon=True,
    )
    reactor_thread.start()

    if not done.wait(timeout=20):
        print("ERROR: timed out waiting for cTrader response.", file=sys.stderr)
        return 1

    try:
        client.stopService()
    except Exception:
        pass
    try:
        reactor.callFromThread(reactor.stop)
    except Exception:
        pass

    if result_holder["error"] is not None:
        print(f"ERROR: {result_holder['error']}", file=sys.stderr)
        return 1

    accounts = result_holder["accounts"] or []
    if not accounts:
        print("No accounts returned. Re-run scripts/ctrader_oauth.py and "
              "make sure you ticked at least one account on the consent page.")
        return 1

    print("\nAccounts visible to this OAuth grant:")
    for a in accounts:
        ctid = a.ctidTraderAccountId
        is_live = bool(getattr(a, "isLive", False))
        print(f"  ctidTraderAccountId={ctid}  isLive={is_live}")

    print("\n--- Paste into .env (pick ONE account) ---")
    first = accounts[0]
    print(f"CTRADER_ACCOUNT_ID={first.ctidTraderAccountId}")
    print(f"CTRADER_ENVIRONMENT={'live' if getattr(first, 'isLive', False) else 'demo'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
