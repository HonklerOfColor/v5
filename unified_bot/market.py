"""Was eine Strategie in einem Zyklus sehen darf. Kein API-Client."""

from __future__ import annotations

from dataclasses import dataclass, field

from unified_bot.gridcore.candles import Candle
from unified_bot.gridcore.specs import ContractSpec
from unified_bot.models import Position, WorkingOrder


@dataclass
class SymbolView:
    symbol: str
    candles: list[Candle]
    bid: float
    ask: float
    last: float
    funding_rate: float | None = None
    spec: ContractSpec | None = None
    bids: list = field(default_factory=list)
    asks: list = field(default_factory=list)
    error: str = ""

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.last


@dataclass
class CycleContext:
    now_ms: int
    mode: str
    sleeve_equity: float
    free_margin: float
    entries_allowed: bool
    views: dict[str, SymbolView]
    positions: list[Position]
    orders: list[WorkingOrder]
    frozen: set[str] = field(default_factory=set)
    day: str = ""
    entries_today: int = 0
    last_stop_ms: dict[str, int] = field(default_factory=dict)

    def known_order_ids(self) -> set[str]:
        return {order.client_oid for order in self.orders}
