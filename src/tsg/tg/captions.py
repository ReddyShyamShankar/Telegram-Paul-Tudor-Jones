"""Caption pools for entry + exit Telegram posts.

Picks one variant per trade deterministically by hashing the entry
timestamp so consecutive signals don't repeat the same closer. No
external services, no LLM calls — pure curated rotation.

The bilingual SMC thesis is composed in `strategy.signal._format_thesis`;
this module only owns the psychology / risk-management paragraph that
follows it (entry side) and the outcome closer (exit side).
"""
from __future__ import annotations

import hashlib
from datetime import datetime


# 18 entry closers. Direct, second person, no dashes, no abbreviations.
# Less polished, less template-y. One person talking to one person.
ENTRY_CLOSERS: tuple[str, ...] = (
    "Risk this at 1% of your account. The same 1% you risked on the last "
    "one. The math works across the curve, not on any single trade.",

    "Sized at 1% of your equity. Whether it hits or misses, the only thing "
    "that matters is that you keep showing up the same way for the next "
    "fifty.",

    "Keep the size small and the conviction high. You don't need this one "
    "to win for the system to work.",

    "Stop is at the broker. Target is at the broker. Walk away from the "
    "screen. The trade resolves on its own.",

    "Don't double the size because this one looks obvious. The obvious "
    "ones are exactly where over leveraged accounts get hurt.",

    "Once you're filled it's a probability event, not a personal one. "
    "Detach from it.",

    "You risk 1R to make 3R. Even if you hit 35% of these, your curve "
    "still climbs. That's the entire game.",

    "Whatever happens on this trade does not decide your month. The next "
    "twenty do.",

    "If this stops out, the framework is still right. If it wins, the "
    "framework is still right. Trust the framework, not the individual "
    "outcome.",

    "Position size is 1% of your account. That's the only number that "
    "needs honoring today. Everything else is noise.",

    "Watch the session open and any scheduled high impact data. Even a "
    "clean setup can get run over by a surprise print.",

    "It's filed. Now you wait. Don't widen the stop, don't move the "
    "target, don't average in. Just observe.",

    "One trade in a thousand. Give it the attention it deserves, which "
    "is minimal.",

    "A stop loss isn't a failure. It's a small tax you pay for the right "
    "to take the next setup. Pay it cleanly.",

    "If you feel the urge to add to this position, that's your cue to "
    "step away from the screen. The size is already decided.",

    "Edge is thin on any single trade. Edge is real across hundreds. "
    "Trust the sample, not this one.",

    "Win rate doesn't need to be high here. It needs to be steady. Stay "
    "steady.",

    "You've taken the trade. The work for today is done. Now let it "
    "play out.",
)


# TP closers. Calm, second person. No dashes.
TP_CLOSERS: tuple[str, ...] = (
    "Clean. Booked at the original target. Same size on the next one, "
    "same rules.",

    "Target hit. Wins don't make you a better trader. Consistency does.",

    "Locked in. The danger right after a green trade is over confidence "
    "on the next. Don't fall for it.",

    "Profit secured at the level you planned. No chasing, no widening. "
    "This is exactly what the framework is supposed to produce.",

    "Took it at the planned level. That feeling of leaving money on the "
    "table is the price of staying mechanical.",

    "Worth noting. This came from the same kind of setup that stopped you "
    "out three trades ago. The system is the system.",

    "Closed at three R. The compounding curve doesn't care which trades "
    "won. It cares that you kept showing up.",

    "Win on the board. Don't celebrate too hard, don't size up the next "
    "one. The plan is the plan.",

    "Target hit. Your risk of ruin moved another notch lower. That's the "
    "only scoreboard worth watching.",
)


# SL closers. Calm, anti revenge, second person. No dashes.
SL_CLOSERS: tuple[str, ...] = (
    "Stopped out at one R. Cost of doing business. Setup was valid, "
    "execution was clean, market disagreed. Move on.",

    "Stop hit. No regret, no rerun. The framework only works if you take "
    "every signal it generates.",

    "Loss is one R. Size was right, stop was right. The only thing wrong "
    "is the outcome, and you don't control that.",

    "Took the loss at the planned level. That is the entire point of "
    "having a stop. The trades that should scare you are the ones with "
    "no defined exit.",

    "Down one R. Don't try to win it back on the next trade. Same size, "
    "same rules, same patience.",

    "Annoying but necessary. The seventy fifth percentile losing streak "
    "in our backtest is seven in a row. You're well within tolerance.",

    "If you feel the urge to revenge trade right now, close the platform "
    "for an hour. The setups will still be there.",

    "Down one R. The strategy never promised a win every time. It "
    "promises that the math works across the curve. Trust the curve.",

    "Stop tagged. A string of losses is a feature of any real edge "
    "system, not a bug. Reset and continue.",
)


def _pick_index(seed: datetime, pool_size: int) -> int:
    """Deterministic, seed-based selection so the same trade always gets
    the same closer (idempotent renders) but consecutive trades almost
    never collide."""
    h = hashlib.sha256(seed.isoformat().encode()).digest()
    return int.from_bytes(h[:4], "big") % pool_size


def entry_closer(entry_time: datetime) -> str:
    """Pick one psychology/risk paragraph for the entry post."""
    return ENTRY_CLOSERS[_pick_index(entry_time, len(ENTRY_CLOSERS))]


def tp_closer(entry_time: datetime) -> str:
    return TP_CLOSERS[_pick_index(entry_time, len(TP_CLOSERS))]


def sl_closer(entry_time: datetime) -> str:
    return SL_CLOSERS[_pick_index(entry_time, len(SL_CLOSERS))]
