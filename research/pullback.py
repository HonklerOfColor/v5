"""Pullback im Trend auf 4h: RSI(2) tief über dem 200er-Mittel kaufen, am 5er-Mittel verkaufen.

Long: Schluss über SMA(200) der 4h-Schlüsse und RSI(2) unter rsi_low → Einstieg
am Schluss (Taker). Ausstieg, wenn der Schluss über SMA(5) liegt, nach
max_hold Kerzen, oder am Stop (entry − atr_mult × ATR, am Schluss geprüft).
Short spiegelbildlich unter SMA(200) mit RSI(2) über rsi_high.
"""

from __future__ import annotations

from dataclasses import dataclass

from gridbot.candles import Candle, aggregate
from gridbot.specs import ContractSpec, floor_to_step
from research.costs import Costs
from research.metrics import Ledger
from research.trend import atr_series, sma_series


@dataclass(frozen=True)
class PullbackParams:
    name: str = "pullback_4h_rsi2"
    trend_sma: int = 200
    exit_sma: int = 5
    rsi_period: int = 2
    rsi_low: float = 10.0
    rsi_high: float = 90.0
    atr_period: int = 14
    atr_mult: float = 3.0
    max_hold: int = 12
    risk_pct: float = 0.01
    max_margin_fraction: float = 0.5
    allow_short: bool = True


def rsi_series(closes: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains += max(diff, 0.0)
        losses += max(-diff, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(diff, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-diff, 0.0)) / period
        out[i] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return out


def run_pullback(
    candles_1h: list[Candle],
    spec: ContractSpec,
    p: PullbackParams,
    costs: Costs,
    equity0: float,
    leverage: int = 2,
    start_index: int = 0,
) -> dict:
    bars = aggregate(candles_1h, 4)
    start_ts = candles_1h[start_index].ts if candles_1h else 0
    closes = [b.close for b in bars]
    trend = sma_series(closes, p.trend_sma)
    fast = sma_series(closes, p.exit_sma)
    rsi = rsi_series(closes, p.rsi_period)
    atrs = atr_series(bars, p.atr_period)
    ledger = Ledger(equity0)
    pos: dict | None = None

    def close_position(price: float, reason: str) -> None:
        nonlocal pos
        assert pos is not None
        fill = costs.taker_sell(price) if pos["side"] == "long" else costs.taker_buy(price)
        pnl = (fill - pos["entry"]) * pos["qty"] if pos["side"] == "long" else (pos["entry"] - fill) * pos["qty"]
        fee = fill * pos["qty"] * costs.taker_fee
        ledger.fee(fee, True)
        ledger.realized += pnl
        ledger.equity += pnl - fee
        ledger.close_trade(pnl - fee - pos["entry_fee"] - pos["funding"], reason)
        pos = None

    for i in range(p.trend_sma, len(bars)):
        bar = bars[i]
        ledger.bars += 1
        if pos is not None:
            ledger.bars_in_market += 1
            charge = costs.funding_charge(spec.symbol, bar.ts, pos["side"], pos["qty"] * bar.close)
            if charge:
                ledger.funding += charge
                ledger.equity -= charge
                pos["funding"] += charge
            pos["bars"] += 1
            f = fast[i]
            if pos["side"] == "long" and (bar.close <= pos["stop"]):
                close_position(bar.close, "stop")
            elif pos["side"] == "short" and (bar.close >= pos["stop"]):
                close_position(bar.close, "stop")
            elif f is not None and ((pos["side"] == "long" and bar.close > f) or (pos["side"] == "short" and bar.close < f)):
                close_position(bar.close, "ziel")
            elif pos["bars"] >= p.max_hold:
                close_position(bar.close, "zeit")
        if pos is None and bar.ts >= start_ts:
            t, r, a = trend[i], rsi[i], atrs[i]
            if t is None or r is None or not a:
                continue
            side = None
            if bar.close > t and r < p.rsi_low:
                side = "long"
            elif p.allow_short and bar.close < t and r > p.rsi_high:
                side = "short"
            if side is None:
                continue
            stop_dist = p.atr_mult * a
            qty = min(ledger.equity * p.risk_pct / stop_dist, ledger.equity * p.max_margin_fraction * leverage / bar.close)
            qty = floor_to_step(qty, spec.qty_step)
            if qty < spec.min_qty or qty * bar.close + 1e-9 < spec.min_notional:
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
        if pos is not None:
            unreal = (bar.close - pos["entry"]) * pos["qty"] if pos["side"] == "long" else (pos["entry"] - bar.close) * pos["qty"]
            ledger.mark(ledger.equity + unreal)
        else:
            ledger.mark(ledger.equity)
    if pos is not None and bars:
        close_position(bars[-1].close, "ende")
        ledger.mark(ledger.equity)
    return ledger.result({"strategy": p.name})
