# SEEDS — append-only checkpoint history

## Checkpoint #001 — 2026-05-09T04:05:00Z

### Changed since previous seed
- (first seed; no previous)

## STATE
Trade Signal Generator is live in production on PythonAnywhere as the always-on task "Paul TJ (Telegram + cTrader signal bot)". exec=ON. Demo cTrader account 45561836 (Pepperstone). Telegram broadcasting to 1 channel as user @ptfadmin. Scanner sleeping until next H1 close; tracker polling every 60s. 23/23 unit tests green on Mac (Python 3.13). Repo `ReddyShyamShankar/Telegram-Paul-Tudor-Jones` at commit 4905eb1 on `main`.

## NEXT_LINE
Watch the Telegram channel for the first SMC signal lifecycle (signal post → outcome quote-reply). On first signal, verify (a) chart-img RR-box renders correctly, (b) cTrader market order fills with broker SL/TP attached, (c) tracker detects close + posts quote-reply.

## MEMORY_KEY
tsg-paul-tj-pa-deploy-live

## OPEN_QUESTIONS
- chart-img drawing field names (`entryPrice`/`stopLoss`/`profitLevel`) — verified against docs but not against a live signal yet; may need one-line fix in `src/tsg/chart/chartimg.py::build_payload` after first render.
- cTrader `place_market_order` `volume` units convention — used `lots * 100` per Open API docs; Pepperstone may apply broker-specific lot-size multiplier. First live execution will confirm or expose mis-sizing.
- Multi-channel broadcast: only 1 channel currently (`-1003771780932`); user mentioned 5–10. Need to add more channel IDs to `TG_CHANNEL_IDS` once user lists them.
- Cross-pair execution (EUR_AUD, AUD_JPY etc.): currently signal-only. v2 needs USD/quote conversion-rate fetch for pip-value math.
- PA disk quota: 75% full (767 MB of 1 GB). One bad pip install could push over.

## Checkpoint #002 — 2026-05-11T05:30:00Z

### Changed since previous seed
- Backtest harness shipped (`scripts/backtest.py` + `scripts/backtest_image.py`, untracked). 8y Dukascopy H1, 21 pairs → 57 trades, 50.9% WR, +15.59R, PF 1.557.
- chart-img v2 schema bug fixed. Old `build_payload` would have 422'd on every live signal. Composite 4-pane renderer locked at v13 (commit `04955db`). 13 iterations.
- `src/tsg/chart/chartimg.py` rewritten: 4× `advanced-chart` calls + Pillow stitch into 1600×900 PNG, blue uniform candles, mint green / very light gray RR zones, no entry line, no text overlays, thin black border, `shiftRight: 20`, Volume study with blue bars (legend not hideable, accepted).
- `ChartImg.render_layout(layout_id)` added for ad-hoc saved-layout snapshots via `/v2/tradingview/layout-chart/<id>`.
- TV session cookies wired through `Config` + `ChartImg` headers. `.env` now has `TV_SESSION_ID` + `TV_SESSION_ID_SIGN`. 80-day refresh reminder scheduled via `mcp__scheduled-tasks__create_scheduled_task` (fires `2026-07-29 09:00 IST`).
- Pair coverage 21 → 28. `config/pairs.yaml` adds GBP_USD, EUR_GBP, GBP_JPY, GBP_CHF, GBP_CAD, GBP_AUD, GBP_NZD. R006 updated — GBP_USD now in v1 USD-major auto-exec scope.
- Caption rewrite shipped (commit `2fb5073`). `src/tsg/tg/bot.py::format_signal_caption` + `format_outcome_caption` rebuilt; new `src/tsg/tg/captions.py` carries 18 entry / 9 TP / 9 SL closers rotated by SHA-256 of entry timestamp. Bilingual SMC parens dropped per user feedback. `src/tsg/strategy/signal.py::_format_thesis` simplified to plain SMC.
- 24 → 42 unit tests. New `tests/test_captions.py` locks no-emoji / no-em-dash / RR int / JPY-2dec / non-JPY-5dec / closer-rotation determinism.
- Test channel `PTJ - 1 H` (id `-1003928938607`) created on user's +91 personal account (@statosphere); `.tsg-test.session` saved alongside production `.tsg.session`. Test smokes in `scripts/tg_smoke_*.py` posted v1-v13 lifecycles for visual review.
- Chart-Kit ZIP shipped to `~/Downloads/tsg-chart-kit.zip` (14 KB, 6 files). Standalone `chartimg.py` + `INSTRUCTIONS.md` for the user's second SMC project (15-min base TF, panes 4H/1H/15m/5m, shares TV cookies + chart-img key, separate Telegram channel). `chart-kit/` directory left in worktree but not committed (delivery artefact).
- Open question 1 (chart-img field names) RESOLVED. Two new rules: R007 (chart-img v2 schema lock), R008 (caption convention). Five new decisions: D006 composite renderer, D007 caption skeleton, D008 chart-kit ZIP hand-off, D009 28-pair coverage, D010 TV cookie wiring + reminder.
- Branch `claude/blissful-spence-ed4ece` ahead of `main` by 2 commits (`04955db`, `2fb5073`). Untracked: `chart-kit/`, `memory/.session-end-warning`, `scripts/backtest.py`, `scripts/backtest_image.py`.

## STATE
Trade Signal Generator is live on PythonAnywhere as the always-on task "Paul TJ" with exec=ON, cTrader demo 45561836, Telegram broadcasting via @ptfadmin to `Private Trading Floor 🏙` (`-1003771780932`). Chart subsystem rebuilt + locked at v13 (4-pane composite, blue candles, mint/gray RR, locked palette, TV cookies wired). 28-pair coverage incl. GBP. Caption convention locked (no emojis / no em-dashes / direct voice / RR int / pip-aware price precision / rotated psych closers). 42/42 tests green on Mac (Python 3.13). Two new commits on branch `claude/blissful-spence-ed4ece` (`04955db`, `2fb5073`); branch not pushed/merged. Chart-Kit ZIP shipped to `~/Downloads/tsg-chart-kit.zip` for the user's second SMC project. Backtest scripts left untracked.

## NEXT_LINE
Push branch `claude/blissful-spence-ed4ece` to GitHub + open PR into `main`, OR fast-forward main locally then push. Then redeploy PA from updated main so live bot starts using the locked chart palette + new captions on its first real H1-close signal fire.

## MEMORY_KEY
tsg-chartkit-locked-2026-05-10

## OPEN_QUESTIONS
- cTrader `place_market_order` volume units (Pepperstone broker-specific lot-size multiplier) — first live execution required to confirm.
- Multi-channel broadcast: still only 1 channel (`-1003771780932`). User mentioned 5–10 eventually. Add IDs to `TG_CHANNEL_IDS` when supplied.
- Cross-pair execution (EUR_AUD, AUD_JPY, GBP_JPY, GBP_CHF, etc.): signal-only. v2 needs USD/quote conversion-rate fetch.
- PA disk quota: was 75% full at last check; needs verification post-Pillow install.
- @ptfadmin not yet a member of `PTJ - 1 H` (`-1003928938607`); production session can't post there. User said they'd add it when ready.
- TV cookies expire `~2026-08-08`; calendar reminder at `2026-07-29 09:00 IST` already scheduled.
- Branch `claude/blissful-spence-ed4ece` not pushed/merged into `main` yet. PA still runs `main` at `4905eb1` so the new chart palette + captions are not live for real signals until merge + redeploy.
