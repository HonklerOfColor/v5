#!/usr/bin/env python3
"""Einstieg für den Backtest-Harness.

  python backtest.py grid --equity 50
  python backtest.py reversal
"""

from __future__ import annotations

import argparse
import json

from unified_bot.backtest_harness import chop_candles, run_grid_backtest, run_reversal_replay


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtests auf der portierten Engine.")
    parser.add_argument("which", choices=("grid", "reversal"))
    parser.add_argument("--equity", type=float, default=50.0)
    parser.add_argument("--bars", type=int, default=400)
    args = parser.parse_args()
    candles = chop_candles(args.bars)
    if args.which == "grid":
        result = run_grid_backtest(candles, equity=args.equity)
    else:
        result = run_reversal_replay(candles, equity=max(args.equity, 200.0))
        result = {key: value for key, value in result.items() if key != "closed"}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()