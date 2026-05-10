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
