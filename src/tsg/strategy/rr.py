"""R:R gate. Hard-rejects any setup whose realised reward < `min_rr` * risk OR
whose TP path is blocked by an opposing structural level.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .levels import prior_swing_against
from .smc import SMCSetup


@dataclass
class RRResult:
    ok: bool
    reason: str
    entry: float
    stop_loss: float
    take_profit: float
    rr: float


def compute_rr(setup: SMCSetup, df_h1: pd.DataFrame, min_rr: float = 3.0,
               atr_buf: float = 0.5) -> RRResult:
    if setup is None:
        return RRResult(False, "no_setup", 0.0, 0.0, 0.0, 0.0)

    if setup.direction == "long":
        sl = setup.ob_low - atr_buf * setup.atr
        risk = setup.entry - sl
        if risk <= 0:
            return RRResult(False, "zero_or_negative_risk", setup.entry, sl, 0.0, 0.0)
        tp = setup.entry + min_rr * risk
        barrier = prior_swing_against(df_h1, setup.entry, "long")
        if barrier is not None and barrier < tp:
            return RRResult(False, "opposing_barrier_below_tp",
                            setup.entry, sl, tp, min_rr)
        return RRResult(True, "ok", setup.entry, sl, tp, min_rr)

    sl = setup.ob_high + atr_buf * setup.atr
    risk = sl - setup.entry
    if risk <= 0:
        return RRResult(False, "zero_or_negative_risk", setup.entry, sl, 0.0, 0.0)
    tp = setup.entry - min_rr * risk
    barrier = prior_swing_against(df_h1, setup.entry, "short")
    if barrier is not None and barrier > tp:
        return RRResult(False, "opposing_barrier_above_tp",
                        setup.entry, sl, tp, min_rr)
    return RRResult(True, "ok", setup.entry, sl, tp, min_rr)
