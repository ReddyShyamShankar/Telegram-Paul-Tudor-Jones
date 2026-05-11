from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pair TEXT NOT NULL,
  direction TEXT NOT NULL CHECK(direction IN ('long','short')),
  entry REAL NOT NULL,
  stop_loss REAL NOT NULL,
  take_profit REAL NOT NULL,
  rr REAL NOT NULL,
  entry_time TEXT NOT NULL,
  thesis TEXT,
  timeframe TEXT,
  telegram_msg_id INTEGER,
  status TEXT NOT NULL DEFAULT 'OPEN'
    CHECK(status IN ('OPEN','TP','SL','SCRATCHED')),
  closed_at TEXT,
  pnl_r REAL,
  max_favourable REAL,
  max_adverse REAL,
  scratch_requested INTEGER NOT NULL DEFAULT 0,
  lots REAL,
  position_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_pair   ON trades(pair);

CREATE TABLE IF NOT EXISTS scan_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  pair TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  result TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trade_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trade_id INTEGER NOT NULL REFERENCES trades(id),
  channel_id TEXT NOT NULL,
  message_id INTEGER NOT NULL,
  posted_at TEXT NOT NULL,
  UNIQUE(trade_id, channel_id)
);
CREATE INDEX IF NOT EXISTS idx_tm_trade ON trade_messages(trade_id);

