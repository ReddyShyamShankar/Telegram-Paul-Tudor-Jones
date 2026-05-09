"""Swing high/low + key structural levels from OHLC dataframe."""
from __future__ import annotations

import pandas as pd


def swings(df: pd.DataFrame, lookback: int = 3) -> pd.DataFrame:
    """Mark swing highs/lows. A swing high at i = high[i] > high[i-lookback..i+lookback].
    Returns df with bool columns 'sh' (swing high) and 'sl' (swing low).
    """
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    n = len(df)
    sh = [False] * n
    sl = [False] * n
    for i in range(lookback, n - lookback):
        win_h = h[i - lookback : i + lookback + 1]
        win_l = l[i - lookback : i + lookback + 1]
        if h[i] == win_h.max() and (win_h.argmax() == lookback):
            sh[i] = True
        if l[i] == win_l.min() and (win_l.argmin() == lookback):
            sl[i] = True
    out = df.copy()
    out["sh"] = sh
    out["sl"] = sl
    return out


def last_swings(df: pd.DataFrame, n: int = 3, lookback: int = 3) -> tuple[list[float], list[float]]:
    """Return last n swing highs and last n swing lows (chronological order)."""
    s = swings(df, lookback=lookback)
    highs = s.loc[s["sh"], "high"].tail(n).tolist()
    lows = s.loc[s["sl"], "low"].tail(n).tolist()
    return highs, lows


def prior_swing_against(df: pd.DataFrame, entry_price: float, direction: str,
                        lookback: int = 3) -> float | None:
    """Find nearest opposing swing level above (for long) / below (for short) entry.
    Used by the R:R gate to reject if a structural barrier sits between entry and TP.
    """
    s = swings(df, lookback=lookback)
    if direction == "long":
        highs = s.loc[s["sh"] & (s["high"] > entry_price), "high"]
        return float(highs.min()) if not highs.empty else None
    else:
        lows = s.loc[s["sl"] & (s["low"] < entry_price), "low"]
        return float(lows.max()) if not lows.empty else None
