"""V1-Regeln aus TRADING_RULES.md. Keine API, kein State."""

from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

VIENNA = ZoneInfo("Europe/Vienna")
BLOCKED_ENTRY_HOURS = frozenset({0, 1, 2, 3, 4, 14, 17, 20, 22})
TIME_STOP_HOURS = 24.0
BREAKEVEN_MIN_AGE_H = 12.0
BREAKEVEN_MIN_ROE_PCT = 0.3
LEVERAGE = 3
TP_ATR_MULT = 2.5
SL_ATR_FALLBACK = 1.5
SL_MIN_ATR = 0.8
MAX_FUNDING_RATE = 0.0005
MAX_SPREAD_PCT = 0.01
LONG_ONLY = True


def vienna_hour(epoch_s: float | None = None) -> int:
    if epoch_s is None:
        epoch_s = time.time()
    return datetime.fromtimestamp(epoch_s, VIENNA).hour


def entry_hour_blocked(epoch_s: float | None = None) -> bool:
    return vienna_hour(epoch_s) in BLOCKED_ENTRY_HOURS


def unrealized_roe_pct(pnl: float, size: float, mark: float, leverage: float) -> float | None:
    if size <= 0 or mark <= 0 or leverage <= 0:
        return None
    margin = size * mark / leverage
    if margin <= 0:
        return None
    return pnl / margin * 100.0


def should_time_stop(age_h: float, roe_pct: float) -> bool:
    return age_h >= TIME_STOP_HOURS and roe_pct <= 0


def time_stop_due(age_h: float, pnl: float, size: float, mark: float, leverage: float) -> bool:
    roe = unrealized_roe_pct(pnl, size, mark, leverage)
    if roe is None:
        roe = 0.0 if pnl <= 0 else 1.0
    return should_time_stop(age_h, roe)


def should_arm_breakeven(age_h: float, roe_pct: float, peak_roe: float, breakeven_pnl_pct: float = 0.03) -> bool:
    return (
        age_h >= BREAKEVEN_MIN_AGE_H
        and roe_pct >= BREAKEVEN_MIN_ROE_PCT
        and peak_roe < (breakeven_pnl_pct * 100.0)
    )


def reversal_long_signal(prev_open: float, prev_close: float, last_open: float, last_close: float) -> bool:
    """Vorletzte Kerze rot, letzte grün. Long-only seit 2026-08-26."""
    return prev_close < prev_open and last_close > last_open
