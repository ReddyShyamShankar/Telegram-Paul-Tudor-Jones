## STATE
Trade Signal Generator is live in production on PythonAnywhere as the always-on task "Paul TJ (Telegram + cTrader signal bot)". exec=ON. Demo cTrader account 45561836 (Pepperstone). Telegram broadcasting to 1 channel as user @ptfadmin. Scanner sleeping until next H1 close; tracker polling every 60s. 24/24 unit tests green on Mac (Python 3.13). chart-img v2 wrapper rewritten with correct field names (`stopPrice`/`targetPrice`/`startDatetime`/camelCase overrides/`rgba()` colors) + TV-layout-`gm7qCQc5` palette (mint green / light gray, light theme); `ChartImg.render_layout` added for pixel-exact saved-layout snapshots. Repo `ReddyShyamShankar/Telegram-Paul-Tudor-Jones` at commit 4905eb1 on `main` (worktree changes uncommitted).

## NEXT_LINE
Watch the Telegram channel for the first SMC signal lifecycle (signal post → outcome quote-reply). On first signal, verify (a) chart-img RR-box renders correctly, (b) cTrader market order fills with broker SL/TP attached, (c) tracker detects close + posts quote-reply.

## MEMORY_KEY
tsg-paul-tj-pa-deploy-live

## OPEN_QUESTIONS
- chart-img drawing field names — RESOLVED 2026-05-10. Correct schema: input `entryPrice`/`stopPrice`/`targetPrice`/`startDatetime` (ISO-8601). Override keys camelCase: `lineColor`/`lineWidth`/`profitZoneColor`/`profitZoneTransparency`/`stopZoneColor`/`stopZoneTransparency`/`showLabel`/`showStats`. Colors only as `rgba(R,G,B,A)`. Default palette mirrors TV layout `gm7qCQc5` (mint green / light gray, light theme). Live-verified via `scripts/tg_smoke_rr.py` and module-path `ChartImg.render()`. Layout-chart endpoint live-verified via `scripts/tg_smoke_layout.py` (msg #17 to channel "Check").
- cTrader `place_market_order` `volume` units convention — used `lots * 100` per Open API docs; Pepperstone may apply broker-specific lot-size multiplier. First live execution will confirm or expose mis-sizing.
- Multi-channel broadcast: only 1 channel currently (`-1003771780932`); user mentioned 5–10. Need to add more channel IDs to `TG_CHANNEL_IDS` once user lists them.
- Cross-pair execution (EUR_AUD, AUD_JPY etc.): currently signal-only. v2 needs USD/quote conversion-rate fetch for pip-value math.
- PA disk quota: 75% full (767 MB of 1 GB). One bad pip install could push over.
