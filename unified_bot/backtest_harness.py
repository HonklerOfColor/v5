"""Backtests. Die Grid-Engine ist die aus dem alten Bot. V1 nutzt die portierten Regeln."""

from __future__ import annotations

import random

from unified_bot.gridcore.backtest_engine import run_backtest
from unified_bot.gridcore.candles import Candle
from unified_bot.gridcore.params import GridParams
from unified_bot.gridcore.specs import ContractSpec
from unified_bot.strategies.reversal_rules import (
    entry_hour_blocked,
    reversal_long_signal,
    time_stop_due,
)


def chop_candles(n: int = 400, seed: int = 7, start: float = 100.0) -> list[Candle]:
    rng = random.Random(seed)
    price = start
    out = []
    for i in range(n):
        price += rng.uniform(-0.35, 0.35)
        price = min(start * 1.025, max(start * 0.975, price))
        out.append(Candle(i * 3_600_000, price, price + 0.08, price - 0.08, price, 1.0))
    return out


def run_grid_backtest(candles: list[Candle] | None = None, equity: float = 50.0, symbol: str = "ALTUSDT") -> dict:
    """Dieselbe Funktion wie gridbot.backtest_engine.run_backtest."""
    series = candles if candles is not None else chop_candles()
    spec = ContractSpec(symbol, min_qty=0.01, min_notional=5.0, qty_step=0.01, price_tick=0.01, price_place=2, qty_place=2)
    return run_backtest(series, spec, GridParams(), equity)


def run_reversal_replay(candles: list[Candle], equity: float = 200.0, fee_rate: float = 0.0008) -> dict:
    """Regelbasiert: Long-Reversal, 24h-Time-Stop, Wien-Stunden, Fees als Abschlag.

    Das ist nicht das alte Monte-Carlo-Skript. Es prüft die portierten Entscheidungen
    auf einer Kerzenserie, inklusive der Stunden-Sperre.
    """
    position = None
    closed = []
    cash = equity
    for index, candle in enumerate(candles):
        epoch_s = candle.ts / 1000
        if position is not None:
            age_h = (candle.ts - position["opened"]) / 3_600_000
            pnl = (candle.close - position["entry"]) * position["qty"]
            stop = time_stop_due(age_h, pnl, position["qty"], candle.close, 3)
            target = candle.high >= position["tp"]
            stopped = candle.low <= position["sl"]
            if stop or target or stopped:
                if stop:
                    exit_price = candle.close
                    reason = "time_stop"
                elif stopped:
                    exit_price = position["sl"]
                    reason = "sl"
                else:
                    exit_price = position["tp"]
                    reason = "tp"
                gross = (exit_price - position["entry"]) * position["qty"]
                fees = fee_rate * position["qty"] * (position["entry"] + exit_price)
                cash += gross - fees
                closed.append({"reason": reason, "net": gross - fees, "gross": gross, "fees": fees})
                position = None
        if position is None and index >= 2:
            prev, last = candles[index - 1], candle
            if entry_hour_blocked(epoch_s):
                continue
            if not reversal_long_signal(prev.open, prev.close, last.open, last.close):
                continue
            entry = candle.close
            risk = entry * 0.01
            qty = max(0.01, (equity * 0.01) / risk)
            position = {
                "entry": entry,
                "qty": qty,
                "sl": entry - risk,
                "tp": entry + risk * 2.5,
                "opened": candle.ts,
            }
    return {
        "start_equity": equity,
        "end_equity": cash,
        "net": cash - equity,
        "trades": len(closed),
        "closed": closed,
    }
