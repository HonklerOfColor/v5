"""Größe abrunden, nie aufrunden. Fee-Abstand für neue Entries."""

from __future__ import annotations

import math
from decimal import Decimal, ROUND_DOWN


def floor_size(raw: float, step: float) -> float:
    """Auf sizeMultiplier abrunden. Niemals aufrunden."""
    if raw <= 0 or step <= 0 or not math.isfinite(raw) or not math.isfinite(step):
        return 0.0
    quantum = Decimal(str(step))
    if quantum <= 0:
        return 0.0
    steps = (Decimal(str(raw)) / quantum).to_integral_value(rounding=ROUND_DOWN)
    return float(steps * quantum)


def round_trip_fee(entry_is_maker: bool, exit_is_maker: bool, maker_fee: float, taker_fee: float) -> float:
    entry = maker_fee if entry_is_maker else taker_fee
    exit_fee = maker_fee if exit_is_maker else taker_fee
    return entry + exit_fee


def tp_distance_pct(entry: float, take_profit: float | None, expected_tp_pct: float | None) -> float | None:
    if expected_tp_pct is not None:
        return float(expected_tp_pct)
    if take_profit is None or entry <= 0:
        return None
    return abs(take_profit - entry) / entry
