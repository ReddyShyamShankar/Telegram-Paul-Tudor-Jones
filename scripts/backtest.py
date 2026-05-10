"""Offline backtest of the SMC signal logic.

Pulls H1 OHLCV from yfinance for each whitelisted pair, replays the live
scanner's SMC pipeline (`h4_bias` -> `find_smc_setup` -> `compute_rr`) on a
sliding 200-bar window, simulates each fired signal forward bar-by-bar to
SL or TP first-touch, and emits a trade-by-trade report (HTML + Markdown)
with summary statistics.

NOT live trading. NOT connected to cTrader, Telegram, or chart-img.
"""
from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

import dukascopy_python as dk
import dukascopy_python.instruments as dk_inst

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tsg.strategy.bias import h4_bias            # noqa: E402
from tsg.strategy.smc import find_smc_setup       # noqa: E402
from tsg.strategy.rr import compute_rr            # noqa: E402


# ---------- config ----------

H1_WINDOW = 200          # matches live scanner CTraderClient.fetch_candles count
H4_WINDOW = 200
MIN_RR = 3.0
MAX_HOLD_BARS = 720      # ~30 days of H1 bars; longer gets dropped
TARGET_TRADES = 100

# Dukascopy H1 fetch range (free, no key). 6+ years gives plenty of room
# for the highly-selective SMC strategy to accumulate 100 signals.
DATA_START = datetime(2018, 1, 1, tzinfo=timezone.utc)
DATA_END = datetime(2026, 5, 9, tzinfo=timezone.utc)

DUKASCOPY_MAJORS = {
    "EUR_USD", "USD_JPY", "USD_CHF", "USD_CAD", "AUD_USD", "NZD_USD", "GBP_USD",
}

OUT_DIR = ROOT / "data"
HTML_OUT = OUT_DIR / "backtest_report.html"
MD_OUT = OUT_DIR / "backtest_report.md"
CACHE_DIR = OUT_DIR / "backtest_cache"


# ---------- data structures ----------

@dataclass
class Trade:
    pair: str
    direction: str
    entry_time: datetime
    entry: float
    stop_loss: float
    take_profit: float
    planned_rr: float
    exit_time: datetime
    exit: float
    exit_reason: str             # "tp" | "sl" | "timeout"
    realized_r: float
    bars_held: int


# ---------- helpers ----------

def _pair_to_duka_const(pair: str) -> str:
    """EUR_USD -> INSTRUMENT_FX_MAJORS_EUR_USD (or CROSSES)."""
    cat = "MAJORS" if pair in DUKASCOPY_MAJORS else "CROSSES"
    return f"INSTRUMENT_FX_{cat}_{pair}"


