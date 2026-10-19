"""Trendfolge als Portfolio: ein gemeinsames Kapital, mehrere Symbole, höchstens N Positionen.

Dieselbe Logik wie research.trend, aber Kapital und Risiko sind geteilt: jede
Position riskiert risk_pct des aktuellen Gesamtkapitals, die Margin je
Position ist auf max_margin_fraction / max_positions gedeckelt. Signale werden
je 4h-Kerze in der Reihenfolge der Symbol-Liste geprüft; sind alle Plätze
belegt, verfällt das Signal.
"""

from __future__ import annotations

from gridbot.candles import Candle, aggregate
from gridbot.specs import ContractSpec, floor_to_step
from research.costs import Costs
from research.metrics import Ledger
from research.trend import TrendParams, atr_series, sma_series


def run_trend_portfolio(
    candles_by_symbol: dict[str, list[Candle]],
    specs: dict[str, ContractSpec],
    p: TrendParams,
    costs: Costs,
    equity0: float,
    leverage: int = 2,
    max_positions: int = 3,
    start_ts: int = 0,
    rank_signals: bool = False,
    shared_margin: bool = False,
) -> dict:
    """rank_signals=True: Signale einer Kerze nach Ausbruchsweite in ATR sortiert, stärkstes zuerst.

    shared_margin=True: statt einer festen Margin-Obergrenze je Platz gilt ein gemeinsames
    Margin-Budget (max_margin_fraction × Kapital × Hebel als Notional) über alle offenen Positionen.
    """
    symbols = list(candles_by_symbol)
    bars = {s: aggregate(candles_by_symbol[s], p.hours) for s in symbols}
    atrs = {s: atr_series(bars[s], p.atr_period) for s in symbols}
    smas = {
        s: (sma_series([b.close for b in bars[s]], p.trend_filter_hours // p.hours) if p.trend_filter_hours else [None] * len(bars[s]))
        for s in symbols
    }
    index = {s: {b.ts: i for i, b in enumerate(bars[s])} for s in symbols}
    stamps = sorted(set().union(*(index[s].keys() for s in symbols)))
    warm = max(p.entry_lookback, p.exit_lookback, p.atr_period) + 1
    ledger = Ledger(equity0)
    positions: dict[str, dict] = {}
    per_symbol: dict[str, float] = {s: 0.0 for s in symbols}

    def close_position(symbol: str, price: float, reason: str) -> None:
        pos = positions.pop(symbol)
        if pos["side"] == "long":
            fill = costs.taker_sell(price)
            pnl = (fill - pos["entry"]) * pos["qty"]
        else:
            fill = costs.taker_buy(price)
            pnl = (pos["entry"] - fill) * pos["qty"]
        fee = fill * pos["qty"] * costs.taker_fee
        ledger.fee(fee, True)
        ledger.realized += pnl
        ledger.equity += pnl - fee
        net = pnl - fee - pos["entry_fee"] - pos["funding"]
        per_symbol[symbol] += net
        ledger.close_trade(net, reason)

    for ts in stamps:
        ledger.bars += 1
        if positions:
            ledger.bars_in_market += 1
        # 1. offene Positionen führen
        for symbol in list(positions):
            i = index[symbol].get(ts)
            if i is None:
                continue
            bar = bars[symbol][i]
            pos = positions[symbol]
            charge = costs.funding_charge(symbol, bar.ts, pos["side"], pos["qty"] * bar.close)
            if charge:
                ledger.funding += charge
                ledger.equity -= charge
                pos["funding"] += charge
            stop = pos["stop"]
            hit = bar.low <= stop if pos["side"] == "long" else bar.high >= stop
            if hit:
                price = min(stop, bar.open) if pos["side"] == "long" else max(stop, bar.open)
                close_position(symbol, price, "stop")
                continue
            pos["bars"] += 1
            atr_now = atrs[symbol][i]
            if atr_now:
                if pos["side"] == "long":
                    pos["stop"] = max(pos["stop"], bar.close - p.atr_stop_mult * atr_now)
                else:
                    pos["stop"] = min(pos["stop"], bar.close + p.atr_stop_mult * atr_now)
            window = bars[symbol][i - p.exit_lookback: i]
            if pos["side"] == "long" and bar.close < min(b.low for b in window):
                close_position(symbol, bar.close, "channel")
            elif pos["side"] == "short" and bar.close > max(b.high for b in window):
                close_position(symbol, bar.close, "channel")
            elif p.max_hold_bars and pos["bars"] >= p.max_hold_bars:
                close_position(symbol, bar.close, "time")
        # 2. neue Signale
        if ts >= start_ts:
            signals: list[tuple[float, str, str, int, float]] = []
            for symbol in symbols:
                if symbol in positions:
                    continue
                i = index[symbol].get(ts)
                if i is None or i < warm:
                    continue
                bar = bars[symbol][i]
                atr_now = atrs[symbol][i]
                if not atr_now:
                    continue
                window = bars[symbol][i - p.entry_lookback: i]
                hi = max(b.high for b in window)
                lo = min(b.low for b in window)
                filt = smas[symbol][i]
                side = None
                if p.allow_long and bar.close > hi and (filt is None or bar.close > filt):
                    side = "long"
                    strength = (bar.close - hi) / atr_now
                elif p.allow_short and bar.close < lo and (filt is None or bar.close < filt):
                    side = "short"
                    strength = (lo - bar.close) / atr_now
                if side is None:
                    continue
                signals.append((strength, symbol, side, i, atr_now))
            if rank_signals:
                signals.sort(key=lambda item: item[0], reverse=True)
            for strength, symbol, side, i, atr_now in signals:
                if len(positions) >= max_positions:
                    break
                bar = bars[symbol][i]
                stop_dist = p.atr_stop_mult * atr_now
                risk = ledger.equity * p.risk_pct
                if shared_margin:
                    used = sum(pos["qty"] * bars[s][index[s][ts]].close for s, pos in positions.items() if ts in index[s])
                    cap_notional = max(0.0, ledger.equity * p.max_margin_fraction * leverage - used)
                else:
                    cap_notional = ledger.equity * p.max_margin_fraction * leverage / max_positions
                qty = min(risk / stop_dist, cap_notional / bar.close)
                spec = specs[symbol]
                qty = floor_to_step(qty, spec.qty_step)
                if qty < spec.min_qty or qty * bar.close + 1e-9 < spec.min_notional:
                    ledger.exits["zu_klein"] = ledger.exits.get("zu_klein", 0) + 1
                    continue
                fill = costs.taker_buy(bar.close) if side == "long" else costs.taker_sell(bar.close)
                fee = fill * qty * costs.taker_fee
                ledger.fee(fee, True)
                ledger.equity -= fee
                positions[symbol] = {
                    "side": side,
                    "qty": qty,
                    "entry": fill,
                    "stop": fill - stop_dist if side == "long" else fill + stop_dist,
                    "entry_fee": fee,
                    "funding": 0.0,
                    "bars": 0,
                }
        # 3. Mark-to-Market
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
    return ledger.result({"strategy": p.name, "per_symbol": per_symbol, "max_positions": max_positions})
