"""Signal orchestrator: H4 bias → H1 SMC setup → R:R gate → Signal."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..feed.client import CTraderClient
from .bias import h4_bias
from .rr import compute_rr
from .smc import find_smc_setup


@dataclass
class Signal:
    pair: str
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    rr: float
    entry_time: datetime
    thesis: str
    timeframe: str


def _format_thesis(direction: str, bias: str, sweep: float, bos: float,
                   atr: float) -> str:
    if direction == "long":
        return (
            f"H4 bias {bias}. H1 swept prior swing low at {sweep:.5f}, then BOS "
            f"above {bos:.5f}. Entry at OB midpoint with 0.5×ATR ({atr:.5f}) "
            f"buffer below OB low."
        )
    return (
        f"H4 bias {bias}. H1 swept prior swing high at {sweep:.5f}, then BOS "
        f"below {bos:.5f}. Entry at OB midpoint with 0.5×ATR ({atr:.5f}) "
        f"buffer above OB high."
    )


def generate_signal(
    client: CTraderClient,
    pair: str,
    min_rr: float = 3.0,
    timeframe: str = "H1",
) -> Optional[tuple[Signal, str]]:
    """Returns (Signal, 'fired') if a valid signal exists, else (None, reason).
    reason ∈ {'no_bias', 'no_setup', 'rr_reject:<sub>'}
    """
    df_h4 = client.fetch_candles(pair, granularity="H4", count=200)
    if df_h4.empty:
        return (None, "no_setup")
    bias = h4_bias(df_h4)
    if bias == "neutral":
        return (None, "no_bias")

    df_h1 = client.fetch_candles(pair, granularity="H1", count=200)
    if df_h1.empty:
        return (None, "no_setup")
    setup = find_smc_setup(df_h1, bias)
    if setup is None:
        return (None, "no_setup")

    rr = compute_rr(setup, df_h1, min_rr=min_rr)
    if not rr.ok:
        return (None, f"rr_reject:{rr.reason}")

    sig = Signal(
        pair=pair,
        direction=setup.direction,
        entry=rr.entry,
        stop_loss=rr.stop_loss,
        take_profit=rr.take_profit,
        rr=rr.rr,
        entry_time=setup.entry_time,
        thesis=_format_thesis(setup.direction, bias,
                              setup.sweep_level, setup.bos_level, setup.atr),
        timeframe=timeframe,
    )
    return (sig, "fired")