def _fetch_dukascopy_h1(pair: str) -> pd.DataFrame:
    """Fetch H1 OHLCV from Dukascopy. Caches to parquet on disk."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{pair}_H1_{DATA_START.year}_{DATA_END.year}.parquet"
    if cache_path.exists():
        try:
            df = pd.read_parquet(cache_path)
            df.index = pd.to_datetime(df.index, utc=True)
            return df
        except Exception:
            pass

    const_name = _pair_to_duka_const(pair)
    instrument = getattr(dk_inst, const_name, None)
    if instrument is None:
        raise RuntimeError(f"dukascopy: no constant {const_name} for {pair}")

    df = dk.fetch(
        instrument=instrument,
        interval=dk.INTERVAL_HOUR_1,
        offer_side=dk.OFFER_SIDE_BID,
        start=DATA_START,
        end=DATA_END,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "time"
    keep = ["open", "high", "low", "close", "volume"]
    df = df[[c for c in keep if c in df.columns]]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    try:
        df.to_parquet(cache_path)
    except Exception:
        pass
    return df


def _resample_h4(h1: pd.DataFrame) -> pd.DataFrame:
    """Resample H1 to H4 with proper OHLCV aggregation. Drops partial bar."""
    if h1.empty:
        return h1
    o = h1["open"].resample("4h", label="left", closed="left").first()
    h = h1["high"].resample("4h", label="left", closed="left").max()
    l = h1["low"].resample("4h", label="left", closed="left").min()
    c = h1["close"].resample("4h", label="left", closed="left").last()
    v = (h1["volume"].resample("4h", label="left", closed="left").sum()
         if "volume" in h1.columns else None)
    out = pd.DataFrame({"open": o, "high": h, "low": l, "close": c}).dropna()
    if v is not None:
        out["volume"] = v.reindex(out.index).fillna(0).astype(int)
    return out


def _simulate_exit(
    h1_future: pd.DataFrame,
    direction: str,
    entry: float,
    sl: float,
    tp: float,
    max_bars: int = MAX_HOLD_BARS,
) -> Optional[tuple[datetime, float, str, int]]:
    """Walk forward bar-by-bar; return (exit_time, exit_price, reason, bars).

    Conservative tie-break: if a single bar pierces both SL and TP, treat
    SL as hit first (assumes adverse intra-bar path). Returns None if
    neither level touched within `max_bars`.
    """
    sub = h1_future.iloc[:max_bars]
    for i in range(len(sub)):
        bar = sub.iloc[i]
        hi = float(bar["high"])
        lo = float(bar["low"])
        if direction == "long":
            sl_hit = lo <= sl
            tp_hit = hi >= tp
            if sl_hit and tp_hit:
                return (sub.index[i].to_pydatetime(), sl, "sl", i + 1)
            if sl_hit:
                return (sub.index[i].to_pydatetime(), sl, "sl", i + 1)
            if tp_hit:
                return (sub.index[i].to_pydatetime(), tp, "tp", i + 1)
        else:  # short
            sl_hit = hi >= sl
            tp_hit = lo <= tp
            if sl_hit and tp_hit:
                return (sub.index[i].to_pydatetime(), sl, "sl", i + 1)
            if sl_hit:
                return (sub.index[i].to_pydatetime(), sl, "sl", i + 1)
            if tp_hit:
                return (sub.index[i].to_pydatetime(), tp, "tp", i + 1)
    return None


def _realized_r(direction: str, entry: float, sl: float, exit_px: float) -> float:
    risk = abs(entry - sl)
    if risk <= 0:
        return 0.0
    if direction == "long":
        return (exit_px - entry) / risk
    return (entry - exit_px) / risk


# ---------- pair backtest ----------

def backtest_pair(pair: str, h1_full: pd.DataFrame) -> list[Trade]:
    """Replay live scanner on a single pair's H1 history. Returns trades."""
    if h1_full.empty or len(h1_full) < H1_WINDOW + 4:
        return []

    h4_full = _resample_h4(h1_full)
    if h4_full.empty:
        return []

    trades: list[Trade] = []
    open_until_idx: int = -1   # bar index up to which pair has an open trade

    n = len(h1_full)
    for i in range(H1_WINDOW, n):
        if i <= open_until_idx:
            continue

        h1_win = h1_full.iloc[i - H1_WINDOW:i]
        # H4 window: only bars closed at or before the H1 window's last close
        last_close_t = h1_win.index[-1]
        h4_win = h4_full.loc[h4_full.index <= last_close_t].tail(H4_WINDOW)
        if len(h4_win) < 30 or len(h1_win) < H1_WINDOW:
            continue

        bias = h4_bias(h4_win)
        if bias == "neutral":
            continue
        setup = find_smc_setup(h1_win, bias)
        if setup is None:
            continue
        rr = compute_rr(setup, h1_win, min_rr=MIN_RR)
        if not rr.ok:
            continue

        entry_time = last_close_t.to_pydatetime()
        entry = float(h1_win["close"].iloc[-1])  # market-fill at signal close
        sl = float(rr.stop_loss)
        tp = float(rr.take_profit)

        # sanity: SL/TP must be on correct side of entry
        if setup.direction == "long":
            if not (sl < entry < tp):
                continue
        else:
            if not (tp < entry < sl):
                continue

        future = h1_full.iloc[i:]
        out = _simulate_exit(future, setup.direction, entry, sl, tp)
        if out is None:
            continue
        exit_time, exit_px, reason, bars_held = out
        r = _realized_r(setup.direction, entry, sl, exit_px)

        trades.append(Trade(
            pair=pair,
            direction=setup.direction,
            entry_time=entry_time,
            entry=entry,
            stop_loss=sl,
            take_profit=tp,
            planned_rr=float(rr.rr),
            exit_time=exit_time,
            exit=exit_px,
            exit_reason=reason,
            realized_r=r,
            bars_held=bars_held,
        ))

        try:
            exit_idx = h1_full.index.get_loc(pd.Timestamp(exit_time))
        except KeyError:
            exit_idx = i + bars_held
        open_until_idx = exit_idx

    return trades


