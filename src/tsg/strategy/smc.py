"""SMC setup detection: liquidity sweep + BOS/CHoCH + order block / FVG entry zone.

Conservative codification of the discretionary playbook:
- For a long, on the most recent closed H1 bar, look back N bars and require:
  1) a *sweep* of the prior swing low (a wick that pierces but the candle closes back inside),
  2) a subsequent *BOS* — close above the prior swing high formed before the sweep,
  3) the *order block* = the last bearish candle before the impulse leg.
  Entry = OB midpoint. SL placed beyond OB extreme (+ 0.5×ATR buffer) by the rr module.
- Mirror logic for shorts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from .levels import swings


@dataclass
class SMCSetup:
    direction: str
    entry: float
    ob_low: float
    ob_high: float
    atr: float
    entry_time: datetime
    sweep_level: float
    bos_level: float


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    h = df["high"]
    l = df["low"]
    c = df["close"].shift(1)
    tr = pd.concat([(h - l), (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def find_smc_setup(df_h1: pd.DataFrame, bias: str,
                   lookback: int = 30, swing_lb: int = 3) -> Optional[SMCSetup]:
    """Return SMCSetup on the latest closed bar, or None."""
    if bias == "neutral" or df_h1 is None or len(df_h1) < lookback + swing_lb * 2 + 2:
        return None

    s = swings(df_h1, lookback=swing_lb)
    last_time: datetime = s.index[-1].to_pydatetime()
    atr = _atr(df_h1)
    if not np.isfinite(atr) or atr <= 0:
        return None

    if bias == "bullish":
        sw_lows = s.loc[s["sl"]].tail(2)
        sw_highs = s.loc[s["sh"]].tail(2)
        if sw_lows.empty or sw_highs.empty:
            return None
        sweep_lvl = float(sw_lows["low"].iloc[-1])
        bos_lvl   = float(sw_highs["high"].iloc[-1])

        recent = df_h1.tail(lookback)
        swept = (recent["low"] < sweep_lvl) & (recent["close"] > sweep_lvl)
        if not swept.any():
            return None
        sweep_idx = recent[swept].index[-1]

        post = df_h1.loc[sweep_idx:]
        if len(post) < 2:
            return None
        bos = (post["close"] > bos_lvl)
        if not bos.any():
            return None
        bos_idx = post[bos].index[0]

        seg = df_h1.loc[sweep_idx:bos_idx]
        red = seg[seg["close"] < seg["open"]]
        if red.empty:
            return None
        ob = red.iloc[-1]
        ob_low = float(ob["low"])
        ob_high = float(ob["high"])
        entry = (ob_low + ob_high) / 2.0

        if bos_idx != df_h1.index[-1] and (df_h1.index[-1] - bos_idx).total_seconds() > 6 * 3600:
            return None
        return SMCSetup("long", entry, ob_low, ob_high, atr, last_time, sweep_lvl, bos_lvl)

    if bias == "bearish":
        sw_highs = s.loc[s["sh"]].tail(2)
        sw_lows  = s.loc[s["sl"]].tail(2)
        if sw_highs.empty or sw_lows.empty:
            return None
        sweep_lvl = float(sw_highs["high"].iloc[-1])
        bos_lvl   = float(sw_lows["low"].iloc[-1])

        recent = df_h1.tail(lookback)
        swept = (recent["high"] > sweep_lvl) & (recent["close"] < sweep_lvl)
        if not swept.any():
            return None
        sweep_idx = recent[swept].index[-1]

        post = df_h1.loc[sweep_idx:]
        if len(post) < 2:
            return None
        bos = (post["close"] < bos_lvl)
        if not bos.any():
            return None
        bos_idx = post[bos].index[0]

        seg = df_h1.loc[sweep_idx:bos_idx]
        green = seg[seg["close"] > seg["open"]]
        if green.empty:
            return None
        ob = green.iloc[-1]
        ob_low = float(ob["low"])
        ob_high = float(ob["high"])
        entry = (ob_low + ob_high) / 2.0

        if bos_idx != df_h1.index[-1] and (df_h1.index[-1] - bos_idx).total_seconds() > 6 * 3600:
            return None
        return SMCSetup("short", entry, ob_low, ob_high, atr, last_time, sweep_lvl, bos_lvl)

    return None
