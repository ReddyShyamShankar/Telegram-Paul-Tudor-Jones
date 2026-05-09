"""H4 trend bias from market structure (HH/HL or LL/LH)."""
from __future__ import annotations

from typing import Literal

import pandas as pd

from .levels import last_swings


Bias = Literal["bullish", "bearish", "neutral"]


def h4_bias(df_h4: pd.DataFrame, n: int = 3, lookback: int = 5) -> Bias:
    """Identify H4 bias from last n swing highs/lows.
    bullish  = strictly higher highs AND higher lows
    bearish  = strictly lower lows AND lower highs
    else neutral.
    """
    if df_h4 is None or len(df_h4) < (n * lookback * 2):
        return "neutral"
    highs, lows = last_swings(df_h4, n=n, lookback=lookback)
    if len(highs) < n or len(lows) < n:
        return "neutral"

    higher_highs = all(highs[i] > highs[i - 1] for i in range(1, n))
    higher_lows  = all(lows[i]  > lows[i - 1]  for i in range(1, n))
    lower_highs  = all(highs[i] < highs[i - 1] for i in range(1, n))
    lower_lows   = all(lows[i]  < lows[i - 1]  for i in range(1, n))

    if higher_highs and higher_lows:
        return "bullish"
    if lower_lows and lower_highs:
        return "bearish"
    return "neutral"
