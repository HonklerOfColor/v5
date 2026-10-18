"""Monatliche Universumswahl, Port von lib.excl_set und lib.universe (PREREG_trend_ensemble.md, "Daten")."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from unified_bot.spot.candles import DailySeries, weekday
from unified_bot.spot.params import (
    TREND_ANNUALIZE,
    TREND_EXCLUDED_BASES,
    TREND_LOW_VOL_ANNUAL,
    TREND_MIN_HISTORY_DAYS,
    TREND_UNIVERSE_MIN_MEDIAN_USDT,
    TREND_UNIVERSE_VOLUME_DAYS,
    TREND_UNIVERSE_VOLUME_MIN_PERIODS,
    TREND_WEEKEND_RATIO,
    TREND_WEEKEND_RULE_FROM_DAY,
)
from unified_bot.spot.signals import pct_change, rolling_median

_LEVERAGED = re.compile(r"\d+[LS]$")


def excluded_by_name(base: str) -> bool:
    """lib.excl_set, Namensregel: EXPL-Liste und Binance-"B"-Varianten; dazu Leveraged-Tokens (3L/3S).

    Bitget-spezifisch (PREREG: "Tokenized Stocks" ausschließen): Tokenized Stocks heißen dort
    "rSPY", "rNVDA", … (kleines r vor Großbuchstaben, areaSymbol=yes, keine Kerzen über die API),
    Pre-Market-Token "preSPCX". Beides fliegt raus.
    """
    raw = base or ""
    if len(raw) > 1 and raw[0] == "r" and raw[1:].isupper():
        return True
    if raw.startswith("pre") and len(raw) > 3 and raw[3:].isupper():
        return True
    base = raw.upper()
    if base in TREND_EXCLUDED_BASES:
        return True
    if base.endswith("B") and len(base) >= 3 and base[:-1] in TREND_EXCLUDED_BASES:
        return True
    if _LEVERAGED.search(base):
        return True
    return False


def excluded_by_returns(series: DailySeries, until_day: int, first_listed_day: int | None) -> bool:
    """lib.excl_set, Rendite-Regeln: Jahresvola < 5 %; Wochenend-Stille nur für Listings ab 2025."""
    index = series.index_of(min(until_day, series.last_day))
    if index is None:
        return False
    closes = series.closes[: index + 1]
    returns = [(series.first_day + offset, value) for offset, value in enumerate(pct_change(closes)) if value == value]
    if len(returns) < 30:
        return False
    values = [value for _, value in returns]
    mean = math.fsum(values) / len(values)
    variance = math.fsum((value - mean) ** 2 for value in values) / (len(values) - 1)
    if math.sqrt(variance) * TREND_ANNUALIZE < TREND_LOW_VOL_ANNUAL:
        return True
    first_return_day = returns[0][0]
    listed = first_listed_day if first_listed_day is not None else first_return_day
    if listed < TREND_WEEKEND_RULE_FROM_DAY:
        return False
    weekend = [abs(value) for day, value in returns if weekday(day) >= 5]
    weekdays = [abs(value) for day, value in returns if weekday(day) < 5]
    if not weekend or not weekdays:
        return False
    wk = math.fsum(weekend) / len(weekend)
    wd = math.fsum(weekdays) / len(weekdays)
    return wd > 0 and wk / wd < TREND_WEEKEND_RATIO


@dataclass
class Candidate:
    symbol: str
    median_volume: float
    history_days: int
    eligible: bool
    reason: str


def median_volume_at(series: DailySeries, day: int) -> float:
    """qvol.rolling(30, min_periods=20).median() am Tag `day`."""
    index = series.index_of(day)
    if index is None:
        return float("nan")
    window = series.quote_volumes[max(0, index - TREND_UNIVERSE_VOLUME_DAYS + 1) : index + 1]
    return rolling_median(window, TREND_UNIVERSE_VOLUME_DAYS, TREND_UNIVERSE_VOLUME_MIN_PERIODS)[-1]


def rank_candidates(
    series_by_symbol: dict[str, DailySeries],
    month_end_day: int,
    excluded: set[str],
    first_listed: dict[str, int] | None = None,
) -> list[Candidate]:
    """lib.universe am Monatsende: Historie >= 60 Schlusskurse, Median >= 2 Mio, Schluss vorhanden."""
    out: list[Candidate] = []
    for symbol, series in series_by_symbol.items():
        if symbol in excluded:
            out.append(Candidate(symbol, float("nan"), 0, False, "excluded"))
            continue
        history = series.count_closes_until(month_end_day)
        median = median_volume_at(series, month_end_day)
        close = series.close_at(month_end_day)
        if close != close:
            out.append(Candidate(symbol, median, history, False, "no_close_at_month_end"))
            continue
        if history < TREND_MIN_HISTORY_DAYS:
            out.append(Candidate(symbol, median, history, False, "history_below_60"))
            continue
        if median != median or median < TREND_UNIVERSE_MIN_MEDIAN_USDT:
            out.append(Candidate(symbol, median, history, False, "median_volume_below_min"))
            continue
        if excluded_by_returns(series, month_end_day, (first_listed or {}).get(symbol)):
            out.append(Candidate(symbol, median, history, False, "excluded_returns"))
            continue
        out.append(Candidate(symbol, median, history, True, "ok"))
    return out


def select_universe(candidates: list[Candidate], size: int) -> list[str]:
    eligible = [item for item in candidates if item.eligible]
    eligible.sort(key=lambda item: (-item.median_volume, item.symbol))
    return [item.symbol for item in eligible[:size]]
