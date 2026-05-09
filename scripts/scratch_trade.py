#!/usr/bin/env python3
"""Manually scratch an open trade. Tracker picks up the flag and posts a
SCRATCHED quote-reply on next tick.

Usage:
    python scripts/scratch_trade.py <trade_id>
"""
from __future__ import annotations

import sys

from tsg.config import load_config
from tsg.store.db import Store


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        trade_id = int(sys.argv[1])
    except ValueError:
        print(f"trade_id must be an integer, got {sys.argv[1]!r}", file=sys.stderr)
        return 2

    cfg = load_config()
    store = Store(cfg.db_path)
    row = store.get(trade_id)
    if row is None:
        print(f"trade {trade_id} not found", file=sys.stderr)
        return 1
    if row.status != "OPEN":
        print(f"trade {trade_id} is not OPEN (status={row.status})", file=sys.stderr)
        return 1
    store.flag_scratch(trade_id)
    print(f"trade {trade_id} flagged for scratch; tracker will post on next tick.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
