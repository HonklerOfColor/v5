"""Querschnitts-Momentum: wöchentlich die stärksten Coins long, die schwächsten short.

Jeden Montag 00:00 UTC (Schluss der letzten 4h-Kerze davor) werden alle
Symbole nach ihrer Rendite über lookback_days sortiert. Die besten top_n werden
long gehalten, die schlechtesten top_n short (market-neutral) oder nur long.
Jede Position bekommt gross / (Zahl der Positionen) des Kapitals als Notional.
Positionen, die im neuen Korb bleiben, werden nicht angefasst; alle anderen
werden per Taker geschlossen bzw. eröffnet. Kein Stop innerhalb der Woche:
das Risiko wird über Streuung und Hebel begrenzt, nicht je Position.
"""

from __future__ import annotations

from dataclasses import dataclass

from gridbot.candles import Candle, aggregate
from gridbot.specs import ContractSpec, floor_to_step
from research.costs import Costs
from research.metrics import Ledger

WEEK_MS = 7 * 86_400_000
MONDAY_OFFSET_MS = 4 * 86_400_000  # Epoche begann an einem Donnerstag


@dataclass(frozen=True)
class MomentumParams:
    name: str = "xs_momentum_28d"
    lookback_days: int = 28
    top_n: int = 3
    long_short: bool = True
    gross: float = 1.0  # Brutto-Exposure als Anteil des Kapitals (1.0 = 100 %)
    rebalance_days: int = 7
    skip_days: int = 0  # jüngste Tage aus dem Lookback ausklammern (0 = aus)


def is_rebalance(ts_ms: int, days: int) -> bool:
    if days == 7:
        return (ts_ms - MONDAY_OFFSET_MS) % WEEK_MS == 0
    return ts_ms % (days * 86_400_000) == 0


def run_momentum(
    candles_by_symbol: dict[str, list[Candle]],
    specs: dict[str, ContractSpec],
    p: MomentumParams,
    costs: Costs,
    equity0: float,
    leverage: int = 2,
    start_ts: int = 0,
) -> dict:
    symbols = list(candles_by_symbol)
    bars = {s: aggregate(candles_by_symbol[s], 4) for s in symbols}
    index = {s: {b.ts: i for i, b in enumerate(bars[s])} for s in symbols}
    stamps = sorted(set().union(*(index[s].keys() for s in symbols)))
    look = p.lookback_days * 6
    skip = p.skip_days * 6
    ledger = Ledger(equity0)
    positions: dict[str, dict] = {}
    per_symbol = {s: 0.0 for s in symbols}
    rebalances = 0

    def close_position(symbol: str, price: float, reason: str) -> None:
        pos = positions.pop(symbol)
        fill = costs.taker_sell(price) if pos["side"] == "long" else costs.taker_buy(price)
        pnl = (fill - pos["entry"]) * pos["qty"] if pos["side"] == "long" else (pos["entry"] - fill) * pos["qty"]
        fee = fill * pos["qty"] * costs.taker_fee
        ledger.fee(fee, True)
        ledger.realized += pnl
        ledger.equity += pnl - fee
        net = pnl - fee - pos["entry_fee"] - pos["funding"]
        per_symbol[symbol] += net
        ledger.close_trade(net, reason)

    def open_position(symbol: str, side: str, price: float, notional: float) -> None:
        spec = specs[symbol]
        qty = floor_to_step(notional / price, spec.qty_step)
        if qty < spec.min_qty or qty * price + 1e-9 < spec.min_notional:
            ledger.exits["zu_klein"] = ledger.exits.get("zu_klein", 0) + 1
            return
        fill = costs.taker_buy(price) if side == "long" else costs.taker_sell(price)
        fee = fill * qty * costs.taker_fee
        ledger.fee(fee, True)
        ledger.equity -= fee
        positions[symbol] = {"side": side, "qty": qty, "entry": fill, "entry_fee": fee, "funding": 0.0}

    for ts in stamps:
        ledger.bars += 1
        if positions:
            ledger.bars_in_market += 1
        for symbol in list(positions):
            i = index[symbol].get(ts)
            if i is None:
                continue
            bar = bars[symbol][i]
            pos = positions[symbol]
            charge = costs.funding_charge(symbol, ts, pos["side"], pos["qty"] * bar.close)
            if charge:
                ledger.funding += charge
                ledger.equity -= charge
                pos["funding"] += charge
        if ts >= start_ts and is_rebalance(ts, p.rebalance_days):
            scores = []
            for symbol in symbols:
                i = index[symbol].get(ts)
                if i is None or i < look:
                    continue
                now = bars[symbol][i - skip].close if skip else bars[symbol][i].close
                then = bars[symbol][i - look].close
                if then > 0:
                    scores.append((now / then - 1.0, symbol))
            if len(scores) >= 2 * p.top_n:
                scores.sort(reverse=True)
                want = {s: "long" for _, s in scores[: p.top_n]}
                if p.long_short:
                    want.update({s: "short" for _, s in scores[-p.top_n:]})
                for symbol in list(positions):
                    if want.get(symbol) != positions[symbol]["side"]:
                        close_position(symbol, bars[symbol][index[symbol][ts]].close, "rebalance")
                per_position = ledger.equity * p.gross / len(want)
                margin_cap = ledger.equity * 0.5 * leverage / len(want)
                for symbol, side in want.items():
                    if symbol in positions:
                        continue
                    open_position(symbol, side, bars[symbol][index[symbol][ts]].close, min(per_position, margin_cap))
                rebalances += 1
        unreal = 0.0
        for symbol, pos in positions.items():
            i = index[symbol].get(ts)
            if i is None:
                continue
            close = bars[symbol][i].close
            unreal += (close - pos["entry"]) * pos["qty"] if pos["side"] == "long" else (pos["entry"] - close) * pos["qty"]
        ledger.mark(ledger.equity + unreal)

    for symbol in list(positions):
        close_position(symbol, bars[symbol][-1].close, "ende")
    ledger.mark(ledger.equity)
    return ledger.result({"strategy": p.name, "per_symbol": per_symbol, "rebalances": rebalances})