# ---------- stats ----------

@dataclass
class Stats:
    n: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float
    avg_r: float
    avg_win_r: float
    avg_loss_r: float
    profit_factor: float
    expectancy_r: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    max_drawdown_r: float
    sharpe_per_trade: float
    total_r: float
    first_trade: str
    last_trade: str


def compute_stats(trades: list[Trade]) -> Stats:
    if not trades:
        return Stats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "-", "-")
    rs = [t.realized_r for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    breakeven = [r for r in rs if r == 0]

    n = len(rs)
    win_rate = len(wins) / n if n else 0.0
    avg_r = sum(rs) / n if n else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    if losses:
        pf = sum(wins) / abs(sum(losses))
    else:
        pf = float("inf") if wins else 0.0

    max_w = cur_w = 0
    max_l = cur_l = 0
    for r in rs:
        if r > 0:
            cur_w += 1; cur_l = 0
            max_w = max(max_w, cur_w)
        elif r < 0:
            cur_l += 1; cur_w = 0
            max_l = max(max_l, cur_l)
        else:
            cur_w = cur_l = 0

    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        dd = peak - cum
        max_dd = max(max_dd, dd)

    if n > 1:
        mean = sum(rs) / n
        var = sum((r - mean) ** 2 for r in rs) / (n - 1)
        std = math.sqrt(var)
        sharpe = mean / std if std > 0 else 0.0
    else:
        sharpe = 0.0

    return Stats(
        n=n,
        wins=len(wins),
        losses=len(losses),
        breakeven=len(breakeven),
        win_rate=win_rate,
        avg_r=avg_r,
        avg_win_r=avg_win,
        avg_loss_r=avg_loss,
        profit_factor=pf,
        expectancy_r=avg_r,
        max_consecutive_wins=max_w,
        max_consecutive_losses=max_l,
        max_drawdown_r=max_dd,
        sharpe_per_trade=sharpe,
        total_r=sum(rs),
        first_trade=trades[0].entry_time.isoformat(),
        last_trade=trades[-1].entry_time.isoformat(),
    )


# ---------- reports ----------

def render_markdown(trades: list[Trade], stats: Stats) -> str:
    lines = []
    lines.append("# SMC Signal Backtest Report")
    lines.append("")
    lines.append(f"- **Generated:** {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- **Data:** Dukascopy H1 BID, {DATA_START.date()} → {DATA_END.date()}")
    lines.append(f"- **Strategy:** H4 bias → H1 SMC sweep+BOS+OB → min RR {MIN_RR}")
    lines.append(f"- **Entry model:** market-fill at signal-bar close (matches live scanner)")
    lines.append(f"- **Exit model:** SL or TP first-touch on subsequent H1 bars; SL-first on same-bar tie")
    lines.append(f"- **Concurrency:** max 1 open trade per pair")
    lines.append(f"- **Max hold:** {MAX_HOLD_BARS} H1 bars (~{MAX_HOLD_BARS/24:.0f} days)")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Trades | {stats.n} |")
    lines.append(f"| Wins / Losses / BE | {stats.wins} / {stats.losses} / {stats.breakeven} |")
    lines.append(f"| Win rate | {stats.win_rate:.1%} |")
    lines.append(f"| Avg R / trade (expectancy) | {stats.expectancy_r:+.3f}R |")
    lines.append(f"| Avg win | {stats.avg_win_r:+.3f}R |")
    lines.append(f"| Avg loss | {stats.avg_loss_r:+.3f}R |")
    pf_str = "∞" if stats.profit_factor == float("inf") else f"{stats.profit_factor:.3f}"
    lines.append(f"| Profit factor | {pf_str} |")
    lines.append(f"| Total R | {stats.total_r:+.2f}R |")
    lines.append(f"| Max drawdown | {stats.max_drawdown_r:.2f}R |")
    lines.append(f"| Max consecutive wins | {stats.max_consecutive_wins} |")
    lines.append(f"| Max consecutive losses | {stats.max_consecutive_losses} |")
    lines.append(f"| Sharpe (per-trade) | {stats.sharpe_per_trade:.3f} |")
    lines.append(f"| First trade | {stats.first_trade} |")
    lines.append(f"| Last trade | {stats.last_trade} |")
    lines.append("")
    lines.append("## Trades")
    lines.append("")
    lines.append("| # | Pair | Dir | Entry time (UTC) | Entry | SL | TP | Exit time (UTC) | Exit | Reason | R | Bars |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, t in enumerate(trades, 1):
        lines.append(
            f"| {i} | {t.pair} | {t.direction} | {t.entry_time.isoformat()} | "
            f"{t.entry:.5f} | {t.stop_loss:.5f} | {t.take_profit:.5f} | "
            f"{t.exit_time.isoformat()} | {t.exit:.5f} | {t.exit_reason} | "
            f"{t.realized_r:+.3f} | {t.bars_held} |"
        )
    return "\n".join(lines) + "\n"


def render_html(trades: list[Trade], stats: Stats) -> str:
    rows = []
    for i, t in enumerate(trades, 1):
        cls = "win" if t.realized_r > 0 else ("loss" if t.realized_r < 0 else "be")
        rows.append(
            f'<tr class="{cls}"><td>{i}</td><td>{t.pair}</td><td>{t.direction}</td>'
            f'<td>{t.entry_time.isoformat()}</td><td>{t.entry:.5f}</td>'
            f'<td>{t.stop_loss:.5f}</td><td>{t.take_profit:.5f}</td>'
            f'<td>{t.exit_time.isoformat()}</td><td>{t.exit:.5f}</td>'
            f'<td>{t.exit_reason}</td><td>{t.realized_r:+.3f}</td>'
            f'<td>{t.bars_held}</td></tr>'
        )

    pf_str = "∞" if stats.profit_factor == float("inf") else f"{stats.profit_factor:.3f}"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>TSG SMC Backtest</title>
<style>
body{{font-family:-apple-system,system-ui,Segoe UI,Roboto,sans-serif;max-width:1200px;margin:2em auto;padding:0 1em;color:#222}}
h1,h2{{border-bottom:1px solid #ddd;padding-bottom:.3em}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border:1px solid #e3e3e3;padding:6px 8px;text-align:right}}
th{{background:#f5f7fa;text-align:center}}
td:nth-child(2),td:nth-child(3),td:nth-child(10){{text-align:center}}
td:nth-child(4),td:nth-child(8){{text-align:left;font-family:Menlo,monospace;font-size:12px}}
tr.win td:nth-child(11){{color:#108040;font-weight:600}}
tr.loss td:nth-child(11){{color:#c0282d;font-weight:600}}
tr.win{{background:#f5fbf6}}
tr.loss{{background:#fdf6f6}}
.summary td{{text-align:left}}
.summary td:nth-child(2){{font-family:Menlo,monospace;text-align:right}}
.note{{color:#666;font-size:13px}}
</style></head><body>
<h1>SMC Signal Backtest Report</h1>
<p class="note">Generated {datetime.now(timezone.utc).isoformat()}. Data: Dukascopy H1 BID, {DATA_START.date()} → {DATA_END.date()}.
Strategy: H4 bias → H1 SMC sweep+BOS+OB, min RR {MIN_RR}.
Entry: market-fill at signal-bar close. Exit: SL or TP first-touch (SL-first on tie).
Max hold {MAX_HOLD_BARS} H1 bars. <strong>No live trading; pure historical replay.</strong></p>

<h2>Summary</h2>
<table class="summary">
<tr><td>Trades</td><td>{stats.n}</td></tr>
<tr><td>Wins / Losses / BE</td><td>{stats.wins} / {stats.losses} / {stats.breakeven}</td></tr>
<tr><td>Win rate</td><td>{stats.win_rate:.1%}</td></tr>
<tr><td>Avg R / trade (expectancy)</td><td>{stats.expectancy_r:+.3f}R</td></tr>
<tr><td>Avg win</td><td>{stats.avg_win_r:+.3f}R</td></tr>
<tr><td>Avg loss</td><td>{stats.avg_loss_r:+.3f}R</td></tr>
<tr><td>Profit factor</td><td>{pf_str}</td></tr>
<tr><td>Total R</td><td>{stats.total_r:+.2f}R</td></tr>
<tr><td>Max drawdown</td><td>{stats.max_drawdown_r:.2f}R</td></tr>
<tr><td>Max consecutive wins</td><td>{stats.max_consecutive_wins}</td></tr>
<tr><td>Max consecutive losses</td><td>{stats.max_consecutive_losses}</td></tr>
<tr><td>Sharpe (per-trade, unitless)</td><td>{stats.sharpe_per_trade:.3f}</td></tr>
<tr><td>First trade entry</td><td>{stats.first_trade}</td></tr>
<tr><td>Last trade entry</td><td>{stats.last_trade}</td></tr>
</table>

<h2>Trades ({stats.n})</h2>
<table>
<thead><tr><th>#</th><th>Pair</th><th>Dir</th><th>Entry time (UTC)</th><th>Entry</th>
<th>SL</th><th>TP</th><th>Exit time (UTC)</th><th>Exit</th><th>Reason</th><th>R</th><th>Bars</th></tr></thead>
<tbody>
{''.join(rows)}
</tbody></table>
</body></html>
"""


# ---------- driver ----------

def load_pairs() -> list[str]:
    data = yaml.safe_load((ROOT / "config" / "pairs.yaml").read_text())
    return [p["instrument"] for p in data["pairs"]]


def main() -> int:
    pairs = load_pairs()
    print(f"[backtest] {len(pairs)} pairs; "
          f"data window {DATA_START.date()} -> {DATA_END.date()} (Dukascopy H1)")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_trades: list[Trade] = []
    per_pair: dict[str, int] = {}

    for pair in pairs:
        t0 = time.time()
        try:
            h1 = _fetch_dukascopy_h1(pair)
        except Exception as e:
            print(f"  {pair}: dukascopy error {e}")
            continue
        if h1.empty:
            print(f"  {pair}: no data")
            continue
        trades = backtest_pair(pair, h1)
        per_pair[pair] = len(trades)
        all_trades.extend(trades)
        print(f"  {pair}: bars={len(h1)} trades={len(trades)} "
              f"({time.time()-t0:.1f}s)")

    all_trades.sort(key=lambda t: t.exit_time)
    if len(all_trades) >= TARGET_TRADES:
        last = all_trades[-TARGET_TRADES:]
    else:
        last = all_trades

    print(f"\n[backtest] total signals fired across all pairs: {len(all_trades)}")
    print(f"[backtest] reporting last {len(last)} trades")
    sorted_counts = dict(sorted(per_pair.items(), key=lambda kv: -kv[1]))
    print(f"[backtest] per-pair counts: {sorted_counts}")

    stats = compute_stats(last)

    md = render_markdown(last, stats)
    html = render_html(last, stats)
    MD_OUT.write_text(md)
    HTML_OUT.write_text(html)
    print(f"\n[backtest] wrote {MD_OUT}")
    print(f"[backtest] wrote {HTML_OUT}")

    print("\n=== SUMMARY ===")
    print(f"Trades            : {stats.n}")
    print(f"Win rate          : {stats.win_rate:.1%}")
    print(f"Total R           : {stats.total_r:+.2f}")
    print(f"Expectancy / trade: {stats.expectancy_r:+.3f}R")
    print(f"Avg win / loss    : {stats.avg_win_r:+.3f}R / {stats.avg_loss_r:+.3f}R")
    pf = "inf" if stats.profit_factor == float("inf") else f"{stats.profit_factor:.3f}"
    print(f"Profit factor     : {pf}")
    print(f"Max drawdown      : {stats.max_drawdown_r:.2f}R")
    print(f"Max win streak    : {stats.max_consecutive_wins}")
    print(f"Max loss streak   : {stats.max_consecutive_losses}")
    print(f"Sharpe (per-trade): {stats.sharpe_per_trade:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
