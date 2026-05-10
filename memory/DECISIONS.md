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

## D006 — 2026-05-10T00:00:00Z
**Decision:** Production signal chart = 4-pane composite via 4× chart-img `advanced-chart` calls + Pillow stitch (1600×900). Default panes 1D / 4H / 1H / 15m. Locked color palette + override schema baked into `src/tsg/chart/chartimg.py`. Per-signal RR drawing carried by the `advanced-chart` endpoint.
**Why:** chart-img has two non-overlapping endpoints — `layout-chart/<id>` reproduces a saved TV layout pixel-exact but cannot inject new drawings; `advanced-chart` accepts dynamic Long Position drawings but renders only one pane per call. Neither alone satisfies "4-pane multi-TF + per-signal RR box". Composite is the only path. 13 iterations to nail the schema (legacy vs canonical key names, fractional alpha rejection on `stopBackground`, range preset validation, candleStyle keys, volume legend un-hideable).
**Alternatives considered:** (a) `layout-chart/gm7qCQc5` only (loses per-signal RR), (b) single-pane `advanced-chart` (loses multi-TF), (c) Playwright screenshot of actual TV chart (10-30s per render, fragile, RAM-heavy), (d) drop chart-img → mplfinance (free but doesn't match TV).
**Status:** ACTIVE

## D007 — 2026-05-10T17:00:00Z
**Decision:** Caption skeleton locked. No emojis, no em-dashes (`—`), no parenthetical glosses anywhere. Bold direction header (`**LONG**` / `**SHORT**` / `**TP HIT**` / `**SL HIT**`). RR formatted `1:N` integer when whole (`1:3`, never `1:3.0`). Price precision per pair: JPY 2 decimals (`156.20`), non-JPY 5 decimals (`1.17500`). Two narrative paragraphs after levels: plain SMC thesis + rotated psych/risk closer. Closer rotation deterministic via SHA-256 of entry timestamp from a curated pool of 18 entry / 9 TP / 9 SL variants.
**Why:** user explicit — "always it should be me talking to the other singular person directly. It should not look like a generated text or template." Curated pool gives variety without LLM dependency or per-signal cost.
**Alternatives considered:** (a) per-signal LLM call for fully unique narratives (cost + dependency), (b) single fixed template (sounds robotic), (c) bilingual SMC + plain-English glosses (tested, dropped — user found parens cluttered).
**Status:** ACTIVE

## D008 — 2026-05-10T19:00:00Z
**Decision:** Hand-off to user's second SMC project = standalone ZIP at `~/Downloads/tsg-chart-kit.zip`. Six-file kit (`chartimg.py`, `INSTRUCTIONS.md`, `smoke_chart.py`, `smoke_lifecycle.py`, `requirements.txt`, `.env.example`). Defaults to 4H / 1H / 15m / 5m panes for 15-min base-TF bot. Shares same chart-img API key + TV session cookies; only `TG_CHANNEL_IDS` differs.
**Why:** chart subsystem took 13 iterations to lock; not acceptable to relive that loop in second project. Kit's INSTRUCTIONS.md captures schema gotchas + locked palette + smoke checklist so next Claude thread reads once and is done. ZIP chosen over GitHub branch / new repo for deliverable simplicity per user pick.
**Alternatives considered:** (a) push branch to GitHub, second project clones (couples projects), (b) new standalone GitHub repo (more setup), (c) PyPI package (maintenance overhead).
**Status:** ACTIVE

## D009 — 2026-05-10T17:00:00Z
**Decision:** Pair coverage expanded 21 → 28. Added 7 GBP combos to `config/pairs.yaml`: GBP_USD, EUR_GBP, GBP_JPY, GBP_CHF, GBP_CAD, GBP_AUD, GBP_NZD. v1 USD-major auto-execution scope (R006) extended to include GBP_USD.
**Why:** user wants full {AUD, NZD, JPY, EUR, GBP, CHF, USD, CAD} = 8C2 = 28-pair coverage. GBP_USD is a USD-major so qualifies for v1 auto-execute. Other GBP crosses signal-only until v2 cross-pair sizing lands.
**Alternatives considered:** (a) keep 21 — user rejected, (b) add only GBP majors (subset) — rejected, user wants full GBP coverage.
**Status:** ACTIVE

## D010 — 2026-05-10T15:00:00Z
**Decision:** Wire TradingView session cookies (`sessionid` / `sessionid_sign`) into `.env` as `TV_SESSION_ID` / `TV_SESSION_ID_SIGN`, pass on every chart-img POST. Schedule one-time reminder at +80 days via `mcp__scheduled-tasks__create_scheduled_task` to re-fetch before TV's ~90-day rotation invalidates them.
**Why:** without cookies chart-img loads charts as anonymous and skips paid TV indicators. TV server-side rotates cookies — no way to make them permanent. User profile mandates calendar reminder before expiry, not after outage. Reminder fires `2026-07-29 09:00 IST`.
**Alternatives considered:** (a) skip cookies entirely (loses paid-indicator support — status quo before this session), (b) automated cookie refresh via headless TV login (impossible without user's password + 2FA), (c) reminder at +89 days (too tight if user is offline).
**Status:** ACTIVE
