# PROGRESS — append-only, numbered, timestamped

## #001 — 2026-05-09T04:05:00Z — feat
Bootstrap project memory + first checkpoint after PA deploy

Trade Signal Generator built end-to-end across one long multi-session run:
- 47 files committed to GitHub (`ReddyShyamShankar/Telegram-Paul-Tudor-Jones`).
- 23 unit tests passing on Mac (Python 3.13).
- Deployed to PythonAnywhere as always-on task "Paul TJ (Telegram + cTrader signal bot)" — running, exec=ON, cTrader demo account 45561836, broadcasting to 1 Telegram channel (ptfadmin).
- Auto-execution layer wired (1% risk, broker bracket SL/TP, daily kill-switch -3R, live-account guard).

Next: monitor first SMC signal lifecycle on Telegram + DB; expand to multi-channel broadcast when more channels added; v2 cross-pair execution.

## #002 — 2026-05-09T13:00:00Z — feat
Offline backtest harness + 57-trade replay over 8y Dukascopy H1

`scripts/backtest.py` + `scripts/backtest_image.py` added. Pulls Dukascopy H1 BID for 21 pairs over 2018-01 → 2026-05, replays the live scanner's `h4_bias` → `find_smc_setup` → `compute_rr` pipeline on a sliding 200-bar window, simulates SL/TP first-touch on subsequent bars. Writes `data/backtest_report.{md,html}` + a 4-pane PNG infographic.

Result: 57 trades across 8.4 years (~6.8/yr), win rate 50.9%, +15.59R total, profit factor 1.557, expectancy +0.273R/trade, max drawdown 7.0R, max loss streak 7. Avg hold 5.2h (intraday). Avg gap 48 days. EUR_CHF / EUR_JPY / CHF_JPY = 39% of all signals; 5 pairs never fired. Backtest scripts left untracked.

## #003 — 2026-05-10T00:00:00Z — fix
chart-img v2 schema rewrite + 4-pane composite renderer locked at v13

`src/tsg/chart/chartimg.py` rewritten. Old `build_payload` used `stopLoss` / `profitLevel` / `time` int — chart-img v2 silently 422'd these so every signal's chart render in production would have failed.

Fixed: drawing input `entryPrice` / `stopPrice` / `targetPrice` / `startDatetime` (ISO). Override keys `profitZoneColor` (fractional rgba alpha OK) for profit, legacy `stopBackground` for stop (only key that actually paints; fractional alpha 422s so use lighter base hex). 4-pane composite via 4× advanced-chart calls (1D / 4H / 1H / 15m) + Pillow stitch into 1600×900 PNG. Locked palette: mint green profit / very light gray stop / blue uniform candles / blue volume / no entry line / no text overlays / thin black border / shiftRight 20.

TV session cookies (`TV_SESSION_ID` + `TV_SESSION_ID_SIGN`) wired through every advanced-chart POST. 13 iterations to nail. Live-verified into test channel `PTJ - 1 H` (`-1003928938607`) via @statosphere session at `.tsg-test.session`. Committed as `04955db`.

## #004 — 2026-05-10T17:00:00Z — feat
28-pair coverage + caption rewrite + locked text contract

`config/pairs.yaml` expanded 21 → 28 pairs (added GBP_USD, EUR_GBP, GBP_JPY, GBP_CHF, GBP_CAD, GBP_AUD, GBP_NZD). USD-major auto-execution scope grew 6 → 7 (GBP_USD).

Caption rewrite (`src/tsg/tg/bot.py` + new `src/tsg/tg/captions.py`): no emojis, no em-dashes, no parenthetical glosses, direct second-person voice. Bold direction header. RR `1:N` integer when whole. JPY pairs 2-decimal price, non-JPY 5-decimal. 18 entry / 9 TP / 9 SL closers rotated by SHA-256 of entry timestamp. `_format_thesis` rewritten — plain SMC, no bilingual glosses.

Tests 26 → 42 (16 new caption tests including emoji regex + em-dash + JPY format + rotation determinism). Committed as `2fb5073`.

## #005 — 2026-05-10T19:00:00Z — feat
Chart-Kit ZIP shipped to `~/Downloads/tsg-chart-kit.zip` for sister project

Built `chart-kit/` in worktree as the standalone hand-off package for the user's second SMC project (15-min base TF, same strategy, separate Telegram channel, shared TV cookies + chart-img key):
- `chartimg.py` — refactored standalone (no project imports). Public API: `ChartImg.render_signal_chart(symbol, direction, entry_price, stop_price, target_price, entry_datetime)`. Default panes 4H / 1H / 15m / 5m.
- `INSTRUCTIONS.md` — full hand-off doc covering chart-img v2 schema gotchas, locked palette, range presets, what CAN'T be done, smoke checklist, refresh schedule.
- `smoke_chart.py` (no Telegram) + `smoke_lifecycle.py` (entry+exit posts) + `requirements.txt` + `.env.example`.

Verified live by rendering CAD/CHF long via kit's standalone `chartimg.py`. ZIP 14 KB, 6 files. Untracked in git (delivery artefact, not product).

Also: 80-day TradingView cookie refresh reminder scheduled via `mcp__scheduled-tasks__create_scheduled_task` (fires `2026-07-29 09:00 IST`).

## #006 — 2026-05-11T05:30:00Z — note
Checkpoint snapshot — chart subsystem locked, kit handed off

Memory bookkeeping pass — captured the chart-img + caption + chart-kit work that occurred since checkpoint #001. Working tree state: branch `claude/blissful-spence-ed4ece`, two new commits (`04955db`, `2fb5073`), four untracked items (`chart-kit/`, `memory/.session-end-warning`, `scripts/backtest.py`, `scripts/backtest_image.py`). 42/42 tests green. Kit ZIP delivered. PA bot still posting from production session as @ptfadmin to `Private Trading Floor 🏙` (`-1003771780932`) when signals fire — expected fire rate ~7/year, so monitoring is passive.
