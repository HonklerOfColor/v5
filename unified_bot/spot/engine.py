"""Tagesschritt des Referenz-Backtests (lib.run_engine, mode="trend"), als Zustand + Schritt.

Beide Module entscheiden damit, welche Umschichtung heute stattfindet. Die Schattenrechnung
führt denselben Schritt mit idealisierten Kosten (COST_PER_SIDE auf den Umsatz, keine Mindestorder).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from unified_bot.spot.params import COST_PER_SIDE, REBALANCE_THRESHOLD

NAN = float("nan")


def _finite(value) -> bool:
    try:
        return value == value and not math.isinf(float(value))
    except (TypeError, ValueError):
        return False


@dataclass
class TradeDecision:
    symbol: str
    target: float          # Ziel-Notional in USDT
    position: float        # Ist-Notional in USDT
    delta: float           # Umschichtung in USDT, >0 kaufen, <0 verkaufen
    trade: bool
    reason: str            # flag | threshold | close_out | below_min | no_change | delisted


def decide_trades(
    equity: float,
    positions: dict[str, float],
    prices: dict[str, float],
    targets: dict[str, float],
    flags: dict[str, bool],
    *,
    threshold: float = REBALANCE_THRESHOLD,
    min_notional: dict[str, float] | None = None,
) -> list[TradeDecision]:
    """Ein Tag aus run_engine: T = TW·E, delta = T − P, Handel bei Flag, > thr·|T| oder Glattstellung.

    `positions` und `prices` sind nach dem Marktschritt (Bewertung zum heutigen Preis) gemeint.
    Mit `min_notional` gilt die capital.py-Logik: Ziel unter Mindestorder wird 0, ein Delta unter
    der Mindestorder wird nicht gehandelt, außer die Position wird ganz geschlossen.
    """
    out: list[TradeDecision] = []
    symbols = sorted(set(positions) | set(targets))
    for symbol in symbols:
        position = float(positions.get(symbol, 0.0))
        price = prices.get(symbol)
        weight = float(targets.get(symbol, 0.0))
        if not _finite(price) or price is None or price <= 0:
            target = 0.0
        else:
            target = weight * equity
        minimum = (min_notional or {}).get(symbol)
        if minimum is not None and abs(target) < minimum:
            target = 0.0
        delta = target - position
        flag = bool(flags.get(symbol, False))
        close_out = target == 0.0 and position != 0.0
        trade = flag or abs(delta) > threshold * abs(target) or close_out
        reason = "no_change"
        if trade:
            reason = "flag" if flag else ("close_out" if close_out else "threshold")
        if minimum is not None and trade and not (abs(delta) >= minimum or target == 0.0):
            trade = False
            reason = "below_min"
        if delta == 0.0:
            trade = False
            if reason != "below_min":
                reason = "no_change"
        if close_out and (price is None or not _finite(price)):
            reason = "delisted"
        out.append(TradeDecision(symbol, target, position, delta, trade, reason))
    return out


@dataclass
class ShadowState:
    """Idealisierte Equity: Notional je Coin, zuletzt bewerteter Preis, Equity in USDT."""

    equity: float
    positions: dict[str, float] = field(default_factory=dict)
    last_prices: dict[str, float] = field(default_factory=dict)
    costs_total: float = 0.0
    turnover_total: float = 0.0

    def to_dict(self) -> dict:
        return {
            "equity": self.equity,
            "positions": dict(self.positions),
            "last_prices": dict(self.last_prices),
            "costs_total": self.costs_total,
            "turnover_total": self.turnover_total,
        }

    @classmethod
    def from_dict(cls, raw: dict | None, start_capital: float) -> "ShadowState":
        raw = raw or {}
        return cls(
            equity=float(raw.get("equity", start_capital)),
            positions={str(k): float(v) for k, v in (raw.get("positions") or {}).items()},
            last_prices={str(k): float(v) for k, v in (raw.get("last_prices") or {}).items()},
            costs_total=float(raw.get("costs_total") or 0.0),
            turnover_total=float(raw.get("turnover_total") or 0.0),
        )

    def mark(self, prices: dict[str, float], cost: float = COST_PER_SIDE) -> list[str]:
        """Marktschritt: P wächst mit dem Preis. Ohne Preis (Delisting) wird zum letzten Kurs geschlossen."""
        dead: list[str] = []
        for symbol in list(self.positions):
            position = self.positions[symbol]
            if position == 0.0:
                self.positions.pop(symbol, None)
                continue
            price = prices.get(symbol)
            last = self.last_prices.get(symbol)
            if price is None or not _finite(price) or price <= 0:
                charge = abs(position) * cost
                self.equity -= charge
                self.costs_total += charge
                self.turnover_total += abs(position)
                self.positions.pop(symbol, None)
                dead.append(symbol)
                continue
            if last and last > 0:
                ratio = price / last
                self.equity += position * (ratio - 1.0)
                self.positions[symbol] = position * ratio
            self.last_prices[symbol] = price
        for symbol, price in prices.items():
            if _finite(price) and price > 0:
                self.last_prices[symbol] = price
        if self.equity <= 0:
            self.equity = 0.0
            self.positions.clear()
        return dead

    def apply(self, decisions: list[TradeDecision], cost: float = COST_PER_SIDE) -> float:
        """Handelsschritt: Kosten auf den Umsatz, Notional nachziehen. Liefert die Kosten."""
        total = 0.0
        for decision in decisions:
            if not decision.trade or decision.delta == 0.0:
                continue
            charge = abs(decision.delta) * cost
            total += charge
            self.turnover_total += abs(decision.delta)
            new_position = self.positions.get(decision.symbol, 0.0) + decision.delta
            if abs(new_position) < 1e-12:
                self.positions.pop(decision.symbol, None)
            else:
                self.positions[decision.symbol] = new_position
        self.equity -= total
        self.costs_total += total
        return total

    def step(
        self,
        prices: dict[str, float],
        targets: dict[str, float],
        flags: dict[str, bool],
        *,
        threshold: float = REBALANCE_THRESHOLD,
        min_notional: dict[str, float] | None = None,
        cost: float = COST_PER_SIDE,
    ) -> list[TradeDecision]:
        """Ein kompletter Tag wie in run_engine: markieren, entscheiden, handeln."""
        self.mark(prices, cost)
        if self.equity <= 0:
            return []
        decisions = decide_trades(
            self.equity, self.positions, prices, targets, flags, threshold=threshold, min_notional=min_notional
        )
        self.apply(decisions, cost)
        return decisions

    def gross_exposure(self) -> float:
        if self.equity <= 0:
            return 0.0
        return sum(abs(value) for value in self.positions.values()) / self.equity


def simulate(
    closes: dict[str, list[float]],
    targets: dict[str, list[float]],
    flags: dict[str, list[bool]],
    start_capital: float,
    *,
    cost: float = COST_PER_SIDE,
    threshold: float = REBALANCE_THRESHOLD,
    min_notional: dict[str, float] | None = None,
) -> list[float]:
    """Ganzer Pfad über ein Panel, nur für Tests gegen lib.run_engine."""
    symbols = sorted(closes)
    length = len(next(iter(closes.values())))
    state = ShadowState(equity=start_capital)
    equity_path: list[float] = []
    for t in range(length):
        prices = {symbol: closes[symbol][t] for symbol in symbols}
        day_targets = {symbol: targets[symbol][t] for symbol in symbols}
        day_flags = {symbol: bool(flags[symbol][t]) for symbol in symbols}
        state.step(prices, day_targets, day_flags, threshold=threshold, min_notional=min_notional, cost=cost)
        equity_path.append(state.equity)
        if state.equity <= 0:
            equity_path.extend([0.0] * (length - t - 1))
            break
    return equity_path
