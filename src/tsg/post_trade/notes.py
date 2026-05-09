"""Rule-based post-trade note. Looks at how the price moved during the trade
(max favourable / max adverse excursion) and picks a one-liner.
"""
from __future__ import annotations

from ..store.db import TradeRow


def _excursion_fractions(trade: TradeRow) -> tuple[float, float]:
    """Return (favourable_frac, adverse_frac) in [0, 1+].
    favourable_frac = how far toward TP the best price went / entry→TP distance.
    adverse_frac    = how far toward SL the worst price went / entry→SL distance.
    """
    if trade.direction == "long":
        tp_dist = trade.take_profit - trade.entry
        sl_dist = trade.entry - trade.stop_loss
        mf = (trade.max_favourable or trade.entry) - trade.entry
        ma = trade.entry - (trade.max_adverse or trade.entry)
    else:
        tp_dist = trade.entry - trade.take_profit
        sl_dist = trade.stop_loss - trade.entry
        mf = trade.entry - (trade.max_adverse or trade.entry)
        ma = (trade.max_favourable or trade.entry) - trade.entry

    fav = max(0.0, mf / tp_dist) if tp_dist > 0 else 0.0
    adv = max(0.0, ma / sl_dist) if sl_dist > 0 else 0.0
    return fav, adv


def generate_note(trade: TradeRow, outcome: str) -> str:
    fav, adv = _excursion_fractions(trade)

    if outcome == "TP":
        if adv < 0.5:
            return "Clean run to target, thesis confirmed."
        return "Volatile path to target — thesis right, timing was tight."
    if outcome == "SL":
        if fav > 0.6:
            return ("Reversal after running in our favour — should have moved "
                    "stop to break-even.")
        if adv < 1.0 and fav < 0.2:
            return "Stopped out fast — setup was invalidated almost immediately."
        return "Stopped out — structure failed to follow through."
    return "Conditions changed pre-resolution; preserving capital."
