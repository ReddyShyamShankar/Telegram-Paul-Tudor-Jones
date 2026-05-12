"""Tests for the cTrader refresh-token exchange path in main.py.

Critical invariants under test:

- Hard-deny errors from the broker (ACCESS_DENIED, invalid_grant,
  invalid_token, INVALID_REFRESH_TOKEN) must NOT be retried. They must
  trigger a single Telegram alert and a clean sys.exit(2). This prevents
  PA always-on from crash-looping the refresh endpoint and triggering a
  12-hour rate-limit ban on the refresh token.
- Transient errors (network blip, broker 5xx, missing accessToken) MUST
  be retried up to REFRESH_MAX_RETRIES with REFRESH_BACKOFF_SECONDS sleep
  between attempts.
- Rotated refresh tokens MUST be persisted atomically to .env.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import requests

from tsg import main as main_mod
from tsg.main import (
    _HardDenyError,
    _TransientRefreshError,
    _do_refresh,
    _exchange_refresh_token,
    _persist_refresh_token,
)


def _build_cfg(tmp_path: Path, refresh_token: str = "old-refresh"):
    from tsg.config import Config, Pair
    return Config(
        ctrader_client_id="cid",
        ctrader_client_secret="csecret",
        ctrader_refresh_token=refresh_token,
        ctrader_account_id=12345678,
        ctrader_env="demo",
        ctrader_host="demo.ctraderapi.com",
        ctrader_port=5035,
        tg_api_id=1,
        tg_api_hash="x",
        tg_phone="+15551234567",
        tg_session_path=tmp_path / ".tsg.session",
        tg_channel_ids=(-1001234567890,),
        chart_img_key="x",
        db_path=tmp_path / "trades.db",
        cache_dir=tmp_path / "charts",
        log_level="WARNING",
        tracker_interval_seconds=60,
        max_concurrent=5,
        min_rr=3.0,
        pairs=(Pair("EUR_USD", 0.0001),),
        enable_execution=False,
        risk_pct=0.01,
        daily_loss_r_cap=3.0,
        allow_live=False,
        execution_max_lots=100.0,
    )


class _FakeResponse:
    def __init__(self, status_code: int, json_body: dict | None = None) -> None:
        self.status_code = status_code
        self._json = json_body or {}
        self.ok = 200 <= status_code < 400

    def json(self):
        return self._json


# ---- _do_refresh ------------------------------------------------------------

def test_do_refresh_returns_access_on_200(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("CTRADER_REFRESH_TOKEN=old-refresh\n")
    monkeypatch.setattr(
        main_mod.requests, "post",
        lambda *a, **k: _FakeResponse(200, {"accessToken": "fresh-access",
                                             "refreshToken": "new-refresh"}),
    )
    assert _do_refresh(cfg) == "fresh-access"
    assert "CTRADER_REFRESH_TOKEN=new-refresh" in (tmp_path / ".env").read_text()


def test_do_refresh_hard_deny_access_denied(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path)
    monkeypatch.setattr(
        main_mod.requests, "post",
        lambda *a, **k: _FakeResponse(401, {"errorCode": "ACCESS_DENIED"}),
    )
    with pytest.raises(_HardDenyError):
        _do_refresh(cfg)


def test_do_refresh_hard_deny_invalid_grant(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path)
    monkeypatch.setattr(
        main_mod.requests, "post",
        lambda *a, **k: _FakeResponse(400, {"error": "invalid_grant"}),
    )
    with pytest.raises(_HardDenyError):
        _do_refresh(cfg)


def test_do_refresh_transient_on_network_error(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path)

    def boom(*a, **k):
        raise requests.ConnectionError("dns")

    monkeypatch.setattr(main_mod.requests, "post", boom)
    with pytest.raises(_TransientRefreshError):
        _do_refresh(cfg)


def test_do_refresh_transient_on_5xx(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path)
    monkeypatch.setattr(
        main_mod.requests, "post",
        lambda *a, **k: _FakeResponse(503, {"error": "unavailable"}),
    )
    with pytest.raises(_TransientRefreshError):
        _do_refresh(cfg)


def test_do_refresh_transient_on_unknown_4xx(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path)
    monkeypatch.setattr(
        main_mod.requests, "post",
        lambda *a, **k: _FakeResponse(429, {"error": "too_many_requests"}),
    )
    with pytest.raises(_TransientRefreshError):
        _do_refresh(cfg)


def test_do_refresh_transient_on_missing_access_token(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path)
    monkeypatch.setattr(
        main_mod.requests, "post",
        lambda *a, **k: _FakeResponse(200, {"refreshToken": "x"}),
    )
    with pytest.raises(_TransientRefreshError):
        _do_refresh(cfg)


# ---- _exchange_refresh_token -----------------------------------------------

def test_exchange_hard_deny_exits_immediately(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path)
    call_count = {"n": 0}

    def fake_do_refresh(_cfg):
        call_count["n"] += 1
        raise _HardDenyError("ACCESS_DENIED")

    monkeypatch.setattr(main_mod, "_do_refresh", fake_do_refresh)
    monkeypatch.setattr(main_mod, "_send_token_death_alert", lambda *a, **k: None)

    with pytest.raises(SystemExit) as exc_info:
        _exchange_refresh_token(cfg)
    assert exc_info.value.code == 2
    assert call_count["n"] == 1


def test_exchange_transient_retries_then_succeeds(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path)
    sequence = iter([
        _TransientRefreshError("network"),
        _TransientRefreshError("503"),
        "good-access-token",
    ])

    def fake_do_refresh(_cfg):
        result = next(sequence)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(main_mod, "_do_refresh", fake_do_refresh)
    sleeps: list[float] = []
    monkeypatch.setattr(main_mod.time, "sleep", lambda s: sleeps.append(s))

    assert _exchange_refresh_token(cfg) == "good-access-token"
    assert sleeps == [main_mod.REFRESH_BACKOFF_SECONDS,
                      main_mod.REFRESH_BACKOFF_SECONDS]


def test_exchange_transient_exhausts_then_exits(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path)
    monkeypatch.setattr(
        main_mod, "_do_refresh",
        lambda _cfg: (_ for _ in ()).throw(_TransientRefreshError("network down")),
    )
    monkeypatch.setattr(main_mod.time, "sleep", lambda s: None)
    alerted = {"called": False}
    monkeypatch.setattr(
        main_mod, "_send_token_death_alert",
        lambda _cfg, reason: alerted.update(called=True, reason=reason),
    )

    with pytest.raises(SystemExit) as exc_info:
        _exchange_refresh_token(cfg)
    assert exc_info.value.code == 2
    assert alerted["called"]
    assert "exhausted" in alerted["reason"]


def test_exchange_hard_deny_sends_alert(tmp_path, monkeypatch):
    cfg = _build_cfg(tmp_path)
    monkeypatch.setattr(
        main_mod, "_do_refresh",
        lambda _cfg: (_ for _ in ()).throw(_HardDenyError("ACCESS_DENIED bad cred")),
    )
    captured: dict = {}
    monkeypatch.setattr(
        main_mod, "_send_token_death_alert",
        lambda _cfg, reason: captured.update(reason=reason),
    )
    with pytest.raises(SystemExit):
        _exchange_refresh_token(cfg)
    assert "ACCESS_DENIED" in captured["reason"]


# ---- _persist_refresh_token -------------------------------------------------

def test_persist_replaces_existing_line(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FOO=bar\nCTRADER_REFRESH_TOKEN=old-value\nBAZ=qux\n")
    _persist_refresh_token(env, "new-value")
    text = env.read_text()
    assert "CTRADER_REFRESH_TOKEN=new-value" in text
    assert "CTRADER_REFRESH_TOKEN=old-value" not in text
    assert "FOO=bar" in text and "BAZ=qux" in text


def test_persist_appends_when_key_missing(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FOO=bar\n")
    _persist_refresh_token(env, "new-value")
    assert "CTRADER_REFRESH_TOKEN=new-value" in env.read_text()


def test_persist_silent_when_env_missing(tmp_path):
    env = tmp_path / ".env"
    _persist_refresh_token(env, "new-value")  # must not raise
