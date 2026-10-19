"""Donchian-Trendfolge auf 4h-Kerzen, eine Position je Symbol, Taker rein und raus.

Entscheidung nur am Schluss einer abgeschlossenen 4h-Kerze. Einstieg, wenn der
Schluss über dem Hoch der letzten N Kerzen liegt (Long) bzw. unter dem Tief
(Short). Ausstieg per ATR-Trailing-Stop (innerhalb der Kerze, bei einer Lücke
am Open) oder wenn der Schluss den Gegenkanal der letzten M Kerzen verlässt.
Größe: fester Risikoanteil des Kapitals auf den Stop-Abstand, gedeckelt durch
Hebel × Margin-Anteil. Zu kleine Orders werden nicht aufgefüllt, sondern
ausgelassen — wie beim Grid.
"""

from __future__ import annotations

from dataclasses import dataclass

from gridbot.candles import Candle, aggregate
from gridbot.indicators import _true_ranges, _wilder
from gridbot.specs import ContractSpec, floor_to_step
from research.costs import Costs
from research.metrics import Ledger


@dataclass(frozen=True)
class TrendParams:
    name: str = "donchian_40_20"
    hours: int = 4
    entry_lookback: int = 40
    exit_lookback: int = 20
    atr_period: int = 14
    atr_stop_mult: float = 3.0
    risk_pct: float = 0.01
    max_margin_fraction: float = 0.5
    allow_short: bool = True
    allow_long: bool = True
    trend_filter_hours: int = 0  # 0 = aus; sonst SMA über so viele Stunden als Richtungsfilter
    max_hold_bars: int = 0  # 0 = kein Zeitstopp


def atr_series(candles: list[Candle], period: int) -> list[float | None]:
    """ATR je Kerze (Wilder), None solange zu wenig Historie."""
    trs, _, _ = _true_ranges(candles)
    out: list[float | None] = [None] * len(candles)
    if len(trs) < period:
        return out
    smoothed = _wilder(trs, period)
    # trs[k] gehört zu candles[k+1]; smoothed[0] gehört zu candles[period]
    for j, value in enumerate(smoothed):
        out[period + j] = value
    return out


def sma_series(closes: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if period <= 0 or len(closes) < period:
        return out
    total = sum(closes[:period])
    out[period - 1] = total / period
    for i in range(period, len(closes)):
        total += closes[i] - closes[i - period]
        out[i] = total / period
    return out


def _size(equity: float, price: float, stop_dist: float, spec: ContractSpec, p: TrendParams, leverage: int) -> float | None:
    if stop_dist <= 0 or price <= 0:
        return None
    risk = equity * p.risk_pct
    qty = risk / stop_dist
    cap_notional = equity * p.max_margin_fraction * leverage
    qty = min(qty, cap_notional / price)
    qty = floor_to_step(qty, spec.qty_step)
    if qty < spec.min_qty or qty * price + 1e-9 < spec.min_notional:
        return None
    return qty


def run_trend(
    candles_1h: list[Candle],
    spec: ContractSpec,
    p: TrendParams,
    costs: Costs,
    equity0: float,
    leverage: int = 2,
    start_index: int = 0,
) -> dict:
    """start_index bezieht sich auf die 1h-Kerzen; davor nur Warmup."""
    bars = aggregate(candles_1h, p.hours)
    start_ts = candles_1h[start_index].ts if candles_1h else 0
    atrs = atr_series(bars, p.atr_period)
    closes = [bar.close for bar in bars]
    sma = sma_series(closes, p.trend_filter_hours // p.hours) if p.trend_filter_hours else [None] * len(bars)
    ledger = Ledger(equity0)
    pos: dict | None = None
    warm = max(p.entry_lookback, p.exit_lookback, p.atr_period) + 1

    def close_position(price: float, reason: str, taker: bool = True) -> None:
        nonlocal pos
        assert pos is not None
        if pos["side"] == "long":
            fill = costs.taker_sell(price) if taker else price
            pnl = (fill - pos["entry"]) * pos["qty"]
        else:
            fill = costs.taker_buy(price) if taker else price
            pnl = (pos["entry"] - fill) * pos["qty"]
        fee = fill * pos["qty"] * (costs.taker_fee if taker else costs.maker_fee)
        ledger.fee(fee, taker)
        ledger.realized += pnl
        ledger.equity += pnl - fee
        ledger.close_trade(pnl - fee - pos["entry_fee"] - pos["funding"], reason)
        pos = None

    for i in range(warm, len(bars)):
        bar = bars[i]
        ledger.bars += 1
        if pos is not None:
            ledger.bars_in_market += 1
            charge = costs.funding_charge(spec.symbol, bar.ts, pos["side"], pos["qty"] * bar.close)
            if charge:
                ledger.funding += charge
                ledger.equity -= charge
                pos["funding"] += charge
            # 1. Stop innerhalb der Kerze
            stop = pos["stop"]
            hit = bar.low <= stop if pos["side"] == "long" else bar.high >= stop
            if hit:
                price = min(stop, bar.open) if pos["side"] == "long" else max(stop, bar.open)
                close_position(price, "stop")
            else:
                pos["bars"] += 1
                atr_now = atrs[i]
                if atr_now:
                    if pos["side"] == "long":
                        pos["stop"] = max(pos["stop"], bar.close - p.atr_stop_mult * atr_now)
                    else:
                        pos["stop"] = min(pos["stop"], bar.close + p.atr_stop_mult * atr_now)
                window = bars[i - p.exit_lookback: i]
                if pos["side"] == "long" and bar.close < min(b.low for b in window):
                    close_position(bar.close, "channel")
                elif pos["side"] == "short" and bar.close > max(b.high for b in window):
                    close_position(bar.close, "channel")
                elif p.max_hold_bars and pos["bars"] >= p.max_hold_bars:
                    close_position(bar.close, "time")
        if pos is None and bar.ts >= start_ts:
            atr_now = atrs[i]
            if not atr_now:
                continue
            window = bars[i - p.entry_lookback: i]
            hi = max(b.high for b in window)
            lo = min(b.low for b in window)
            filt = sma[i]
            side = None
            if p.allow_long and bar.close > hi and (filt is None or bar.close > filt):
                side = "long"
            elif p.allow_short and bar.close < lo and (filt is None or bar.close < filt):
                side = "short"
            if side is None:
                continue
            stop_dist = p.atr_stop_mult * atr_now
            qty = _size(ledger.equity, bar.close, stop_dist, spec, p, leverage)
            if qty is None:
                ledger.exits["zu_klein"] = ledger.exits.get("zu_klein", 0) + 1
                continue
            fill = costs.taker_buy(bar.close) if side == "long" else costs.taker_sell(bar.close)
            fee = fill * qty * costs.taker_fee
            ledger.fee(fee, True)
            ledger.equity -= fee
            pos = {
                "side": side,
                "qty": qty,
                "entry": fill,
                "stop": fill - stop_dist if side == "long" else fill + stop_dist,
                "entry_fee": fee,
                "funding": 0.0,
                "bars": 0,
            }
        # Mark-to-Market
        if pos is not None:
            unreal = (bar.close - pos["entry"]) * pos["qty"] if pos["side"] == "long" else (pos["entry"] - bar.close) * pos["qty"]
            ledger.mark(ledger.equity + unreal)
        else:
            ledger.mark(ledger.equity)

    if pos is not None and bars:
        close_position(bars[-1].close, "ende")
        ledger.mark(ledger.equity)
    return ledger.result({"strategy": p.name})
