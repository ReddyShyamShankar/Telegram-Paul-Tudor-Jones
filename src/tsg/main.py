"""Daemon entry. Wires Config + Store + cTrader feed + Telegram broadcaster +
chart-img and runs Scanner and Tracker concurrently."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .chart.chartimg import ChartImg
from .config import Config, load_config
from .feed.client import CTraderClient
from .scanner import Scanner
from .store.db import Store
from .tg.bot import TelegramBroadcaster
from .tracker.tracker import Tracker


TOKEN_URL = "https://openapi.ctrader.com/apps/token"

# Refresh-retry tuning. Conservative defaults: 5-min backoff x 3 attempts.
# Prevents crash-loop hammering of cTrader endpoint that triggers 12-hour
# rate-limit bans. Hard-deny errors skip the retry loop entirely.
REFRESH_MAX_RETRIES = 3
REFRESH_BACKOFF_SECONDS = 300
HARD_DENY_TOKENS = (
    "invalid_grant", "invalid_token", "INVALID_REFRESH_TOKEN",
    "ACCESS_DENIED",
)

log = logging.getLogger(__name__)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )


def _persist_refresh_token(env_path: Path, new_refresh: str) -> None:
    """Atomically rewrite CTRADER_REFRESH_TOKEN line in .env."""
    if not env_path.exists():
        log.warning(".env at %s missing; skipping refresh-token persist", env_path)
        return
    text = env_path.read_text()
    pattern = re.compile(r"^CTRADER_REFRESH_TOKEN=.*$", re.MULTILINE)
    if pattern.search(text):
        new_text = pattern.sub(f"CTRADER_REFRESH_TOKEN={new_refresh}", text)
    else:
        new_text = text.rstrip() + f"\nCTRADER_REFRESH_TOKEN={new_refresh}\n"
    tmp = env_path.with_suffix(".env.tmp")
    tmp.write_text(new_text)
    os.replace(tmp, env_path)
    log.info("CTRADER_REFRESH_TOKEN rotated and persisted to %s", env_path)


class _HardDenyError(Exception):
    """cTrader broker hard-rejected the refresh token. Manual OAuth re-run
    required. No amount of retry will recover. Caller should alert user and
    sys.exit(2) — never enter PA-restart crash-loop."""


class _TransientRefreshError(Exception):
    """Network blip, broker 5xx, or other recoverable error. Caller should
    sleep and retry up to REFRESH_MAX_RETRIES."""


def _do_refresh(cfg: Config) -> str:
    """Single refresh attempt. Returns access_token on success. Raises
    _HardDenyError on broker rejection or _TransientRefreshError otherwise.
    Persists the rotated refresh_token on success."""
    try:
        r = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": cfg.ctrader_refresh_token,
                "client_id": cfg.ctrader_client_id,
                "client_secret": cfg.ctrader_client_secret,
            },
            timeout=20,
        )
    except requests.RequestException as e:
        raise _TransientRefreshError(f"network error: {e}") from e

    body: dict = {}
    try:
        body = r.json()
    except Exception:
        pass
    err = body.get("errorCode") or body.get("error")
    if err and any(token in str(err) for token in HARD_DENY_TOKENS):
        raise _HardDenyError(f"broker rejected refresh token: {err} body={body}")

    if r.status_code >= 500:
        raise _TransientRefreshError(f"broker 5xx: {r.status_code} body={body}")
    if not r.ok:
        # 4xx without a known hard-deny code -> treat as transient (broker
        # may recover). Conservative: never crash-loop on unknown 4xx.
        raise _TransientRefreshError(f"broker {r.status_code}: {body}")

    access = body.get("accessToken") or body.get("access_token")
    if not access:
        raise _TransientRefreshError(f"refresh response missing accessToken: {body}")

    new_refresh = body.get("refreshToken") or body.get("refresh_token")
    if new_refresh and new_refresh != cfg.ctrader_refresh_token:
        _persist_refresh_token(Path(".env"), new_refresh)
    return access


def _send_token_death_alert(cfg: Config, reason: str) -> None:
    """Send a single Telegram alert via the existing Telethon user session
    notifying that the cTrader refresh token has been hard-denied. Best
    effort: any failure here is swallowed since the process is about to
    exit anyway. The full bot has not started yet at this point so we
    connect a one-shot Telethon client directly to the existing session
    file at cfg.tg_session_path."""
    try:
        from telethon import TelegramClient  # type: ignore
    except Exception as e:
        log.warning("token-death alert skipped (telethon import failed): %s", e)
        return

    msg = (
        f"🚨 ALERT: tsg — cTrader refresh-token denied.\n"
        f"Reason: {reason}\n"
        f"Action: ssh PA -> cd ~/tsg -> source .venv/bin/activate -> "
        f"python scripts/ctrader_oauth.py -> paste new CTRADER_REFRESH_TOKEN "
        f"into .env -> restart always-on task.\n"
        f"Timestamp: {datetime.now(timezone.utc).isoformat()}"
    )

    async def _send() -> None:
        client = TelegramClient(
            str(cfg.tg_session_path), cfg.tg_api_id, cfg.tg_api_hash,
        )
        try:
            await client.connect()
            if not await client.is_user_authorized():
                log.warning("token-death alert: Telethon session not authorised")
                return
            for ch in cfg.tg_channel_ids:
                try:
                    await client.send_message(ch, msg)
                except Exception as e:
                    log.warning("token-death alert send to %s failed: %s", ch, e)
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

    # Run on an isolated thread + fresh event loop so we don't conflict with
    # any parent asyncio.run() that may already be on the call stack (e.g.
    # when _exchange_refresh_token is invoked from inside amain()).
    def _runner() -> None:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_send())
        finally:
            try:
                loop.close()
            except Exception:
                pass

    try:
        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join(timeout=15)
        if t.is_alive():
            log.warning("token-death Telegram alert thread timed out after 15s")
        else:
            log.info("token-death Telegram alert dispatched")
    except Exception as e:
        log.error("token-death Telegram alert failed: %s", e)


def _exchange_refresh_token(cfg: Config) -> str:
    """Trade refresh token for short-lived access token.

    On a single attempt this delegates to _do_refresh. On transient errors
    (network blip, broker 5xx) the loop sleeps REFRESH_BACKOFF_SECONDS and
    retries up to REFRESH_MAX_RETRIES times. On a hard broker deny
    (invalid_grant / invalid_token / ACCESS_DENIED) we send a Telegram alert
    and sys.exit(2) immediately — critical because PA always-on auto-restarts
    the process and naive retries would hammer the cTrader endpoint and
    trigger a 12-hour rate-limit ban on the refresh token.
    """
    last_err: Exception | None = None
    for attempt in range(1, REFRESH_MAX_RETRIES + 1):
        try:
            return _do_refresh(cfg)
        except _HardDenyError as e:
            log.error("cTrader hard-denied refresh token: %s", e)
            log.error("Manual recovery: python scripts/ctrader_oauth.py")
            _send_token_death_alert(cfg, reason=str(e))
            sys.exit(2)
        except _TransientRefreshError as e:
            last_err = e
            if attempt < REFRESH_MAX_RETRIES:
                log.warning(
                    "refresh attempt %d/%d failed (transient): %s; sleeping %ds",
                    attempt, REFRESH_MAX_RETRIES, e, REFRESH_BACKOFF_SECONDS,
                )
                time.sleep(REFRESH_BACKOFF_SECONDS)
            else:
                log.error(
                    "refresh attempt %d/%d failed (transient): %s; giving up",
                    attempt, REFRESH_MAX_RETRIES, e,
                )

    log.error(
        "cTrader refresh exhausted %d retries: %s",
        REFRESH_MAX_RETRIES, last_err,
    )
    _send_token_death_alert(
        cfg,
        reason=f"exhausted {REFRESH_MAX_RETRIES} retries; last error: {last_err}",
    )
    sys.exit(2)


async def amain() -> None:
    cfg = load_config()
    _setup_logging(cfg.log_level)
    log.info(
        "loaded config: %d pairs, min_rr=%.1f, env=%s, channels=%d, "
        "exec=%s, risk=%.1f%%, daily_kill=%.1fR",
        len(cfg.pairs), cfg.min_rr, cfg.ctrader_env, len(cfg.tg_channel_ids),
        "ON" if cfg.enable_execution else "off",
        cfg.risk_pct * 100, cfg.daily_loss_r_cap,
    )

    if cfg.ctrader_env == "live" and cfg.enable_execution and not cfg.allow_live:
        log.error(
            "REFUSING TO RUN: CTRADER_ENVIRONMENT=live with execution enabled "
            "but TSG_ALLOW_LIVE != yes. Set TSG_ALLOW_LIVE=yes in .env to "
            "explicitly allow live trading, or switch to demo."
        )
        sys.exit(2)

    access_token = _exchange_refresh_token(cfg)
    log.info("cTrader access token obtained")

    store = Store(cfg.db_path)
    feed = CTraderClient(
        host=cfg.ctrader_host,
        port=cfg.ctrader_port,
        client_id=cfg.ctrader_client_id,
        client_secret=cfg.ctrader_client_secret,
        access_token=access_token,
        account_id=cfg.ctrader_account_id,
    )
    feed.start()

    bot = TelegramBroadcaster(
        api_id=cfg.tg_api_id,
        api_hash=cfg.tg_api_hash,
        phone=cfg.tg_phone,
        session_path=cfg.tg_session_path,
        channel_ids=cfg.tg_channel_ids,
    )
    await bot.start()

    chart = ChartImg(
        api_key=cfg.chart_img_key,
        cache_dir=cfg.cache_dir,
        tv_session_id=cfg.tv_session_id,
        tv_session_id_sign=cfg.tv_session_id_sign,
    )

    scanner = Scanner(cfg, store, feed, bot, chart)
    tracker = Tracker(cfg, store, feed, bot, chart)

    try:
        await asyncio.gather(scanner.run_forever(), tracker.run_forever())
    finally:
        feed.stop()
        await bot.stop()


def run() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    run()
