# DECISIONS — append-only, numbered, never overwrite (supersede with status edit)

## D001 — 2026-05-09T04:05:00Z
**Decision:** Use cTrader Open API (Pepperstone broker) as price feed, not OANDA.
**Why:** OANDA rejected user's account application (likely jurisdictional). Pepperstone cTrader works for user, free Open API access, supports all 21 pairs, real-time spot ticks.
**Alternatives considered:** OANDA practice (rejected by broker), TwelveData (paid for full speed), Alpha Vantage (rate-limit too tight), MetaTrader 5 Python bridge (Windows-only — user on Mac), yfinance (15-min delayed).
**Status:** ACTIVE

## D002 — 2026-05-09T04:05:00Z
**Decision:** Use Telegram User API (Telethon) for broadcast, not Bot API (`python-telegram-bot`).
**Why:** User runs 5–10 channels and cannot add a Bot-API bot as admin to each. User API logs in as the user (one-time SMS), inherits whatever channel post permissions the user already has — zero per-channel config.
**Alternatives considered:** Bot API + per-channel admin grant (user refused), Discord webhook, Twitter/X (public), local web dashboard.
**Status:** ACTIVE

## D003 — 2026-05-09T04:05:00Z
**Decision:** Use chart-img.com v2 Advanced Chart for the visual RR-box screenshots.
**Why:** Native TradingView Long/Short Position drawings anchored at entry candle time. Free tier 100 charts/month covers expected signal frequency.
**Alternatives considered:** Playwright + TradingView screenshot (fragile, 10-30s render, RAM-heavy), mplfinance/plotly (no TradingView UI), TradingView snapshot share URL (no overlay control).
**Status:** ACTIVE

## D004 — 2026-05-09T04:05:00Z
**Decision:** Conservative execution profile: 1% equity per trade, round lots DOWN, force min 0.01 lot, broker bracket SL/TP, daily kill -3R, live-account guard `TSG_ALLOW_LIVE=yes`. v1 USD-major pairs only.
**Why:** User explicit choice from "Conservative vs Aggressive vs Custom" prompt. Cross-pair pip-value math (USD/quote conversion) deferred to v2 to avoid mis-sizing risk in v1.
**Alternatives considered:** Aggressive (round up, no daily kill), Custom (user-spelled values).
**Status:** ACTIVE

## D005 — 2026-05-09T04:05:00Z
**Decision:** Deploy on PythonAnywhere Developer plan. Edgewonk project deleted with user consent to free its always-on slot for tsg ("Paul TJ" task).
**Why:** PA Developer plan = 2 always-on tasks max; both slots used (Ctrader-copier + edgewonk). User chose to delete edgewonk entirely instead of merging via supervisor or upgrading plan.
**Alternatives considered:** Upgrade to PA Custom plan ($13+/mo for +1 always-on), Hetzner/DigitalOcean VPS ($5/mo no quota), supervisor merge (Option B in `DEPLOY-pythonanywhere.md` — superseded by this decision).
**Status:** ACTIVE
