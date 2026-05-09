# Deploy to PythonAnywhere

PA tier required: **Hacker plan ($5/mo)** or higher. Free tier blocks
outbound TCP to non-whitelisted hosts (cTrader's `demo.ctraderapi.com:5035`
is not whitelisted), and free tier has no always-on tasks.

---

## 1. Push the code to a Git repo (GitHub/GitLab/Bitbucket)

On your Mac:

```
cd "/Users/reddyshyamshankar/Documents/Code/Trade Signal Generator"
git init
git add -A
git commit -m "tsg: initial"
git remote add origin <your repo url>
git push -u origin main
```

Confirm `.env` and `.tsg.session` are NOT in the commit (the `.gitignore`
already excludes them).

---

## 2. PythonAnywhere setup

1. Log in to https://www.pythonanywhere.com/.
2. Open **Consoles** → **Bash**.
3. Run:

```
git clone <your repo url> tsg
cd tsg
python3.11 -m venv .venv     # PA supports up to 3.11; Telethon + ctrader-open-api both compatible
source .venv/bin/activate
pip install -e ".[dev]"
chflags nohidden .venv/lib/python3.11/site-packages/*.pth 2>/dev/null || true
pytest      # should print "23 passed"
```

If pytest fails with "No module named tsg", run:
```
mkdir -p .venv/lib/python3.11/site-packages
echo "$HOME/tsg/src" > .venv/lib/python3.11/site-packages/tsg-editable.pth
```

---

## 3. Upload secrets

Two files need to come from your Mac (NOT git):

- `.env` — the actual key file
- `.tsg.session` — Telegram login session

On PA Bash console:

```
nano .env
# paste contents of your local .env, save with Ctrl+O, Ctrl+X
```

For `.tsg.session`: PA Files tab → upload `.tsg.session` from your Mac to
`/home/<youruser>/tsg/.tsg.session`.

(Do NOT re-run `scripts/telegram_login.py` on PA — Telethon would send a
new SMS and might split your session. Reuse the session file from local.)

---

## 4. Always-on task

### Option A — fresh task (1 spare always-on slot)

1. PA dashboard → **Tasks** tab → **Always-on tasks** section.
2. Click **Create a new always-on task**.
3. Command:
   ```
   cd /home/<youruser>/tsg && /home/<youruser>/tsg/.venv/bin/python run.py
   ```
4. Click **Create**. PA starts the task immediately and restarts on crash.

### Option B — merge with existing task (no spare slot)

If both always-on slots are already in use (e.g. you already run `edgewonk bot`
and `Ctrader-copier`), use the supervisor script to run `tsg` alongside one
existing task in the same slot.

The supervisor in this repo (`scripts/pa_supervisor.sh`) by default merges
`tsg` with `edgewonk bot`. Edit env vars at the top of the file if your paths
differ.

Steps:

1. PA Bash console:
   ```
   chmod +x ~/tsg/scripts/pa_supervisor.sh
   ```
2. PA dashboard → **Tasks** tab.
3. Find the **edgewonk bot** always-on task. Click the **edit** (pencil) icon.
4. Change the **command** field from:
   ```
   cd EdgeWonk_journal_V2.0 && source venv/bin/activate && python main.py
   ```
   to:
   ```
   bash /home/<youruser>/tsg/scripts/pa_supervisor.sh
   ```
5. Save.
6. **Disable** then **Re-enable** the task (so PA picks up the new command).
7. Open the task's log file. You should see lines from both bots:
   ```
   [supervisor 2026-05-08T18:00:00Z] starting edgewonk (cwd=/home/<youruser>/EdgeWonk_journal_V2.0)
   [supervisor 2026-05-08T18:00:00Z] starting tsg (cwd=/home/<youruser>/tsg)
   ...edgewonk's own log lines...
   2026-05-08 18:00:01,000 INFO tsg.main :: loaded config: 21 pairs, ...
   ```

Behaviour: if either child crashes, supervisor exits → PA restarts → both
bots restart together. Unified lifecycle. Logs interleave in the one PA
task log.

The other always-on task (`Ctrader-copier`) is unchanged.

---

## 5. Verify

1. Open the task's **log file** link from the Tasks tab.
2. Within 30 seconds you should see:
   ```
   loaded config: 21 pairs, ... exec=ON, risk=1.0%, daily_kill=3.0R
   cTrader access token obtained
   cTrader connected
   cTrader: NN symbols loaded
   Telegram authorised as ... ; broadcasting to N channels
   scanner started; 21 pairs whitelisted
   ```
3. Wait. First signal may take hours/days (SMC discipline).

---

## 6. Operational

| Need | How |
|---|---|
| Stop bot | Tasks tab → click the running task → **Disable** |
| Restart bot | Tasks tab → click task → **Re-enable** |
| Pull new code | Bash console: `cd tsg && git pull` then disable+enable task |
| View logs | Tasks tab → "log file" link next to the task |
| Update `.env` | `nano /home/<youruser>/tsg/.env` then disable+enable task |
| Manual scratch | Bash console: `cd tsg && source .venv/bin/activate && python scripts/scratch_trade.py <id>` |
| Daily DB inspection | `sqlite3 ~/tsg/data/trades.db "SELECT id, pair, status, pnl_r, lots FROM trades ORDER BY id DESC LIMIT 20"` |

---

## 7. Costs

- PA Hacker: $5/mo
- chart-img: $0 (free tier 100 charts/mo) until you outgrow → $15/mo for 6k/mo
- cTrader Open API: free
- Telegram User API: free
- **Total ongoing: ~$5/mo**

---

## 8. Common failure modes

| Symptom in log | Fix |
|---|---|
| `cTrader refresh token invalid. Re-run: python scripts/ctrader_oauth.py` | Re-run OAuth on Mac, copy new `CTRADER_REFRESH_TOKEN` line into PA `.env`, restart task |
| `Telegram session not authorised` | Re-upload `.tsg.session` from Mac |
| `cTrader: unknown symbol 'XYZ'` | Pepperstone uses suffixed symbols (e.g. `EURUSD.r`); update `_instrument_to_ctrader` in `src/tsg/feed/client.py` |
| `chart-img: 400 Bad Request` | chart-img field name mismatch; one-line fix in `src/tsg/chart/chartimg.py::build_payload` |
| Always-on task keeps restarting | Check log; if cTrader access denied, refresh token is stale → re-OAuth |

---

## 9. Disable execution remotely

To pause auto-trading without stopping the bot (still posts signals):

```
nano ~/tsg/.env
# change: TSG_ENABLE_EXECUTION=no
```

Then disable+enable the always-on task.
