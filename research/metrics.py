"""Gemeinsame Kennzahlen für jeden Kandidaten."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Ledger:
    equity0: float
    equity: float = 0.0  # realisiertes Kapital (Cash)
    marked: float = 0.0  # Kapital inklusive offener Lage
    peak: float = 0.0
    max_dd: float = 0.0
    fees: float = 0.0
    maker_fees: float = 0.0
    taker_fees: float = 0.0
    funding: float = 0.0
    realized: float = 0.0
    trades: int = 0
    wins: int = 0
    profit_sum: float = 0.0
    loss_sum: float = 0.0
    exits: dict[str, int] = field(default_factory=dict)
    bars_in_market: int = 0
    bars: int = 0

    def __post_init__(self) -> None:
        self.equity = self.equity0
        self.marked = self.equity0
        self.peak = self.equity0

    def mark(self, equity: float) -> None:
        """Mark-to-Market: nur Spitze und Drawdown, das Cash bleibt unberührt."""
        self.marked = equity
        self.peak = max(self.peak, equity)
        if self.peak > 0:
            self.max_dd = max(self.max_dd, (self.peak - equity) / self.peak)

    def fee(self, amount: float, taker: bool) -> None:
        self.fees += amount
        if taker:
            self.taker_fees += amount
        else:
            self.maker_fees += amount

    def close_trade(self, pnl_after_costs: float, reason: str) -> None:
        self.trades += 1
        if pnl_after_costs > 0:
            self.wins += 1
            self.profit_sum += pnl_after_costs
        elif pnl_after_costs < 0:
            self.loss_sum += pnl_after_costs
        self.exits[reason] = self.exits.get(reason, 0) + 1

    def result(self, extra: dict | None = None) -> dict:
        out = {
            "net": self.marked - self.equity0,
            "end_equity": self.marked,
            "realized": self.realized,
            "fees": self.fees,
            "maker_fees": self.maker_fees,
            "taker_fees": self.taker_fees,
            "funding": self.funding,
            "max_drawdown_pct": self.max_dd * 100.0,
            "trades": self.trades,
            "wins": self.wins,
            "profit_factor": (self.profit_sum / abs(self.loss_sum)) if self.loss_sum < 0 else None,
            "exits": dict(self.exits),
            "bars": self.bars,
            "exposure_pct": (100.0 * self.bars_in_market / self.bars) if self.bars else 0.0,
        }
        if extra:
            out.update(extra)
        return out


def normalize_grid_result(raw: dict) -> dict:
    """Bringt das Ergebnis der Grid-Engine auf dieselben Schlüssel."""
    closed = raw.get("closed_grid_wins", 0) + raw.get("closed_grid_losses", 0)
    return {
        "net": raw["net"],
        "end_equity": raw["end_equity"],
        "realized": raw["realized"],
        "fees": raw["fees"],
        "maker_fees": raw["maker_fees"],
        "taker_fees": raw["taker_fees"],
        "funding": raw["funding"],
        "max_drawdown_pct": raw["max_drawdown_pct"],
        "trades": raw["grids_started"],
        "wins": raw.get("closed_grid_wins", 0),
        "profit_factor": raw.get("profit_factor"),
        "exits": raw.get("exits", {}),
        "bars": raw["bars"],
        "exposure_pct": None,
        "round_trips": raw.get("round_trips", 0),
        "closed": closed,
    }
