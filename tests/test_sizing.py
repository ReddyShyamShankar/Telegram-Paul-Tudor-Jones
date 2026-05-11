"""Position-sizing tests for Conservative profile rules."""
from __future__ import annotations

from tsg.execution.sizing import compute_lots


def test_eur_usd_normal_sizing():
    # 10k equity, 1% risk = $100. SL 30 pips on EUR/USD => loss/lot = $300.
    # raw_lots = 100/300 = 0.333, rounded down to 0.33.
    r = compute_lots(
        equity_usd=10_000, risk_pct=0.01,
        entry=1.0850, stop_loss=1.0820, pair="EUR_USD",
        current_price=1.0850,
    )
    assert r.ok
    assert abs(r.lots - 0.33) < 1e-6
    assert r.volume_units == 33


def test_min_lot_floor_when_under_001():
    # tiny equity -> raw_lots < 0.01 -> forced to 0.01 per user rule
    r = compute_lots(
        equity_usd=10, risk_pct=0.01,
        entry=1.0850, stop_loss=1.0820, pair="EUR_USD",
        current_price=1.0850,
    )
    assert r.ok
    assert r.lots == 0.01
    assert r.volume_units == 1


def test_round_down_lots_never_up():
    # 11k equity, 1% = $110, SL 30 pips => raw_lots = 110/300 = 0.3666...
    # must round down to 0.36 not 0.37
    r = compute_lots(
        equity_usd=11_000, risk_pct=0.01,
        entry=1.0850, stop_loss=1.0820, pair="EUR_USD",
        current_price=1.0850,
    )
    assert r.ok
    assert abs(r.lots - 0.36) < 1e-6


def test_usd_jpy_inverse_pricing():
    # USD/JPY: pip = 0.01, USD is base.
    # SL distance = 0.30. Loss/lot = (0.30 * 100000) / 150 = $200/lot
    # 10k * 1% = $100 risk. raw_lots = 100/200 = 0.5
    r = compute_lots(
        equity_usd=10_000, risk_pct=0.01,
        entry=150.00, stop_loss=150.30, pair="USD_JPY",
        current_price=150.00,
    )
    assert r.ok
    assert abs(r.lots - 0.50) < 1e-6


def test_cross_pair_rejects_without_usd_rate():
    """Without a USD/quote conversion rate, cross pairs are unsized."""
    r = compute_lots(
        equity_usd=10_000, risk_pct=0.01,
        entry=1.6500, stop_loss=1.6470, pair="EUR_AUD",
        current_price=1.6500,
    )
    assert not r.ok
    assert r.reason == "cross_pair_unsupported_no_rate"


def test_cross_pair_accepts_with_usd_rate_eur_aud():
    """EUR/AUD with AUD/USD=0.66 conversion. SL distance 0.0030 AUD.
    Loss/lot in AUD = 0.0030 * 100000 = 300 AUD. In USD = 300 * 0.66 = $198.
    10k * 1% = $100 risk. raw_lots = 100/198 = 0.505 -> floor 0.50."""
    r = compute_lots(
        equity_usd=10_000, risk_pct=0.01,
        entry=1.6500, stop_loss=1.6470, pair="EUR_AUD",
        current_price=1.6500,
        usd_per_quote_rate=0.66,
    )
    assert r.ok
    assert abs(r.lots - 0.50) < 1e-6


def test_cross_pair_accepts_with_usd_rate_chf_jpy():
    """CHF/JPY with USD/JPY=150 -> JPY/USD = 1/150. SL distance 0.30 JPY.
    Loss/lot in JPY = 0.30 * 100000 = 30000 JPY. In USD = 30000 / 150 = $200.
    10k * 1% = $100 risk. raw_lots = 100/200 = 0.50."""
    r = compute_lots(
        equity_usd=10_000, risk_pct=0.01,
        entry=201.59, stop_loss=201.29, pair="CHF_JPY",
        current_price=201.59,
        usd_per_quote_rate=1.0 / 150.0,
    )
    assert r.ok
    assert abs(r.lots - 0.50) < 1e-6


def test_explicit_usd_rate_overrides_auto_derivation():
    """If usd_per_quote_rate is passed for a USD-major pair, it overrides
    the auto-derivation. Caller-given rate wins."""
    r = compute_lots(
        equity_usd=10_000, risk_pct=0.01,
        entry=1.0850, stop_loss=1.0820, pair="EUR_USD",
        current_price=1.0850,
        usd_per_quote_rate=2.0,    # pretend each USD == 2.0 USD
    )
    assert r.ok
    # loss_per_lot = 0.0030 * 100000 * 2.0 = 600. raw = 100/600 = 0.166 -> 0.16
    assert abs(r.lots - 0.16) < 1e-6


def test_non_positive_usd_rate_rejects():
    r = compute_lots(
        equity_usd=10_000, risk_pct=0.01,
        entry=1.6500, stop_loss=1.6470, pair="EUR_AUD",
        current_price=1.6500,
        usd_per_quote_rate=0.0,
    )
    assert not r.ok
    assert r.reason == "non_positive_usd_quote_rate"


def test_zero_equity_rejected():
    r = compute_lots(
        equity_usd=0, risk_pct=0.01,
        entry=1.0850, stop_loss=1.0820, pair="EUR_USD",
        current_price=1.0850,
    )
    assert not r.ok


def test_zero_sl_distance_rejected():
    r = compute_lots(
        equity_usd=10_000, risk_pct=0.01,
        entry=1.0850, stop_loss=1.0850, pair="EUR_USD",
        current_price=1.0850,
    )
    assert not r.ok
    assert r.reason == "zero_sl_distance"


def test_sanity_cap_blocks_oversize():
    # Risk 50% of $1M with tiny SL => obviously too many lots
    r = compute_lots(
        equity_usd=1_000_000, risk_pct=0.5,
        entry=1.0850, stop_loss=1.08499, pair="EUR_USD",
        current_price=1.0850,
        max_lots=10.0,
    )
    assert not r.ok
    assert "sanity_cap_exceeded" in r.reason
