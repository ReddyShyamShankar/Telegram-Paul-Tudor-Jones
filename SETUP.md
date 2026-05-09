# SETUP — step by step

Do every step in order. Do not skip.

---

## 0. Open a Terminal

1. Open Terminal app.
2. Run: `cd "/Users/reddyshyamshankar/Documents/Code/Trade Signal Generator"`

---

## 1. Create the Python environment

1. Run: `python3 -m venv .venv`
2. Run: `source .venv/bin/activate`
3. Run: `pip install -e ".[dev]"`
4. You should see `Successfully installed ...` at the end.

---

## 2. Create `.env`

1. Run: `cp .env.example .env`
2. Open `.env` in any text editor.
3. Leave it open. You will paste values into it during the next sections.

---

## 3. cTrader Open API — application

1. Open a browser. Go to: `https://openapi.ctrader.com/`
2. Click **Sign in**. Use your Pepperstone / cTrader account credentials.
3. Click **Applications** in the top menu.
4. Click **Add new application**.
5. Fill the form:
   - Name: `tsg`
   - Description: `Personal trade signals`
   - Redirect URI: `http://localhost:8080/callback`
   - Scope: tick **trading**
6. Submit. Wait 24–72 hours for approval (you receive an email).
7. After approval: open the application page. You see **Client ID** and **Client Secret**.
8. In `.env`, paste:
   - `CTRADER_CLIENT_ID=` *(value of Client ID)*
   - `CTRADER_CLIENT_SECRET=` *(value of Client Secret)*

---

## 4. cTrader OAuth — refresh token

1. In Terminal (still in the project folder, with `.venv` active):
2. Run: `python scripts/ctrader_oauth.py`
3. A browser tab opens. Click **Authorise**.
4. The terminal prints lines starting with `CTRADER_REFRESH_TOKEN=`, `CTRADER_ACCOUNT_ID=`, `CTRADER_ENVIRONMENT=`.
5. Copy each of those three lines into `.env`, replacing the existing line with the same name.
6. Save `.env`.

---

## 5. Telegram User API — `api_id` and `api_hash`

1. Open a browser. Go to: `https://my.telegram.org/`
2. Log in using your Telegram phone number. Telegram sends a code to your Telegram app — enter it.
3. Click **API development tools**.
4. Fill the **Create new application** form:
   - App title: `tsg`
   - Short name: `tsg`
   - Platform: `Desktop`
5. Click **Create application**.
6. The page shows two values: **App api_id** (numeric) and **App api_hash** (hex string).
7. In `.env`, paste:
   - `TG_API_ID=` *(numeric value)*
   - `TG_API_HASH=` *(hex string)*
   - `TG_PHONE=+countrycodeNumber` *(e.g. `+919876543210`. No spaces.)*
8. Save `.env`.

---

## 6. Telegram session — one-time login

1. In Terminal: `python scripts/telegram_login.py`
2. Telegram sends a code to the Telegram app on your phone.
3. Enter the code in the terminal.
4. If you have 2-factor on Telegram, enter the password.
5. You should see `Logged in as: <your name> id=<number>`.
6. A file `.tsg.session` is created in the project folder. **Do not delete it.**

---

## 7. List your channels — find IDs

1. In Terminal: `python scripts/telegram_list_chats.py`
2. The terminal prints a table of channels you are part of.
3. Look at the rightmost column **broadcast?**. The bot only needs IDs of rows where the **admin?** column is `True`.
4. The script prints a final line:
   `Suggested TG_CHANNEL_IDS line for .env:`
   `  TG_CHANNEL_IDS=-100xxxx,-100yyyy,...`
5. Copy that suggested line into `.env`, replacing the existing `TG_CHANNEL_IDS=` line.
6. Save `.env`.

---

## 8. chart-img.com key

1. Open a browser. Go to: `https://chart-img.com/`
2. Click **Sign up**. Free tier: 100 charts / month.
3. After login, go to **Dashboard** → **API Keys**.
4. Copy your API key.
5. In `.env`, paste:
   - `CHART_IMG_API_KEY=` *(your key)*
6. Save `.env`.

---

## 9. Run the bot

1. In Terminal: `pytest`
2. You should see `... passed`.
3. In Terminal: `python -m tsg`
4. You should see lines like:
   - `loaded config: 21 pairs, min_rr=3.0, env=demo, channels=N`
   - `cTrader access token obtained`
   - `cTrader connected`
   - `Telegram authorised as <your name>; broadcasting to N channels`
   - `scanner started; 21 pairs whitelisted`
5. Leave it running.

---

## 10. Manual scratch (optional, when needed)

1. Find the trade ID in the Telegram caption or in `data/trades.db`.
2. In Terminal (a new tab is fine): `python scripts/scratch_trade.py <trade_id>`
3. Within 60 seconds the bot posts a `🟡 SCRATCHED` quote-reply on each channel.

---

## 11. Always-on (macOS launchd, optional)

1. Edit `com.shyam.tsg.plist`. Replace every path with the real absolute path on your machine.
2. Run: `cp com.shyam.tsg.plist ~/Library/LaunchAgents/`
3. Run: `launchctl load ~/Library/LaunchAgents/com.shyam.tsg.plist`
4. Verify: `launchctl list | grep com.shyam.tsg`. You should see a line.

---

## 12. If something is wrong

1. **Stop the bot:** in the Terminal where it runs, press `Ctrl+C`.
2. **Check logs:** if running under launchd, see `data/tsg.err.log`.
3. **Re-run failing step from this file.**
4. If the cTrader access token expired or the refresh token was invalidated, the bot exits with: `cTrader refresh token invalid. Re-run: python scripts/ctrader_oauth.py`. Do exactly that, then restart.
5. If Telegram session expired (rare; only after long inactivity or you logged out elsewhere), re-run step 6.

---

## 13. Rotate any credentials previously shared in chat

1. cTrader: open https://openapi.ctrader.com/ → your application → **Reset Secret**. Re-do step 4.
2. chart-img: open https://chart-img.com/dashboard → **API Keys** → **Regenerate**. Update `.env`.
3. Telegram api_id/api_hash do not need rotating; they are not secret on their own.
