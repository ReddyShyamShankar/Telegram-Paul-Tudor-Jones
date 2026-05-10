# CLAUDE.md — Project Memory Anchor

> Auto-loaded by Claude Code on every session start. Read this first, then `LATEST_SEED.md`, then last 5 entries of `PROGRESS.md`. Brief the user in 6 lines (DNA, state, next line, memory key, open questions, last 3 decisions) before accepting any input.

## PROJECT_DNA
- **Name:** Trade Signal Generator (repo: `Telegram-Paul-Tudor-Jones`)
- **North star:** Paul Tudor Jones-disciplined FX signal bot. Generate SMC-based signals on 21 G7 pairs at min 1:3 R:R, broadcast to Telegram channels, auto-execute on cTrader demo at 1% risk per trade.
- **Non-negotiables:**
  1. Min 1:3 R:R on every trade — never bend.
  2. 1% equity per trade max — never bend.
  3. Hard live-account guard: `TSG_ALLOW_LIVE=yes` required if `CTRADER_ENVIRONMENT=live`.
  4. Daily kill-switch at -3R cumulative — block new trades for the day.
  5. 21-pair whitelist only ({AUD,NZD,JPY,EUR,CHF,CAD,USD} combos in `config/pairs.yaml`). Never trade outside.
- **Working style:** terse caveman (drop articles/filler/hedging; fragments OK). One action per step. AI does it itself when possible (Bash/Edit/MCP/Chrome MCP); only asks user as last resort with numbered exact instructions, expected output, failure mode.
- **Locked stack:** Python 3.10+, cTrader Open API (`ctrader-open-api>=0.9.2`), Telethon User API (`telethon>=1.36`), chart-img.com v2 (TradingView-style RR-box), SQLite (stdlib), Twisted (reactor in worker thread), asyncio scanner+tracker. Hosted on PythonAnywhere as always-on task.

## Auto-resume directive
On session start: silently read `memory/LATEST_SEED.md` and the last 5 entries of `memory/PROGRESS.md`. Then print exactly this 6-line briefing before doing anything else:

1. **DNA:** <one-line restate of north star>
2. **State:** <2–3 sentence current state from latest seed>
3. **Next line:** <literal next action>
4. **Memory key:** <anchor phrase>
5. **Open questions:** <bullets>
6. **Last 3 decisions:** <ids + one-line each>

## Foundational rules
(Append rules here as the project evolves. Never delete — supersede with `SUPERSEDED-BY: #id`.)

- **R001** (2026-05-09): Never write secrets to project files. User pastes into `.env` themselves. `.env`, `.tsg.session` always gitignored. **Why:** chat logs are not a safe place for credentials; user already had to rotate cTrader + chart-img keys after pasting in chat.
- **R002** (2026-05-09): Action priority — (1) AI does it via Bash/Edit/MCP, (2) AI uses Chrome MCP / computer-use for UI work, (3) only ask user as fallback with numbered exact instructions, expected output, failure mode. **Why:** user explicitly stated this is their skill philosophy; matches their Google-Maps-style preference for instructions.
- **R003** (2026-05-09): On macOS Python 3.13, all `.pth` files in venv site-packages get auto-tagged `UF_HIDDEN`, breaking pip's editable install. Workaround: project ships `conftest.py` and `run.py` at root that prepend `src/` to `sys.path`. **Why:** known macOS-specific Python 3.13 site.py + xattr interaction; tests + runtime both fail without the bootstraps.
- **R004** (2026-05-09): On PythonAnywhere, Python user-site (`~/.local`) overrides venv site-packages for some packages (Telethon in particular). Run script with `PYTHONNOUSERSITE=1` to force venv to win. **Why:** PA had Telethon 1.36 globally; tsg requires 1.43 for the session-file format we generated locally.
- **R005** (2026-05-09): cTrader rotates the refresh token on each refresh exchange. `tsg/main.py::_persist_refresh_token` writes the new value back to `.env` atomically. If cTrader returns `invalid_grant`, exit non-zero (no tight-loop) and print `python scripts/ctrader_oauth.py` recovery hint. **Why:** observed silent invalidation when refresh token gets used by parallel scripts (`ctrader_list_accounts.py` rotated it once, broke `run.py`).
- **R006** (2026-05-09, updated 2026-05-10): v1 auto-execution scope = USD-major pairs only (EUR_USD, USD_JPY, USD_CHF, USD_CAD, AUD_USD, NZD_USD, GBP_USD). Cross pairs (EUR_AUD, AUD_JPY, GBP_JPY, etc.) still post Telegram signals but DO NOT execute. v2 needs USD/quote conversion-rate math. **Why:** position-size formula simple for USD majors; cross-pair pip-value math requires extra rate fetch and risks mis-sizing in v1.

- **R007** (2026-05-10): chart-img v2 schema rules baked into `src/tsg/chart/chartimg.py` and `chart-kit/chartimg.py`. Long/Short Position drawing input keys: `entryPrice` / `stopPrice` / `targetPrice` / `startDatetime` (ISO-8601). NOT `stopLoss` / `profitLevel` / `time`. Override keys: `profitZoneColor` (accepts `rgba(R,G,B,a)` with fractional alpha) for profit; **`stopBackground`** (canonical key that actually paints; rejects fractional alpha → use lighter base hex) for stop. `stopZoneColor` is silently ignored. Colors only as `rgb(R,G,B)` or `rgba(R,G,B,A)` — hex 422s. `range` only accepts `1D / 5D / 1M / 3M / 6M / 1Y / 5Y / ALL` (2D, 3D, 1W, 2W all 422). Volume study legend cannot be hidden via overrides — accept it or drop the study. **Why:** 13-iteration discovery cycle in 2026-05-10 session; must not be relearned. Full table in `chart-kit/INSTRUCTIONS.md`.

- **R008** (2026-05-10): Caption convention — no emojis anywhere, no em-dashes (`—`), no parenthetical glosses, direct second-person ("you") voice. Bold direction header `**LONG**` / `**SHORT**` / `**TP HIT**` / `**SL HIT**`. RR formatted `1:N` integer when whole (`1:3` not `1:3.0`). Price precision: JPY pairs 2 decimals (`156.20`), non-JPY 5 decimals (`1.17500`). Two narrative paragraphs after levels: SMC thesis (plain, no bilingual glosses) + rotated psych/risk closer from a curated pool. Closer rotation deterministic via SHA-256 of entry timestamp. **Why:** user explicit — sound like one person talking to one person, not generated text. Locked in `src/tsg/tg/captions.py` (18 entry / 9 TP / 9 SL closers) + `src/tsg/tg/bot.py::format_signal_caption` + `format_outcome_caption`.
