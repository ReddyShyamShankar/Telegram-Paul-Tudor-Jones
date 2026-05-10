"""Render the SMC backtest report as a PNG infographic.

Parses `data/backtest_report.md` (the markdown produced by `backtest.py`)
and emits `data/backtest_stats.png` with: equity curve, R distribution,
per-pair counts, win/loss pie, and a summary metrics panel.
"""
from __future__ import annotations

import math
import re
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

ROOT = Path(__file__).resolve().parents[1]
MD_IN = ROOT / "data" / "backtest_report.md"
PNG_OUT = ROOT / "data" / "backtest_stats.png"


# ---------- parse ----------

ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*([A-Z_]+)\s*\|\s*(long|short)\s*\|\s*"
    r"([0-9T:+\-.]+)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*"
    r"([0-9T:+\-.]+)\s*\|\s*([0-9.]+)\s*\|\s*(tp|sl|timeout)\s*\|\s*"
    r"([+\-][0-9.]+)\s*\|\s*(\d+)\s*\|\s*$"
)


def parse_trades(md_text: str) -> list[dict]:
    trades = []
    for line in md_text.splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        trades.append({
            "n": int(m.group(1)),
            "pair": m.group(2),
            "dir": m.group(3),
            "entry_time": datetime.fromisoformat(m.group(4)),
            "entry": float(m.group(5)),
            "sl": float(m.group(6)),
            "tp": float(m.group(7)),
            "exit_time": datetime.fromisoformat(m.group(8)),
            "exit": float(m.group(9)),
            "reason": m.group(10),
            "r": float(m.group(11)),
            "bars": int(m.group(12)),
        })
    return trades


# ---------- stats ----------

def compute_stats(trades: list[dict]) -> dict:
    rs = [t["r"] for t in trades]
    n = len(rs)
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    win_rate = len(wins) / n if n else 0.0
    avg_r = sum(rs) / n if n else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    if losses:
        pf = sum(wins) / abs(sum(losses))
    else:
        pf = float("inf") if wins else 0.0

    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    equity: list[float] = []
    for r in rs:
        cum += r
        equity.append(cum)
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    max_w = cur_w = 0
    max_l = cur_l = 0
    for r in rs:
        if r > 0:
            cur_w += 1
            cur_l = 0
            max_w = max(max_w, cur_w)
        elif r < 0:
            cur_l += 1
            cur_w = 0
            max_l = max(max_l, cur_l)
        else:
            cur_w = cur_l = 0

    if n > 1:
        mean = sum(rs) / n
        var = sum((r - mean) ** 2 for r in rs) / (n - 1)
        std = math.sqrt(var)
        sharpe = mean / std if std > 0 else 0.0
    else:
        sharpe = 0.0

    return dict(
        n=n,
        wins=len(wins),
        losses=len(losses),
        win_rate=win_rate,
        avg_r=avg_r,
        avg_win=avg_win,
        avg_loss=avg_loss,
        pf=pf,
        total_r=sum(rs),
        max_dd=max_dd,
        max_w=max_w,
        max_l=max_l,
        sharpe=sharpe,
        equity=equity,
        rs=rs,
        first_trade=trades[0]["entry_time"] if trades else None,
        last_trade=trades[-1]["entry_time"] if trades else None,
    )


# ---------- plot ----------

WIN_COLOR = "#108040"
LOSS_COLOR = "#c0282d"
NEUTRAL = "#3a4a6b"
BG = "#fafbfc"


