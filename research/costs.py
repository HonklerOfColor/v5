"""Kostenmodell, identisch für alle Kandidaten. Werte wie im Grid-Backtest.

Funding: ohne hinterlegte Raten gilt die Pauschale 0,01 % je 8h auf die
Nettoposition, immer als Kosten (wie im Grid-Backtest). Mit hinterlegten
Raten (research.funding) wird das Vorzeichen beachtet: Long zahlt bei positiver
Rate, Short bekommt sie. Fehlt eine Rate zu einem Zeitpunkt, fällt nichts an.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Costs:
    maker_fee: float = 0.0002
    taker_fee: float = 0.0006
    taker_slippage_pct: float = 0.0002
    funding_rate_8h: float = 0.0001  # Pauschale auf |Netto-Position|, kein historischer Satz
    funding_books: dict[str, dict[int, float]] = field(default_factory=dict, compare=False, hash=False)

    def taker_buy(self, price: float) -> float:
        return price * (1.0 + self.taker_slippage_pct)

    def taker_sell(self, price: float) -> float:
        return price * (1.0 - self.taker_slippage_pct)

    @property
    def has_real_funding(self) -> bool:
        return bool(self.funding_books)

    def funding_charge(self, symbol: str, ts_ms: int, side: str, notional: float) -> float:
        """Kosten (positiv) oder Ertrag (negativ) zum Zeitpunkt ts_ms, 0 wenn kein Funding fällig."""
        book = self.funding_books.get(symbol)
        if book is None:
            if not funding_due(ts_ms):
                return 0.0
            return notional * self.funding_rate_8h
        rate = book.get(ts_ms)
        if rate is None:
            return 0.0
        signed = rate if side == "long" else -rate
        return notional * signed


def funding_due(ts_ms: int) -> bool:
    return ts_ms % (8 * 3_600_000) == 0
