"""chart-img.com v2 Advanced Chart wrapper.

Posts a `Long Position` or `Short Position` drawing anchored at the entry
candle time so the rendered TradingView chart visually shows the RR box
exactly the way the trader sees it on TradingView.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx

from ..strategy.signal import Signal


CHART_IMG_URL = "https://api.chart-img.com/v2/tradingview/advanced-chart"

Status = Literal["OPEN", "CLOSED"]


def _instrument_to_symbol(pair: str) -> str:
    """EUR_USD -> OANDA:EURUSD"""
    return f"OANDA:{pair.replace('_', '')}"


def build_payload(signal: Signal, status: Status = "OPEN",
                  closed_at: datetime | None = None,
                  width: int = 1280, height: int = 720) -> dict:
    interval = "1h" if signal.timeframe == "H1" else "4h"
    drawing_name = "Long Position" if signal.direction == "long" else "Short Position"
    entry_unix = int(signal.entry_time.timestamp())
    payload = {
        "symbol": _instrument_to_symbol(signal.pair),
        "interval": interval,
        "theme": "dark",
        "width": width,
        "height": height,
        "studies": [{"name": "Volume"}],
        "drawings": [
            {
                "name": drawing_name,
                "input": {
                    "entryPrice": signal.entry,
                    "stopLoss": signal.stop_loss,
                    "profitLevel": signal.take_profit,
                    "time": entry_unix,
                },
                "override": {"linewidth": 2},
            }
        ],
        "range": "5D",
    }
    return payload


@dataclass
class ChartImg:
    api_key: str
    cache_dir: Path
    timeout: float = 20.0

    def render(self, signal: Signal, status: Status = "OPEN",
               closed_at: datetime | None = None,
               signal_id: int | None = None) -> bytes:
        payload = build_payload(signal, status=status, closed_at=closed_at)
        headers = {"x-api-key": self.api_key, "content-type": "application/json"}
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(CHART_IMG_URL, json=payload, headers=headers)
            r.raise_for_status()
            png = r.content
        if signal_id is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{signal_id}_{status}.png").write_bytes(png)
        return png
