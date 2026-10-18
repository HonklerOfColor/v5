"""Tagesverlust und Kill-Switch. Der Kill-Switch bleibt, bis die Datei weg ist."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RiskGuard:
    day: str = ""
    day_start_equity: float = 0.0
    halted: bool = False
    halt_reason: str = ""
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
        return self.halted

    def engage_kill(self, reason: str = "kill_switch") -> None:
        self.halted = True
        self.halt_reason = reason

    def release_kill_if_clear(self) -> None:
        if self.halt_reason == "kill_switch":
            self.halted = False
            self.halt_reason = ""

    def to_dict(self) -> dict:
        return {
            "day": self.day,
            "day_start_equity": self.day_start_equity,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
        }

    @classmethod
    def from_dict(cls, raw: dict | None) -> "RiskGuard":
        raw = raw or {}
        return cls(
            day=str(raw.get("day", "")),
            day_start_equity=float(raw.get("day_start_equity", 0) or 0),
            halted=bool(raw.get("halted", False)),
            halt_reason=str(raw.get("halt_reason", "")),
        )


def kill_file_active(path: Path) -> bool:
    return path.is_file()
