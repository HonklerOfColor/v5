"""ADX, Bollinger-Breite, ATR und Kaufman-Efficiency. Nur geschlossene Kerzen."""

from __future__ import annotations

import math

from unified_bot.gridcore.candles import Candle


def _wilder(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    seed = sum(values[:period]) / period
    out = [seed]
    for value in values[period:]:
        seed = (seed * (period - 1) + value) / period
        out.append(seed)
    return out


def _true_ranges(candles: list[Candle]) -> tuple[list[float], list[float], list[float]]:
    trs: list[float] = []
    plus: list[float] = []
    minus: list[float] = []
    for i in range(1, len(candles)):
        high = candles[i].high
        low = candles[i].low
        prev = candles[i - 1]
        trs.append(max(high - low, abs(high - prev.close), abs(low - prev.close)))
        up = high - prev.high
        down = prev.low - low
        plus.append(up if up > down and up > 0 else 0.0)
        minus.append(down if down > up and down > 0 else 0.0)
    return trs, plus, minus


def adx(candles: list[Candle], period: int = 14) -> float | None:
    """Wilder-ADX. None, wenn die Serie zu kurz ist."""
    if len(candles) < period * 3 + 2:
        return None
    trs, plus, minus = _true_ranges(candles)
    atr_s = _wilder(trs, period)
    plus_s = _wilder(plus, period)
    minus_s = _wilder(minus, period)
    dxs: list[float] = []
    for atr_v, p_v, m_v in zip(atr_s, plus_s, minus_s):
        if atr_v <= 0:
            dxs.append(0.0)
            continue
        pdi = 100.0 * p_v / atr_v
        mdi = 100.0 * m_v / atr_v
        denom = pdi + mdi
        dxs.append(0.0 if denom == 0 else 100.0 * abs(pdi - mdi) / denom)
    smoothed = _wilder(dxs, period)
    if not smoothed:
        return None
    return smoothed[-1]


def atr(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) < period + 2:
        return None
    trs, _, _ = _true_ranges(candles)
    smoothed = _wilder(trs, period)
    if not smoothed:
        return None
    return smoothed[-1]


def atr_pct(candles: list[Candle], period: int = 14) -> float | None:
    value = atr(candles, period)
    close = candles[-1].close if candles else 0.0
    if value is None or close <= 0:
        return None
    return value / close


def bb_width(closes: list[float], period: int = 20, mult: float = 2.0) -> float | None:
    if len(closes) < period:
        return None
    window = closes[-period:]
    mid = sum(window) / period
    if mid <= 0:
        return None
    var = sum((item - mid) ** 2 for item in window) / period
    std = math.sqrt(var)
    return (2.0 * mult * std) / mid


def efficiency_ratio(closes: list[float], lookback: int) -> float | None:
    if len(closes) < lookback + 1 or lookback <= 0:
        return None
    change = abs(closes[-1] - closes[-1 - lookback])
    path = 0.0
    start = len(closes) - lookback
    for i in range(start, len(closes)):
        path += abs(closes[i] - closes[i - 1])
    if path == 0:
        return 0.0
    return change / path


def mid_crosses(candles: list[Candle], lookback: int) -> int:
    if len(candles) < lookback or lookback < 2:
        return 0
    window = candles[-lookback:]
    high = max(item.high for item in window)
    low = min(item.low for item in window)
    mid = (high + low) / 2.0
    crosses = 0
    prev_above = window[0].close > mid
    for candle in window[1:]:
        above = candle.close > mid
        if above != prev_above:
            crosses += 1
            prev_above = above
    return crosses
