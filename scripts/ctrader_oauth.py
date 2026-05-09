#!/usr/bin/env python3
"""One-time OAuth helper for the cTrader Open API.

Prereqs (do these in browser):
  1. Sign in at https://openapi.ctrader.com/.
  2. Create an "Application" with Redirect URI = http://localhost:8080/callback
     and the "trading" scope.
  3. Wait for approval (24-72h). After approval, copy the Client ID + Client
     Secret into your .env (CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET).

Then run:
    python scripts/ctrader_oauth.py

The script:
  - Opens your default browser to the cTrader Authorisation page.
  - Spins up a tiny local HTTP server on port 8080 to catch the redirect.
  - Exchanges the auth code for a refresh token + access token.
  - Lists your ctidTraderAccountIds so you can pick the right one.
  - Prints exactly what to paste into .env.

Run once. The refresh token is long-lived; the bot exchanges it for short-
lived access tokens automatically (see CTraderClient).
"""
from __future__ import annotations

import http.server
import os
import socketserver
import sys
import threading
import urllib.parse
import webbrowser

import requests
from dotenv import load_dotenv


AUTH_URL = "https://openapi.ctrader.com/apps/auth"
TOKEN_URL = "https://openapi.ctrader.com/apps/token"
ACCOUNTS_URL = "https://openapi.ctrader.com/connect/tradingaccounts"

REDIRECT_URI = "http://localhost:8080/callback"
SCOPE = "trading"
PORT = 8080


_received_code: dict[str, str] = {}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _received_code["code"] = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authorisation captured.</h2>"
                b"<p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing 'code' query parameter.")

    def log_message(self, *a, **kw):
        pass


def _wait_for_code(timeout: float = 300.0) -> str:
    server = socketserver.TCPServer(("localhost", PORT), _Handler)
    server.timeout = 1.0
    deadline = threading.Event()

    def _serve():
        while not deadline.is_set() and "code" not in _received_code:
            server.handle_request()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    t.join(timeout=timeout)
    deadline.set()
    server.server_close()
    if "code" not in _received_code:
        raise TimeoutError("OAuth timeout: no auth code received.")
    return _received_code["code"]


def main() -> int:
    load_dotenv()
    cid = os.environ.get("CTRADER_CLIENT_ID", "").strip()
    csec = os.environ.get("CTRADER_CLIENT_SECRET", "").strip()
    if not cid or not csec:
        print("ERROR: set CTRADER_CLIENT_ID and CTRADER_CLIENT_SECRET in .env first.",
              file=sys.stderr)
        return 2

    auth_qs = urllib.parse.urlencode({
        "client_id": cid,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "response_type": "code",
    })
    auth_url = f"{AUTH_URL}?{auth_qs}"
    print("Opening browser for authorization...")
    print(f"If it doesn't open, visit:\n  {auth_url}\n")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    code = _wait_for_code()
    print("Auth code received. Exchanging for tokens...")

    r = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": cid,
        "client_secret": csec,
    }, timeout=20)
    r.raise_for_status()
    tok = r.json()
    access = tok.get("accessToken") or tok.get("access_token")
    refresh = tok.get("refreshToken") or tok.get("refresh_token")
    if not access or not refresh:
        print(f"ERROR: unexpected token response: {tok}", file=sys.stderr)
        return 1

    # Print FULL refresh token immediately so the user can save it even if
    # the account-listing REST call below fails (cTrader has changed that
    # endpoint multiple times).
    print("\n--- Paste into .env (refresh token first; long-lived) ---")
    print(f"CTRADER_REFRESH_TOKEN={refresh}")
    print("CTRADER_ENVIRONMENT=demo   # set to 'live' if you authorised a live account")
    print(f"\n(access_token short-lived: {access[:12]}...{access[-6:]})")

    print("\nFetching trading accounts...")
    accounts: list[dict] = []
    for url in (
        "https://openapi.ctrader.com/connect/tradingaccounts",
        "https://api.spotware.com/connect/tradingaccounts",
    ):
        try:
            ar = requests.get(url, params={"access_token": access}, timeout=20)
            if ar.status_code == 200:
                accounts = ar.json().get("data", [])
                break
            print(f"  {url} -> HTTP {ar.status_code}")
        except Exception as e:
            print(f"  {url} -> {e}")

    if not accounts:
        print(
            "\nCould not auto-fetch account list via REST.\n"
            "Run: python scripts/ctrader_list_accounts.py\n"
            "(uses protobuf instead — works regardless of REST URL changes)"
        )
        return 0

    print("\nAccounts visible to this OAuth grant:")
    for a in accounts:
        ctid = a.get("ctidTraderAccountId") or a.get("traderLogin")
        label = (
            f"  ctidTraderAccountId={ctid}  "
            f"login={a.get('traderLogin')}  "
            f"broker={a.get('brokerName')}  "
            f"live={a.get('live')}"
        )
        print(label)
    first = accounts[0]
    ctid = first.get("ctidTraderAccountId") or first.get("traderLogin")
    is_live = bool(first.get("live", False))
    print(f"\nCTRADER_ACCOUNT_ID={ctid}")
    print(f"CTRADER_ENVIRONMENT={'live' if is_live else 'demo'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
