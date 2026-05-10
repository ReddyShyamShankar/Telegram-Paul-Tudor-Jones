"""Lock the new caption skeleton: no emojis, bold direction, RR int format,
two narrative paragraphs, deterministic closer rotation."""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta

from tsg.strategy.signal import Signal
from tsg.store.db import TradeRow
from tsg.tg.bot import format_signal_caption, format_outcome_caption
from tsg.tg.captions import (
    ENTRY_CLOSERS, TP_CLOSERS, SL_CLOSERS,
    entry_closer, tp_closer, sl_closer,
)


# any unicode pictograph, emoji-presentation, miscellaneous symbol, dingbats
EMOJI_RANGES = re.compile(
    "["
    "\U0001F300-\U0001FAFF"   # extended pictographs / emoji
    "\U00002700-\U000027BF"   # dingbats
    "\U00002600-\U000026FF"   # misc symbols
    "\U0001F000-\U0001F02F"   # mahjong / dominoes
    "]"
)


def _signal(direction: str = "long", pair: str = "EUR_USD",
            entry_time: datetime | None = None) -> Signal:
    return Signal(
        pair=pair, direction=direction,
        entry=1.0850, stop_loss=1.0820, take_profit=1.0940,
        rr=3.0,
        entry_time=entry_time or datetime(2026, 5, 8, 7, 0, 0, tzinfo=timezone.utc),
        thesis="bilingual thesis goes here",
        timeframe="H1",
    )


# ---------- entry caption ----------

def test_entry_caption_no_emojis():
    cap = format_signal_caption(_signal("long"))
    assert not EMOJI_RANGES.search(cap), f"emoji leaked: {cap!r}"


def test_entry_caption_bold_direction_long():
    cap = format_signal_caption(_signal("long"))
    assert cap.startswith("**LONG**")
    assert "**SHORT**" not in cap


def test_entry_caption_bold_direction_short():
    cap = format_signal_caption(_signal("short"))
    assert cap.startswith("**SHORT**")


def test_entry_caption_rr_integer_format():
    """RR=3.0 → '1:3', NOT '1:3.0'."""
    cap = format_signal_caption(_signal("long"))
    assert "RR: 1:3\n" in cap
    assert "1:3.0" not in cap


def test_entry_caption_field_labels():
    cap = format_signal_caption(_signal("long"))
    # the new label set, no pip annotations on the level lines
    assert "Entry: 1.08500" in cap
    assert "Stop Loss: 1.08200" in cap
    assert "Take Profit: 1.09400" in cap


def test_entry_caption_has_thesis_and_closer():
    cap = format_signal_caption(_signal("long"))
    # thesis flows in unchanged, closer is one of the pool
    assert "bilingual thesis goes here" in cap
    assert any(c in cap for c in ENTRY_CLOSERS)


# ---------- outcome caption ----------

def _trade(direction: str = "long") -> TradeRow:
    return TradeRow(
        id=1, pair="EUR_USD", direction=direction,
        entry=1.0850, stop_loss=1.0820, take_profit=1.0940,
        rr=3.0,
        entry_time="2026-05-08T07:00:00+00:00",
        thesis="t", timeframe="H1",
        telegram_msg_id=None, status="closed_tp",
        closed_at="2026-05-08T17:00:00+00:00", pnl_r=3.0,
        max_favourable=None, max_adverse=None, scratch_requested=0, lots=None,
    )


def test_outcome_tp_caption_shape():
    cap = format_outcome_caption(_trade(), "TP", note="reached target.")
    assert cap.startswith("**TP HIT**")
    assert not EMOJI_RANGES.search(cap)
    assert "1:3" in cap
    assert any(c in cap for c in TP_CLOSERS)


def test_outcome_sl_caption_shape():
    cap = format_outcome_caption(_trade(), "SL", note="invalidation.")
    assert cap.startswith("**SL HIT**")
    assert not EMOJI_RANGES.search(cap)
    assert any(c in cap for c in SL_CLOSERS)


# ---------- closer rotation ----------

def test_closer_pool_size():
    assert len(ENTRY_CLOSERS) >= 12
    assert len(TP_CLOSERS) >= 8
    assert len(SL_CLOSERS) >= 8


def test_closer_rotation_deterministic():
    """Same entry_time always picks same closer."""
    t = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert entry_closer(t) == entry_closer(t)
    assert tp_closer(t) == tp_closer(t)
    assert sl_closer(t) == sl_closer(t)


def test_closer_rotation_varies_across_trades():
    """Many distinct timestamps map to most pool indices."""
    base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    seen = {entry_closer(base + timedelta(hours=h)) for h in range(40)}
    # at least half of the pool surfaced across 40 sample timestamps
    assert len(seen) >= len(ENTRY_CLOSERS) // 2


# ---------- regression: no em-dashes, no hyphenated abbreviations ----------

def test_no_em_dashes_in_pools():
    """User explicitly asked for no `—` (em dash) anywhere."""
    for pool_name, pool in (("ENTRY", ENTRY_CLOSERS),
                             ("TP", TP_CLOSERS),
                             ("SL", SL_CLOSERS)):
        for i, line in enumerate(pool):
            assert "—" not in line, f"em-dash in {pool_name}[{i}]: {line!r}"


def test_no_em_dash_in_entry_caption():
    cap = format_signal_caption(_signal("long"))
    assert "—" not in cap


def test_jpy_pair_price_format():
    """JPY pairs render with 2 decimals (155.90), not 5 (155.90000)."""
    sig = Signal(
        pair="USD_JPY", direction="long",
        entry=156.20, stop_loss=155.90, take_profit=157.10,
        rr=3.0,
        entry_time=datetime(2026, 5, 8, 7, 0, 0, tzinfo=timezone.utc),
        thesis="t", timeframe="H1",
    )
    cap = format_signal_caption(sig, pair_pip=0.01)
    assert "Entry: 156.20\n" in cap
    assert "Stop Loss: 155.90\n" in cap
    assert "Take Profit: 157.10\n" in cap
    assert "156.20000" not in cap


def test_non_jpy_pair_price_format():
    """Non-JPY pairs keep 5-decimal precision."""
    cap = format_signal_caption(_signal("long"))
    assert "Entry: 1.08500" in cap


def test_thesis_has_no_parentheses_glosses():
    """User dropped bilingual glosses; thesis should be plain SMC."""
    from tsg.strategy.signal import _format_thesis
    t = _format_thesis("long", "bullish", 1.17380, 1.17460, 0.00040)
    # no parentheticals like `(higher-timeframe uptrend)` or `(stop-hunt …)`
    # only the ATR value's parens stay (numerical, not gloss)
    assert "(higher-timeframe" not in t
    assert "(stop-hunt" not in t
    assert "(institutional" not in t
    assert "(volatility" not in t
    assert "(break-of-structure" not in t
