# Trade Signal Generator

FX trade-signal daemon. SMC-rules-based. Price feed via **cTrader Open API**
(works with any cTrader broker — Pepperstone, IC Markets, FxPro, etc.).
Telegram-delivered, with TradingView-style RR-box chart screenshots via
chart-img.com.

**Hard rules:**
- Pairs whitelist: 21 combinations of {AUD, NZD, JPY, EUR, CHF, CAD, USD} only (`config/pairs.yaml`).
- Minimum **1:3 risk-to-reward** on every trade. Lower = no signal.
- One open trade per pair, ≤ 5 concurrent total.

## Lifecycle

1. **Scanner** (H1 + H4 bar close) → SMC structure + liquidity rules → `Signal` candidate.
2. **R:R gate** rejects if reward < 3× risk *or* an opposing structural level sits between entry and TP.
3. **Chart-img** renders TradingView chart with the Long/Short Position drawing anchored at entry candle.
4. **Telegram** posts photo + caption (entry, SL, TP, R:R, thesis) to your channel.
5. **Tracker** polls cTrader spot prices every 60s on every open trade.
6. On TP hit / SL hit / manual scratch: **quote-reply** the original Telegram message with outcome chart + brief post-trade note.

## One-time setup

### 1. Get a cTrader Open API application

1. Sign up for a Pepperstone (or any) cTrader **demo** account.
2. At https://openapi.ctrader.com/ → Applications → Add new application.
3. Redirect URI: `http://localhost:8080/callback`. Scope: `trading`.
4. Wait 24-72 h for approval. Copy the **Client ID** + **Client Secret**.

### 2. Install the project

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env       # fill CTRADER_CLIENT_ID / SECRET, leave others blank for now
```

### 3. Mint a refresh token

```bash
python scripts/ctrader_oauth.py
```

Browser opens; authorise. Script prints lines for `CTRADER_REFRESH_TOKEN`,
`CTRADER_ACCOUNT_ID`, `CTRADER_ENVIRONMENT`. Paste them into `.env`.

### 4. Telegram bot

1. In Telegram, message `@BotFather`, `/newbot`, follow prompts. Save the bot token.
2. Create a private channel.
3. Channel settings → Administrators → Add Admin → your bot. Enable "Post Messages".
4. Forward any message from the channel to `@userinfobot` to get the numeric channel ID.
5. Paste `TG_BOT_TOKEN` + `TG_CHANNEL_ID` into `.env`.

### 5. chart-img.com key

1. Sign up at https://chart-img.com/. Free tier: 100 charts/month.
2. Copy API key. Paste `CHART_IMG_API_KEY` into `.env`.

### 6. Run

```bash
pytest                # run unit tests
python -m tsg         # start daemon
```

## Manual scratch

If conditions change before SL/TP:

```bash
python scripts/scratch_trade.py <trade_id>
```

Tracker picks it up on the next tick and posts the SCRATCHED quote-reply.

## Always-on (macOS launchd)

`com.shyam.tsg.plist` is a launchd template — edit paths, copy to
`~/Library/LaunchAgents/`, then `launchctl load
~/Library/LaunchAgents/com.shyam.tsg.plist`.

## Layout

```
src/tsg/
├── main.py            # daemon entry
├── config.py          # env + pairs.yaml loader
├── feed/              # cTrader Open API client + pricing
├── strategy/          # bias, levels, SMC, R:R gate, signal orchestrator
├── chart/             # chart-img.com wrapper
├── tg/                # Telegram bot
├── tracker/           # open-trade poll loop
├── post_trade/        # outcome notes
├── scanner.py         # bar-close scanner
└── store/             # SQLite DAO
```
