"""Globales Risiko. Exits bleiben erlaubt, neue Entries nicht, wenn ein Limit zieht."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from unified_bot.models import OrderIntent
from unified_bot.settings import Settings, StrategySettings
from unified_bot.sizing import floor_size, round_trip_fee, tp_distance_pct
from unified_bot.gridcore.specs import ContractSpec


@dataclass
class RiskDecision:
    allow: bool
    reason: str
    size: float = 0.0
    notional: float = 0.0
    margin: float = 0.0


@dataclass
class RiskState:
    day: str = ""
    day_start_equity: float = 0.0
    halted: bool = False
    halt_reason: str = ""
    frozen_symbols: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)

    def on_day(self, day: str, equity: float) -> None:
        if day == self.day:
            return
        self.day = day
        self.day_start_equity = equity
        if self.halt_reason == "daily_loss":
            self.halted = False
            self.halt_reason = ""

    def check_daily(self, equity: float, daily_loss_pct: float) -> bool:
        if self.halted and self.halt_reason == "kill_switch":
            return True
        if self.day_start_equity <= 0:
            return False
        loss = self.day_start_equity - equity
        if loss >= self.day_start_equity * daily_loss_pct - 1e-9:
            self.halted = True
            self.halt_reason = "daily_loss"
            return True
        return self.halted and self.halt_reason == "daily_loss"

    def engage_kill(self) -> None:
        self.halted = True
        self.halt_reason = "kill_switch"

    def release_kill_if_clear(self) -> None:
        if self.halt_reason == "kill_switch":
            self.halted = False
            self.halt_reason = ""

    def entries_blocked(self) -> bool:
        return self.halted

    def to_dict(self) -> dict:
        return {
            "day": self.day,
            "day_start_equity": self.day_start_equity,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "frozen_symbols": sorted(self.frozen_symbols),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, raw: dict | None) -> "RiskState":
        raw = raw or {}
        return cls(
            day=str(raw.get("day") or ""),
            day_start_equity=float(raw.get("day_start_equity") or 0),
            halted=bool(raw.get("halted", False)),
            halt_reason=str(raw.get("halt_reason") or ""),
            frozen_symbols=set(raw.get("frozen_symbols") or []),
            notes=list(raw.get("notes") or []),
        )


def kill_file_active(path: Path) -> bool:
    return path.is_file()


class RiskManager:
    def __init__(self, settings: Settings, state: RiskState | None = None):
        self.settings = settings
        self.state = state or RiskState()

    def evaluate_open(
        self,
        intent: OrderIntent,
        spec: ContractSpec,
        strategy: StrategySettings,
        *,
        sleeve_free_margin: float,
        account_equity: float,
        open_notional: float,
        mark: float,
    ) -> RiskDecision:
        if intent.market == "spot" and intent.strategy_id != "funding_arb":
            return RiskDecision(False, "spot_not_enabled")
        if intent.strategy_id == "funding_arb":
            return RiskDecision(False, "funding_arb_not_implemented")
        if intent.strategy_id == "daily_trend":
            return RiskDecision(False, "daily_trend_not_implemented")
        if not strategy.enabled:
            return RiskDecision(False, "strategy_disabled")
        if strategy.entries_paused:
            return RiskDecision(False, "entries_paused")
        if self.state.entries_blocked():
            return RiskDecision(False, self.state.halt_reason or "halted")
        if intent.symbol in self.state.frozen_symbols:
            return RiskDecision(False, "symbol_frozen")
        if strategy.allocation <= 0:
            return RiskDecision(False, "no_allocation")
        if intent.leverage > self.settings.global_max_leverage or intent.leverage > strategy.max_leverage:
            return RiskDecision(False, "leverage_cap")
        if intent.leverage < 1 or mark <= 0 or intent.size <= 0:
            return RiskDecision(False, "bad_inputs")
        if spec.qty_step <= 0 or spec.min_qty <= 0:
            return RiskDecision(False, "bad_contract")

        size = floor_size(intent.size, spec.qty_step)
        price = intent.price if intent.price and intent.price > 0 else mark
        notional = size * price
        margin = notional / intent.leverage
        fields = dict(size=size, notional=notional, margin=margin)
        min_notional = max(spec.min_notional, self.settings.min_notional_usdt)
        if size + 1e-12 < spec.min_qty:
            return RiskDecision(False, "below_min_size", **fields)
        # Grid-Lose sind gleich groß. Still kürzen würde die Engine und die Börse auseinanderlaufen lassen.
        if intent.strategy_id == "grid" and abs(size - intent.size) > max(spec.qty_step * 0.01, 1e-9):
            return RiskDecision(False, "size_step", **fields)
        if notional + 1e-9 < min_notional:
            return RiskDecision(False, "below_min_notional", **fields)
        if margin > sleeve_free_margin + 1e-8:
            return RiskDecision(False, "margin_exceeds_sleeve", **fields)
        if account_equity <= 0:
            return RiskDecision(False, "no_equity", **fields)
        projected = open_notional + notional
        if projected > account_equity * self.settings.max_total_exposure + 1e-6:
            return RiskDecision(False, "exposure_cap", **fields)

        exit_maker = intent.wants_post_only if intent.exit_is_maker is None else bool(intent.exit_is_maker)
        if intent.exit_is_maker is not None:
            exit_maker = bool(intent.exit_is_maker)
        distance = tp_distance_pct(price, intent.take_profit, intent.expected_tp_pct)
        if distance is None:
            return RiskDecision(False, "tp_unknown", **fields)
        needed = self.settings.fee_tp_mult * round_trip_fee(
            intent.wants_post_only,
            exit_maker,
            self.settings.maker_fee,
            self.settings.taker_fee,
        )
        if distance + 1e-12 < needed:
            return RiskDecision(False, "tp_inside_fees", **fields)
        return RiskDecision(True, "ok", **fields)
