"""Offene Steckplätze. Keine Orders, bis die Recherche einen Regelstand hat."""

from __future__ import annotations

from unified_bot.market import CycleContext
from unified_bot.models import CyclePlan


class _ResearchSlot:
    id = ""
    todo = ""

    def __init__(self, settings):
        self.settings = settings.strategy(self.id)

    def plan(self, ctx: CycleContext) -> CyclePlan:
        return CyclePlan(notes=[self.todo])

    def consume_fill(self, fill, book) -> None:
        return None

    def on_reject(self, intent, reason: str) -> None:
        return None

    def export_state(self) -> dict:
        return {"status": "research"}

    def load_state(self, raw: dict) -> None:
        return None


class FundingArbSlot(_ResearchSlot):
    id = "funding_arb"
    todo = (
        "TODO Recherche: Funding-Arbitrage Spot long + Perp short (oder umgekehrt). "
        "Kein Signal, keine Orders. Spot-Payload existiert nur als Schnittstelle."
    )


class DailyTrendSlot(_ResearchSlot):
    id = "daily_trend"
    todo = (
        "TODO Recherche: Daily Trend Following. Kein Signal, keine Orders, "
        "bis eine festgelegte Regel out-of-sample positiv ist."
    )
