"""Daemon entry. Wires Config + Store + cTrader feed + Telegram broadcaster +
chart-img and runs Scanner and Tracker concurrently."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
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


def _exchange_refresh_token(cfg: Config) -> str:
    """Trade refresh token for short-lived access token. Persist rotated
    refresh tokens. On invalidation, log recovery command and exit non-zero.
    """
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
    body = {}
    try:
        body = r.json()
    except Exception:
        pass
    err = body.get("errorCode") or body.get("error")
    if err in {"invalid_grant", "invalid_token", "INVALID_REFRESH_TOKEN"}:
        log.error(
            "cTrader refresh token invalid (%s). "
            "Re-run: python scripts/ctrader_oauth.py", err,
        )
        sys.exit(2)
    r.raise_for_status()
    access = body.get("accessToken") or body.get("access_token")
    if not access:
        raise RuntimeError(f"cTrader token refresh failed: {body}")
    new_refresh = body.get("refreshToken") or body.get("refresh_token")
    if new_refresh and new_refresh != cfg.ctrader_refresh_token:
        _persist_refresh_token(Path(".env"), new_refresh)
    return access


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

    chart = ChartImg(cfg.chart_img_key, cfg.cache_dir)

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