def render_png(trades: list[dict], stats: dict, out_path: Path) -> None:
    fig = plt.figure(figsize=(14, 10), facecolor=BG)
    gs = GridSpec(3, 3, figure=fig, hspace=0.55, wspace=0.32,
                  left=0.06, right=0.97, top=0.92, bottom=0.06)

    fig.suptitle("SMC Signal Backtest — Stats Sheet",
                 fontsize=18, fontweight="bold", color="#1a1a1a", y=0.985)
    fig.text(0.06, 0.95,
             f"Dukascopy H1 BID  ·  {len(trades)} trades  ·  "
             f"{stats['first_trade'].date()} → {stats['last_trade'].date()}  ·  "
             f"21 G7 pairs  ·  min RR 3.0",
             fontsize=10, color="#555")

    # 1) Equity curve (full width)
    ax1 = fig.add_subplot(gs[0, :])
    xs = list(range(1, stats["n"] + 1))
    eq = stats["equity"]
    ax1.plot(xs, eq, color=NEUTRAL, linewidth=2)
    ax1.fill_between(xs, 0, eq, alpha=0.10, color=NEUTRAL)
    ax1.axhline(0, color="#bbb", linewidth=0.8)
    peak_idx = eq.index(max(eq)) + 1
    ax1.scatter([peak_idx], [max(eq)], s=40, color=WIN_COLOR, zorder=5)
    ax1.annotate(f"peak {max(eq):+.1f}R",
                 (peak_idx, max(eq)), xytext=(8, -12),
                 textcoords="offset points", fontsize=9, color=WIN_COLOR)
    ax1.set_title("Cumulative R (equity curve)", fontsize=12, fontweight="bold", loc="left")
    ax1.set_xlabel("trade #")
    ax1.set_ylabel("cumulative R")
    ax1.grid(True, alpha=0.25)

    # 2) R distribution histogram
    ax2 = fig.add_subplot(gs[1, 0])
    rs = stats["rs"]
    bins = [-1.5, -1.0, -0.5, 0, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 8.0]
    colors = [LOSS_COLOR if (b + 0.001) < 0 else WIN_COLOR for b in bins[:-1]]
    _, _, patches = ax2.hist(rs, bins=bins, edgecolor="white", linewidth=0.6)
    for p, c in zip(patches, colors):
        p.set_facecolor(c)
    ax2.axvline(stats["avg_r"], color="#1a1a1a", linestyle="--", linewidth=1.2,
                label=f"avg {stats['avg_r']:+.2f}R")
    ax2.legend(fontsize=9)
    ax2.set_title("Per-trade R distribution", fontsize=12, fontweight="bold", loc="left")
    ax2.set_xlabel("R")
    ax2.set_ylabel("count")
    ax2.grid(True, alpha=0.25, axis="y")

    # 3) Per-pair counts
    ax3 = fig.add_subplot(gs[1, 1:])
    pair_counts: dict[str, int] = {}
    pair_r: dict[str, float] = {}
    for t in trades:
        pair_counts[t["pair"]] = pair_counts.get(t["pair"], 0) + 1
        pair_r[t["pair"]] = pair_r.get(t["pair"], 0.0) + t["r"]
    pairs = sorted(pair_counts.keys(), key=lambda p: -pair_counts[p])
    counts = [pair_counts[p] for p in pairs]
    bar_colors = [WIN_COLOR if pair_r[p] > 0 else LOSS_COLOR for p in pairs]
    bars = ax3.bar(range(len(pairs)), counts, color=bar_colors, edgecolor="white")
    for b, p in zip(bars, pairs):
        ax3.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.05,
                 f"{pair_r[p]:+.1f}", ha="center", va="bottom", fontsize=8,
                 color=("#108040" if pair_r[p] > 0 else "#c0282d"))
    ax3.set_xticks(range(len(pairs)))
    ax3.set_xticklabels(pairs, rotation=45, ha="right", fontsize=8)
    ax3.set_title("Trades per pair (color = pair total-R sign; label = total R)",
                  fontsize=12, fontweight="bold", loc="left")
    ax3.set_ylabel("count")
    ax3.grid(True, alpha=0.25, axis="y")

    # 4) Win/Loss pie
    ax4 = fig.add_subplot(gs[2, 0])
    wl = [stats["wins"], stats["losses"]]
    ax4.pie(wl, labels=[f"Wins\n{stats['wins']}", f"Losses\n{stats['losses']}"],
            colors=[WIN_COLOR, LOSS_COLOR], startangle=90,
            wedgeprops=dict(edgecolor="white", linewidth=2),
            textprops=dict(fontsize=10, color="white", fontweight="bold"))
    ax4.set_title(f"Win rate {stats['win_rate']:.1%}",
                  fontsize=12, fontweight="bold", loc="left")

    # 5) Summary metrics panel
    ax5 = fig.add_subplot(gs[2, 1:])
    ax5.axis("off")
    pf_str = "∞" if stats["pf"] == float("inf") else f"{stats['pf']:.3f}"
    metrics = [
        ("Trades", f"{stats['n']}"),
        ("Win rate", f"{stats['win_rate']:.1%}"),
        ("Total R", f"{stats['total_r']:+.2f}R"),
        ("Expectancy / trade", f"{stats['avg_r']:+.3f}R"),
        ("Avg win", f"{stats['avg_win']:+.3f}R"),
        ("Avg loss", f"{stats['avg_loss']:+.3f}R"),
        ("Profit factor", pf_str),
        ("Max drawdown", f"{stats['max_dd']:.2f}R"),
        ("Max consec wins", f"{stats['max_w']}"),
        ("Max consec losses", f"{stats['max_l']}"),
        ("Sharpe (per-trade)", f"{stats['sharpe']:.3f}"),
        ("Span", f"{stats['first_trade'].date()} → {stats['last_trade'].date()}"),
    ]
    cols = 2
    rows = (len(metrics) + cols - 1) // cols
    for i, (label, value) in enumerate(metrics):
        col = i // rows
        row = i % rows
        x = 0.02 + col * 0.50
        y = 0.92 - row * 0.155
        ax5.text(x, y, label, fontsize=10, color="#666", transform=ax5.transAxes)
        color = "#1a1a1a"
        if "R" in value and value.startswith("+"):
            color = WIN_COLOR
        elif "R" in value and value.startswith("-"):
            color = LOSS_COLOR
        ax5.text(x + 0.21, y, value, fontsize=14, color=color,
                 fontweight="bold", transform=ax5.transAxes,
                 family="monospace")
    ax5.set_title("Summary", fontsize=12, fontweight="bold", loc="left")

    fig.savefig(out_path, dpi=150, facecolor=BG, bbox_inches="tight")
    plt.close(fig)


# ---------- driver ----------

def main() -> int:
    text = MD_IN.read_text()
    trades = parse_trades(text)
    if not trades:
        print(f"no trades parsed from {MD_IN}")
        return 1
    stats = compute_stats(trades)
    render_png(trades, stats, PNG_OUT)
    pf_str = "inf" if stats["pf"] == float("inf") else f"{stats['pf']:.3f}"
    print(f"wrote {PNG_OUT}  ({stats['n']} trades, win {stats['win_rate']:.1%}, "
          f"total {stats['total_r']:+.2f}R, PF {pf_str})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