CREATE TABLE IF NOT EXISTS ob_signatures (
  pair TEXT PRIMARY KEY,
  sweep_level REAL NOT NULL,
  bos_level REAL NOT NULL,
  ob_low REAL NOT NULL,
  ob_high REAL NOT NULL,
  last_fired_at TEXT NOT NULL
);
"""


@dataclass
class TradeMessage:
    id: int
    trade_id: int
    channel_id: str
    message_id: int
    posted_at: str


@dataclass
class TradeRow:
    id: int
    pair: str
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    rr: float
    entry_time: str
    thesis: str | None
    timeframe: str | None
    telegram_msg_id: int | None
    status: str
    closed_at: str | None
    pnl_r: float | None
    max_favourable: float | None
    max_adverse: float | None
    scratch_requested: int
    lots: float | None = None
    position_id: int | None = None


def init_db(path: Path | str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    try:
        con.executescript(SCHEMA_SQL)
        # Additive migrations for pre-existing trades tables. CREATE TABLE
        # IF NOT EXISTS is a no-op on existing tables so new columns must
        # be added via ALTER. Each statement is idempotent via try/except.
        for col_def in (
            "ALTER TABLE trades ADD COLUMN lots REAL",
            "ALTER TABLE trades ADD COLUMN position_id INTEGER",
        ):
            try:
                con.execute(col_def)
            except sqlite3.OperationalError:
                pass  # column already exists
        con.commit()
    finally:
        con.close()


class Store:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        init_db(self.path)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def insert_trade(self, *, pair: str, direction: str, entry: float,
                     stop_loss: float, take_profit: float, rr: float,
                     entry_time: datetime, thesis: str, timeframe: str) -> int:
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO trades(pair, direction, entry, stop_loss, take_profit, rr,
                                       entry_time, thesis, timeframe)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (pair, direction, entry, stop_loss, take_profit, rr,
                 entry_time.isoformat(), thesis, timeframe),
            )
            return int(cur.lastrowid)

    def set_telegram_msg(self, trade_id: int, msg_id: int) -> None:
        with self._conn() as c:
            c.execute("UPDATE trades SET telegram_msg_id=? WHERE id=?", (msg_id, trade_id))

    def update_extremes(self, trade_id: int, high: float, low: float) -> None:
        with self._conn() as c:
            cur = c.execute(
                "SELECT max_favourable, max_adverse FROM trades WHERE id=?", (trade_id,)
            ).fetchone()
            if not cur:
                return
            mf, ma = cur["max_favourable"], cur["max_adverse"]
            new_mf = high if mf is None else max(mf, high)
            new_ma = low if ma is None else min(ma, low)
            c.execute(
                "UPDATE trades SET max_favourable=?, max_adverse=? WHERE id=?",
                (new_mf, new_ma, trade_id),
            )

    def close_trade(self, trade_id: int, status: str, pnl_r: float,
                    closed_at: datetime) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE trades SET status=?, pnl_r=?, closed_at=? WHERE id=?",
                (status, pnl_r, closed_at.isoformat(), trade_id),
            )

    def update_lots_and_position(self, trade_id: int, lots: float | None,
                                 position_id: int | None) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE trades SET lots=?, position_id=? WHERE id=?",
                (lots, position_id, trade_id),
            )

    def daily_pnl_r(self, start_of_day_utc: datetime) -> float:
        """Sum of R-multiples on trades CLOSED today. Used for kill-switch."""
        with self._conn() as c:
            row = c.execute(
                """SELECT COALESCE(SUM(pnl_r), 0) FROM trades
                   WHERE status IN ('TP','SL','SCRATCHED')
                     AND closed_at IS NOT NULL
                     AND closed_at >= ?""",
                (start_of_day_utc.isoformat(),),
            ).fetchone()
            return float(row[0] or 0.0)

    def flag_scratch(self, trade_id: int) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE trades SET scratch_requested=1 WHERE id=? AND status='OPEN'",
                (trade_id,),
            )

    def log_scan(self, ts: datetime, pair: str, timeframe: str, result: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO scan_runs(ts, pair, timeframe, result) VALUES (?,?,?,?)",
                (ts.isoformat(), pair, timeframe, result),
            )

    def open_trades(self) -> list[TradeRow]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM trades WHERE status='OPEN'").fetchall()
            return [TradeRow(**dict(r)) for r in rows]

    def open_count(self) -> int:
        with self._conn() as c:
            return int(c.execute("SELECT COUNT(*) FROM trades WHERE status='OPEN'").fetchone()[0])

    def has_open_for_pair(self, pair: str) -> bool:
        with self._conn() as c:
            n = c.execute(
                "SELECT COUNT(*) FROM trades WHERE pair=? AND status='OPEN'", (pair,)
            ).fetchone()[0]
            return n > 0

    # ---------- trade_messages (multi-channel broadcast) ----------
    def add_trade_message(self, trade_id: int, channel_id: int | str,
                          message_id: int, posted_at: datetime) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT OR IGNORE INTO trade_messages
                   (trade_id, channel_id, message_id, posted_at)
                   VALUES (?, ?, ?, ?)""",
                (trade_id, str(channel_id), message_id, posted_at.isoformat()),
            )

    def messages_for_trade(self, trade_id: int) -> list[TradeMessage]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM trade_messages WHERE trade_id=? ORDER BY id",
                (trade_id,),
            ).fetchall()
            return [TradeMessage(**dict(r)) for r in rows]

    def get(self, trade_id: int) -> TradeRow | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
            return TradeRow(**dict(r)) if r else None

    # ---------- ob_signatures (same-OB dedup) ----------
    def get_last_ob_signature(self, pair: str) -> tuple[float, float, float, float] | None:
        """Return (sweep_level, bos_level, ob_low, ob_high) of the last fired
        OB on this pair, or None if no OB has ever fired for it."""
        with self._conn() as c:
            r = c.execute(
                "SELECT sweep_level, bos_level, ob_low, ob_high FROM ob_signatures WHERE pair=?",
                (pair,),
            ).fetchone()
            if r is None:
                return None
            return (float(r["sweep_level"]), float(r["bos_level"]),
                    float(r["ob_low"]), float(r["ob_high"]))

    def set_ob_signature(self, pair: str, sweep_level: float, bos_level: float,
                         ob_low: float, ob_high: float, ts: datetime) -> None:
        """Upsert the OB signature for this pair to the latest fired one."""
        with self._conn() as c:
            c.execute(
                """INSERT INTO ob_signatures(pair, sweep_level, bos_level, ob_low, ob_high, last_fired_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(pair) DO UPDATE SET
                     sweep_level=excluded.sweep_level,
                     bos_level=excluded.bos_level,
                     ob_low=excluded.ob_low,
                     ob_high=excluded.ob_high,
                     last_fired_at=excluded.last_fired_at""",
                (pair, sweep_level, bos_level, ob_low, ob_high, ts.isoformat()),
            )
