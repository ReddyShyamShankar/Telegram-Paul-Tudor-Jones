"""chart-img.com v2 wrapper.

Two endpoints:
  - `/v2/tradingview/advanced-chart`  — render a Long/Short Position drawing
    over a fresh TV chart. Production signal chart calls this 4 times (one
    per timeframe) and Pillow stitches the panes into a 2x2 grid.
  - `/v2/tradingview/layout-chart/<LAYOUT_ID>` — replicate a saved/shared
    TV layout pixel-exact. Used on demand by `scripts/tg_smoke_layout.py`
    for dashboard-style posts; not in the production hot path.

Field names + color format must match the chart-img v2 schema verbatim
(API rejects unknown fields with 422). See plan
`all-wrong-in-chartimg-starry-fiddle.md` for the wrong-vs-correct table.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx
from PIL import Image

from ..strategy.signal import Signal


CHART_IMG_URL = "https://api.chart-img.com/v2/tradingview/advanced-chart"
LAYOUT_CHART_URL = "https://api.chart-img.com/v2/tradingview/layout-chart"

# Fixed TV-layout snapshot helper (ad-hoc only; not used per-signal).
SIGNAL_LAYOUT_ID = "gm7qCQc5"
SIGNAL_CHART_WIDTH = 1600
SIGNAL_CHART_HEIGHT = 900

Status = Literal["OPEN", "CLOSED"]


# Color palette sampled from TV layout `gm7qCQc5` (light theme).
# Probe (data/probe_*.png) confirmed:
#   * `profitZoneColor` / `stopZoneColor` (docs sample) paint at 30% opacity
#     when transparency=70 — too faint, candles dominate.
#   * `profitBackground` / `stopBackground` (validator-message convention)
#     paint solidly; transparency field appears inverted/ignored.
# Solution: bake desired alpha into the rgba string itself (alpha=0.30 ≈
# pale visible fill, matches user's TV reference) and send BOTH key names
# so whichever the API picks renders correctly.
# Probe results (data/probe_*.png):
#   * profit zone: `profitZoneColor` rgba(.., 0.5) paints mint at 50% opacity ✓
#   * stop zone:   `stopZoneColor` is silently ignored (falls back to TV
#     default red). MUST use legacy `stopBackground` key, alpha must be 1
#     (validator rejects fractional). Use lighter base hex to dial visual
#     opacity since transparency field doesn't apply.
_PROFIT_COLOR_RGBA = "rgba(34,197,94,0.5)"   # works on profitZoneColor
_STOP_COLOR_RGBA = "rgba(232,232,232,1)"     # very light gray; needs stopBackground key
_PROFIT_TRANSPARENCY = 0
_STOP_TRANSPARENCY = 0
# Outer rectangle border = thin light-black for visible frame.
# Entry middle horizontal line hidden separately via entryLineWidth=0.
_LINE_COLOR = "rgba(40,40,40,0.4)"

# Candle palette — matches user's TV settings panel exactly:
#   Body  up = light blue, down = mid blue
#   Borders + wicks = mid blue (both directions)
_CANDLE_UP_COLOR    = "rgb(120,165,243)"   # light blue body (bull)
_CANDLE_DOWN_COLOR  = "rgb(82,136,240)"    # mid blue body (bear)
_CANDLE_BORDER_UP   = "rgb(82,136,240)"
_CANDLE_BORDER_DOWN = "rgb(82,136,240)"
_CANDLE_WICK_UP     = "rgb(82,136,240)"
_CANDLE_WICK_DOWN   = "rgb(82,136,240)"

# Volume bars use the same scheme (same colors, lower alpha so they don't
# dominate the lower pane).
_VOLUME_UP_COLOR   = "rgba(120,165,243,0.6)"   # light blue (up bars)
_VOLUME_DOWN_COLOR = "rgba(82,136,240,0.6)"    # mid blue (down bars)


# Production composite layout: 2x2 grid of advanced-chart panes.
# Order matches user's TV-layout convention.
PANE_INTERVALS: tuple[str, str, str, str] = ("1D", "4h", "1h", "15m")
PANE_WIDTH = 800
PANE_HEIGHT = 450
GRID_WIDTH = 2 * PANE_WIDTH       # 1600
GRID_HEIGHT = 2 * PANE_HEIGHT     # 900


def _instrument_to_symbol(pair: str) -> str:
    """EUR_USD -> OANDA:EURUSD"""
    return f"OANDA:{pair.replace('_', '')}"


def _range_for_interval(interval: str) -> str:
    """Pick a chart history window per timeframe. chart-img only accepts a
    fixed set of ranges: {1D, 5D, 1M, 3M, 6M, 1Y, 5Y, ALL}. Per-pane
    defaults give the comfortable zoom the user approved on the 1D pane.
    """
    if interval == "15m":
        return "1D"        # ~96 candles
    if interval == "1h":
        return "5D"        # ~120 candles (no shorter valid option)
    if interval == "4h":
        return "1M"        # ~180 candles
    return "3M"            # 1D and higher; ~65 candles (user-approved)


def build_payload(signal: Signal, *, interval: str | None = None,
                  status: Status = "OPEN",
                  closed_at: datetime | None = None,
                  width: int = PANE_WIDTH,
                  height: int = PANE_HEIGHT) -> dict:
    """Build the chart-img v2 advanced-chart POST body.

    Schema reference: https://doc.chart-img.com/v2/tradingview/advanced-chart
    Long/Short Position drawing input: entryPrice / stopPrice / targetPrice /
    startDatetime (ISO8601). Override keys camelCase. Colors as rgba() strings;
    transparency is a separate 0-100 int (higher = more see-through).

    `interval` controls which timeframe this pane shows (e.g. `15m`, `1h`,
    `4h`, `1D`). If omitted, defaults to the signal's own timeframe.
    """
    if interval is None:
        interval = "1h" if signal.timeframe == "H1" else "4h"
    drawing_name = "Long Position" if signal.direction == "long" else "Short Position"
    return {
        "symbol": _instrument_to_symbol(signal.pair),
        "interval": interval,
        "theme": "light",
        "style": "candle",
        "width": width,
        "height": height,
        # Pan the chart slightly so the latest candle isn't pinned to the
        # right edge. 20 bars = ~3 weeks on 1D, ~3 days on 4H, ~20h on 1H,
        # ~5h on 15m — enough breathing room without pushing the RR
        # drawing off-screen on lower-TF panes.
        "shiftRight": 20,
        "studies": [
            {
                "name": "Volume",
                "override": {
                    "Volume.color.0": _VOLUME_UP_COLOR,
                    "Volume.color.1": _VOLUME_DOWN_COLOR,
                },
            }
        ],
        "range": _range_for_interval(interval),
        "override": {
            "style": {
                "candleStyle.upColor":         _CANDLE_UP_COLOR,
                "candleStyle.downColor":       _CANDLE_DOWN_COLOR,
                "candleStyle.borderUpColor":   _CANDLE_BORDER_UP,
                "candleStyle.borderDownColor": _CANDLE_BORDER_DOWN,
                "candleStyle.wickUpColor":     _CANDLE_WICK_UP,
                "candleStyle.wickDownColor":   _CANDLE_WICK_DOWN,
                "candleStyle.drawWick":   True,
                "candleStyle.drawBody":   True,
                "candleStyle.drawBorder": True,
            },
        },
        "drawings": [
            {
                "name": drawing_name,
                "input": {
                    "entryPrice": signal.entry,
                    "stopPrice": signal.stop_loss,
                    "targetPrice": signal.take_profit,
                    "startDatetime": signal.entry_time.isoformat(),
                },
                "override": {
                    "lineWidth": 1,
                    "lineColor": _LINE_COLOR,
                    # Hide the horizontal entry line at the entry price
                    # (the dotted blue/violet line that crossed the box).
                    "entryLineWidth": 0,
                    "entryLineColor": "rgba(0,0,0,0)",
                    # profit zone: docs-sanctioned `profitZoneColor` accepts
                    # rgba with fractional alpha and paints correctly.
                    "profitZoneColor": _PROFIT_COLOR_RGBA,
                    "profitZoneTransparency": _PROFIT_TRANSPARENCY,
                    # stop zone: legacy `stopBackground` is the canonical key
                    # that actually paints; new `stopZoneColor` is silently
                    # ignored. alpha must be 1 (fractional → 422); use lighter
                    # base hex to control visual opacity.
                    "stopBackground": _STOP_COLOR_RGBA,
                    "stopBackgroundTransparency": _STOP_TRANSPARENCY,
                    # Hide all text overlays (Target / Stop / Open P&L / RR)
                    # — caption already carries those numbers.
                    "showLabel": False,
                    "showStats": False,
                },
            }
        ],
    }


@dataclass
class ChartImg:
    api_key: str
    cache_dir: Path
    timeout: float = 30.0
    # Optional TradingView session cookies — when set, every advanced-chart
    # POST sends them as `tradingview-session-id` / `tradingview-session-id-sign`
    # headers so chart-img loads paid/private TV indicators on user's behalf.
    tv_session_id: str | None = None
    tv_session_id_sign: str | None = None

    def render(self, signal: Signal, status: Status = "OPEN",
               closed_at: datetime | None = None,
               signal_id: int | None = None) -> bytes:
        """Render the production signal chart as a 2x2 multi-timeframe composite.

        Calls `advanced-chart` 4 times (one per pane: 1D / 4h / 1h / 15m) for
        the signal's symbol, each with a Long/Short Position drawing at the
        signal's entry/SL/TP using the locked RR colors. Stitches the four
        PNGs into a single 1600x900 image via Pillow.

        Output ordering on the grid:
            +-------+-------+
            |  1D   |  4H   |
            +-------+-------+
            |  1H   |  15m  |
            +-------+-------+
        """
        headers = {"x-api-key": self.api_key, "content-type": "application/json"}
        if self.tv_session_id:
            headers["tradingview-session-id"] = self.tv_session_id
        if self.tv_session_id_sign:
            headers["tradingview-session-id-sign"] = self.tv_session_id_sign
        panes: list[bytes] = []
        with httpx.Client(timeout=self.timeout) as client:
            for interval in PANE_INTERVALS:
                payload = build_payload(
                    signal, interval=interval, status=status,
                    closed_at=closed_at, width=PANE_WIDTH, height=PANE_HEIGHT,
                )
                r = client.post(CHART_IMG_URL, json=payload, headers=headers)
                r.raise_for_status()
                panes.append(r.content)

        grid = Image.new("RGB", (GRID_WIDTH, GRID_HEIGHT), (255, 255, 255))
        for idx, png in enumerate(panes):
            img = Image.open(io.BytesIO(png)).convert("RGB")
            if img.size != (PANE_WIDTH, PANE_HEIGHT):
                img = img.resize((PANE_WIDTH, PANE_HEIGHT))
            col = idx % 2
            row = idx // 2
            grid.paste(img, (col * PANE_WIDTH, row * PANE_HEIGHT))

        out = io.BytesIO()
        grid.save(out, format="PNG", optimize=True)
        png_bytes = out.getvalue()

        if signal_id is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{signal_id}_{status}.png").write_bytes(png_bytes)
        return png_bytes

    def render_layout(self, layout_id: str, *,
                      symbol: str | None = None,
                      interval: str | None = None,
                      width: int = 1280, height: int = 720,
                      tv_session_id: str | None = None,
                      tv_session_id_sign: str | None = None,
                      timeout: float = 60.0) -> bytes:
        """Render a saved TradingView layout pixel-exact.

        Calls `/v2/tradingview/layout-chart/<LAYOUT_ID>`. The layout MUST
        be shared in TradingView for unauthenticated access; otherwise pass
        `tv_session_id` + `tv_session_id_sign`. Docs require >= 60s timeout
        for complex layouts (multi-pane, custom indicators).
        """
        body: dict = {"width": width, "height": height, "format": "png"}
        if symbol:
            body["symbol"] = symbol
        if interval:
            body["interval"] = interval
        headers = {"x-api-key": self.api_key, "content-type": "application/json"}
        if tv_session_id:
            headers["tradingview-session-id"] = tv_session_id
        if tv_session_id_sign:
            headers["tradingview-session-id-sign"] = tv_session_id_sign
        url = f"{LAYOUT_CHART_URL}/{layout_id}"
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, json=body, headers=headers)
            r.raise_for_status()
            return r.content
