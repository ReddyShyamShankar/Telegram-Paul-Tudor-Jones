"""Position sizing for the cTrader execution layer.

Rules (from user spec, "Conservative" profile):
- Risk = 1% of account equity per trade.
- Round lots DOWN to step 0.01.
- If math gives < 0.01 lots, force 0.01 (i.e. always trade min lot).
- Sanity ceiling at `max_lots` (default 100.0) protects against bug-induced
  over-sizing.
- v1 limitation: USD-major pairs only (base or quote = USD).
  Cross pairs return ok=False — caller should skip execution but still
  fire the Telegram signal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


CONTRACT_SIZE = 100_000.0  # standard FX lot size


@dataclass
class SizingResult:
    ok: bool
    reason: str
    lots: float
    volume_units: int
    loss_per_lot: float

    @classmethod
    def reject(cls, reason: str) -> "SizingResult":
        return cls(False, reason, 0.0, 0, 0.0)


def _round_down_lots(raw_lots: float, step: float = 0.01) -> float:
    """Round DOWN to multiple of `step`. 0.0073 -> 0.00 (then min-floor handles)."""
    return math.floor(raw_lots / step) * step


def compute_lots(
    *,
    equity_usd: float,
    risk_pct: float,
    entry: float,
    stop_loss: float,
    pair: str,
    current_price: float,
    contract_size: float = CONTRACT_SIZE,
    min_lots: float = 0.01,
    max_lots: float = 100.0,
) -> SizingResult:
    """Compute lot size and integer cTrader volume units.

    Assumes account currency is USD.

    For X/USD pair (USD is the quote): pip-distance loss per lot
        loss_per_lot_usd = sl_distance * contract_size

    For USD/X pair (USD is the base): we close at the price-in-X then
    convert back to USD using current_price (the spot mid)
        loss_per_lot_usd = (sl_distance * contract_size) / current_price

    Cross pair (no USD leg): not supported in v1 — needs USD/quote
    conversion rate which is not always sourced from the same OANDA-listed
    spot. Caller should skip execution but still post Telegram signal.
    """
    if equity_usd <= 0:
        return SizingResult.reject("non_positive_equity")
    if risk_pct <= 0 or risk_pct > 0.5:
        return SizingResult.reject("risk_pct_out_of_bounds")
    if entry <= 0 or current_price <= 0:
        return SizingResult.reject("non_positive_price")

    sl_distance = abs(entry - stop_loss)
    if sl_distance == 0:
        return SizingResult.reject("zero_sl_distance")

    parts = pair.split("_")
    if len(parts) != 2:
        return SizingResult.reject("malformed_pair")
    base, quote = parts

    if quote == "USD":
        loss_per_lot = sl_distance * contract_size
    elif base == "USD":
        loss_per_lot = (sl_distance * contract_size) / current_price
    else:
        return SizingResult.reject("cross_pair_unsupported")

    if loss_per_lot <= 0:
        return SizingResult.reject("zero_loss_per_lot")

    risk_usd = equity_usd * risk_pct
    raw_lots = risk_usd / loss_per_lot
    # Round to 6dp first to suppress float artifacts like 0.4999999... that
    # otherwise floor down past the intended lot step.
    raw_lots = round(raw_lots, 6)

    lots = _round_down_lots(raw_lots, step=0.01)
    if lots < min_lots:
        lots = min_lots  # force min lot per user rule
    if lots > max_lots:
        return SizingResult.reject(f"sanity_cap_exceeded:{lots:.2f}>{max_lots}")

    # cTrader Open API volume convention: 1 unit = 0.01 lot, so 100 units = 1 lot.
    volume_units = int(round(lots * 100))
    return SizingResult(True, "ok", lots, volume_units, loss_per_lot)
