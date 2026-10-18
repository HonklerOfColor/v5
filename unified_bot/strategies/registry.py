"""Reihenfolge ist die Priorität bei Symbol-Sperren. Kleinere Zahl zuerst."""

from __future__ import annotations

from unified_bot.settings import Settings
from unified_bot.strategies.grid import GridStrategy
from unified_bot.strategies.reversal import ReversalStrategy
from unified_bot.strategies.slots import DailyTrendSlot, FundingArbSlot
from unified_bot.strategies.sniper import SniperStrategy
from unified_bot.strategies.trendjoin import TrendJoinStrategy


def build_strategies(settings: Settings) -> list:
    strategies = [
        GridStrategy(settings),
        ReversalStrategy(settings),
        SniperStrategy(settings),
        TrendJoinStrategy(settings),
        FundingArbSlot(settings),
        DailyTrendSlot(settings),
    ]
    return sorted(strategies, key=lambda item: settings.strategy(item.id).priority)
