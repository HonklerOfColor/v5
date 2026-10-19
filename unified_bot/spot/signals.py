"""Signale, Zeile für Zeile aus docs/spot_modules/code/lib.py (trend_panel, donchian_combo) und tf.py (sig "ENS").

Reine Python-Ports ohne pandas/numba, damit der Bot keine neuen Abhängigkeiten braucht.
Die Tests prüfen sie gegen Referenzwerte, die mit lib.py/tf.py erzeugt wurden (Toleranz 1e-9).
"""

from __future__ import annotations

import math

from unified_bot.spot.params import (
    TF_SMA_WINDOWS,
    TREND_ANNUALIZE,
    TREND_CAP,
    TREND_SIGMA_DAYS,
    TREND_VT,
    TREND_WINDOWS,
)

NAN = float("nan")


def _finite(value: float) -> bool:
    return value == value and not math.isinf(value)


def pct_change(closes: list[float]) -> list[float]:
    """pandas pct_change(fill_method=None): NaN, wenn heute oder gestern fehlt."""
    out = [NAN] * len(closes)
    for index in range(1, len(closes)):
        previous = closes[index - 1]
        current = closes[index]
        if _finite(previous) and _finite(current) and previous != 0:
            out[index] = current / previous - 1.0
    return out


def rolling_std(values: list[float], window: int, min_periods: int) -> list[float]:
    """pandas rolling(window, min_periods).std(): Stichproben-Std (ddof=1) über die endlichen Werte."""
    out = [NAN] * len(values)
    for end in range(len(values)):
        start = max(0, end - window + 1)
        sample = [value for value in values[start : end + 1] if _finite(value)]
        if len(sample) < min_periods or len(sample) < 2:
            continue
        mean = math.fsum(sample) / len(sample)
        variance = math.fsum((value - mean) ** 2 for value in sample) / (len(sample) - 1)
        out[end] = math.sqrt(variance) if variance > 0 else 0.0
    return out


def rolling_mean(values: list[float], window: int, min_periods: int) -> list[float]:
    out = [NAN] * len(values)
    for end in range(len(values)):
        start = max(0, end - window + 1)
        sample = [value for value in values[start : end + 1] if _finite(value)]
        if len(sample) < min_periods:
            continue
        out[end] = math.fsum(sample) / len(sample)
    return out


def rolling_median(values: list[float], window: int, min_periods: int) -> list[float]:
    out = [NAN] * len(values)
    for end in range(len(values)):
        start = max(0, end - window + 1)
        sample = sorted(value for value in values[start : end + 1] if _finite(value))
        if len(sample) < min_periods or not sample:
            continue
        middle = len(sample) // 2
        if len(sample) % 2:
            out[end] = sample[middle]
        else:
            out[end] = 0.5 * (sample[middle - 1] + sample[middle])
    return out


def sigma_annualized(closes: list[float], days: int = TREND_SIGMA_DAYS, annualize: float = TREND_ANNUALIZE) -> list[float]:
    """lib.trend_panel: r.rolling(90, min_periods=90).std() * sqrt(365)."""
    return [value * annualize if _finite(value) else NAN for value in rolling_std(pct_change(closes), days, days)]


def donchian_combo(
    closes: list[float],
    sigma: list[float],
    windows: tuple[int, ...] = TREND_WINDOWS,
    vt: float = TREND_VT,
    cap: float = TREND_CAP,
) -> tuple[list[float], list[bool], dict[int, tuple[int, float]]]:
    """Port von lib.donchian_combo. Liefert Gewichte W, Flags ch und den Endzustand je Fenster.

    Einstieg: Schluss >= Fenster-Hoch (Schlusskurse). Stop = Mittelband, nur aufwärts.
    Ausstieg: Schluss <= Stop. Gewicht je Fenster min(vt/σ, cap)/Anzahl Fenster.
    """
    length = len(closes)
    weights = [0.0] * length
    changed = [False] * length
    final_state: dict[int, tuple[int, float]] = {}
    for window in windows:
        pos = 0
        stop = NAN
        for t in range(length):
            previous = pos
            close = closes[t]
            sig = sigma[t]
            if not _finite(close) or not _finite(sig) or t < window - 1:
                pos = 0
            else:
                highest = -1e300
                lowest = 1e300
                bad = False
                for k in range(t - window + 1, t + 1):
                    value = closes[k]
                    if not _finite(value):
                        bad = True
                        break
                    if value > highest:
                        highest = value
                    if value < lowest:
                        lowest = value
                if bad:
                    pos = 0
                else:
                    mid = 0.5 * (highest + lowest)
                    if pos == 0:
                        if close >= highest:
                            pos = 1
                            stop = mid
                    else:
                        if close <= stop:
                            pos = 0
                        elif mid > stop:
                            stop = mid
            if pos != previous:
                changed[t] = True
            if pos == 1 and sig > 0:
                weights[t] += min(vt / sig, cap) / len(windows)
        final_state[window] = (pos, stop)
    return weights, changed, final_state


def trend_weights(closes: list[float]) -> tuple[list[float], list[bool], dict[int, tuple[int, float]]]:
    """lib.trend_panel für einen Coin: Gewicht je Tag (Anteil von 1, vor der 1/B-Teilung) und Flag."""
    return donchian_combo(closes, sigma_annualized(closes))


def sma_signal(closes: list[float], window: int) -> list[float]:
    """tf.sig("SMAn"): 1.0 wenn Close > SMA(n), 0.0 sonst, NaN solange die SMA fehlt."""
    means = rolling_mean(closes, window, window)
    out = [NAN] * len(closes)
    for index, mean in enumerate(means):
        if not _finite(mean):
            continue
        close = closes[index]
        out[index] = 1.0 if (_finite(close) and close > mean) else 0.0
    return out


def ensemble_signal(closes: list[float], windows: tuple[int, ...] = TF_SMA_WINDOWS) -> list[float]:
    """tf.sig("ENS"): Mittel der Binärsignale, NaN sobald eines fehlt (skipna=False)."""
    parts = [sma_signal(closes, window) for window in windows]
    out = [NAN] * len(closes)
    for index in range(len(closes)):
        values = [part[index] for part in parts]
        if any(not _finite(value) for value in values):
            continue
        out[index] = math.fsum(values) / len(values)
    return out
