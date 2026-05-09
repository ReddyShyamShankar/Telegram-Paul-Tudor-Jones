from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True)
class Pair:
    instrument: str
    pip: float


@dataclass(frozen=True)
class Config:
    # cTrader
    ctrader_client_id: str
    ctrader_client_secret: str
    ctrader_refresh_token: str
    ctrader_account_id: int
    ctrader_env: str          # demo | live
    ctrader_host: str
    ctrader_port: int

    # Telegram User API (Telethon)
    tg_api_id: int
    tg_api_hash: str
    tg_phone: str
    tg_session_path: Path
    tg_channel_ids: tuple[int, ...]

    # chart-img
    chart_img_key: str

    # local
    db_path: Path
    cache_dir: Path
    log_level: str

    # tunables
    tracker_interval_seconds: int
    max_concurrent: int
    min_rr: float
    pairs: tuple[Pair, ...]

    # execution layer
    enable_execution: bool
    risk_pct: float
    daily_loss_r_cap: float
    allow_live: bool
    execution_max_lots: float


def _require(env: str) -> str:
    val = os.environ.get(env, "")
    if not val:
        raise RuntimeError(f"missing env var: {env}")
    return val


def _parse_channel_ids(raw: str) -> tuple[int, ...]:
    out: list[int] = []
    for token in raw.split(","):
        t = token.strip()
        if not t:
            continue
        try:
            out.append(int(t))
        except ValueError as e:
            raise RuntimeError(
                f"TG_CHANNEL_IDS contains non-numeric token {t!r}; "
                "use channel IDs like -1001234567890"
            ) from e
    if not out:
        raise RuntimeError("TG_CHANNEL_IDS is empty; need at least one channel")
    return tuple(out)


def load_config(pairs_yaml: str = "config/pairs.yaml") -> Config:
    load_dotenv()
    raw = yaml.safe_load(Path(pairs_yaml).read_text())
    pairs = tuple(Pair(p["instrument"], float(p["pip"])) for p in raw["pairs"])

    db_path = Path(os.environ.get("TSG_DB_PATH", "./data/trades.db"))
    cache_dir = Path(os.environ.get("TSG_CACHE_DIR", "./data/charts"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.get("CTRADER_ENVIRONMENT", "demo")
    host = (
        os.environ.get("CTRADER_HOST_DEMO", "demo.ctraderapi.com")
        if env == "demo"
        else os.environ.get("CTRADER_HOST_LIVE", "live.ctraderapi.com")
    )

    return Config(
        ctrader_client_id=_require("CTRADER_CLIENT_ID"),
        ctrader_client_secret=_require("CTRADER_CLIENT_SECRET"),
        ctrader_refresh_token=_require("CTRADER_REFRESH_TOKEN"),
        ctrader_account_id=int(_require("CTRADER_ACCOUNT_ID")),
        ctrader_env=env,
        ctrader_host=host,
        ctrader_port=int(os.environ.get("CTRADER_PORT", "5035")),

        tg_api_id=int(_require("TG_API_ID")),
        tg_api_hash=_require("TG_API_HASH"),
        tg_phone=_require("TG_PHONE"),
        tg_session_path=Path(os.environ.get("TG_SESSION_PATH", ".tsg.session")),
        tg_channel_ids=_parse_channel_ids(_require("TG_CHANNEL_IDS")),

        chart_img_key=_require("CHART_IMG_API_KEY"),
        db_path=db_path,
        cache_dir=cache_dir,
        log_level=os.environ.get("TSG_LOG_LEVEL", "INFO"),
        tracker_interval_seconds=int(os.environ.get("TSG_TRACKER_INTERVAL_SECONDS", "60")),
        max_concurrent=int(os.environ.get("TSG_MAX_CONCURRENT", "5")),
        min_rr=float(os.environ.get("TSG_MIN_RR", "3.0")),
        pairs=pairs,
        enable_execution=_parse_bool(os.environ.get("TSG_ENABLE_EXECUTION", "no")),
        risk_pct=float(os.environ.get("TSG_RISK_PCT", "0.01")),
        daily_loss_r_cap=float(os.environ.get("TSG_DAILY_LOSS_R_CAP", "3.0")),
        allow_live=_parse_bool(os.environ.get("TSG_ALLOW_LIVE", "no")),
        execution_max_lots=float(os.environ.get("TSG_EXECUTION_MAX_LOTS", "100.0")),
    )


def _parse_bool(s: str) -> bool:
    return str(s).strip().lower() in ("yes", "true", "1", "on")
