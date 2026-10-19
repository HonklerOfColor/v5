"""Virtuelles Spot-Ledger je Modul: USDT plus Coin-Bestände. Unabhängig vom Perp-Buch."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from unified_bot.spot.candles import day_iso, day_of_ms


@dataclass
class SpotTrade:
    ts_ms: int
    symbol: str
    side: str          # buy | sell
    qty: float
    price: float       # Ausführungspreis inkl. Slippage
    fee: float         # USDT
    value_usdt: float  # qty × price
    reason: str

    @property
    def day(self) -> str:
        return day_iso(day_of_ms(self.ts_ms))

    def to_dict(self) -> dict:
        return {
            "ts_ms": self.ts_ms,
            "day": self.day,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "price": self.price,
            "fee": self.fee,
            "value_usdt": self.value_usdt,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "SpotTrade":
        return cls(
            ts_ms=int(raw["ts_ms"]),
            symbol=str(raw["symbol"]),
            side=str(raw["side"]),
            qty=float(raw["qty"]),
            price=float(raw["price"]),
            fee=float(raw.get("fee") or 0.0),
            value_usdt=float(raw.get("value_usdt") or 0.0),
            reason=str(raw.get("reason") or ""),
        )


@dataclass
class SpotLedger:
    start_capital: float
    cash: float
    holdings: dict[str, float] = field(default_factory=dict)
    last_prices: dict[str, float] = field(default_factory=dict)
    trades: list[SpotTrade] = field(default_factory=list)
    fees_total: float = 0.0

    @classmethod
    def fresh(cls, start_capital: float) -> "SpotLedger":
        return cls(start_capital=start_capital, cash=start_capital)

    def qty(self, symbol: str) -> float:
        return float(self.holdings.get(symbol, 0.0))

    def price_for(self, symbol: str, prices: dict[str, float] | None) -> float | None:
        value = (prices or {}).get(symbol)
        if value is not None and value == value and value > 0:
            return float(value)
        value = self.last_prices.get(symbol)
        if value is not None and value > 0:
            return float(value)
        return None

    def position_values(self, prices: dict[str, float] | None) -> dict[str, float]:
        out: dict[str, float] = {}
        for symbol, qty in self.holdings.items():
            if qty <= 0:
                continue
            price = self.price_for(symbol, prices)
            out[symbol] = qty * price if price else 0.0
        return out

    def equity(self, prices: dict[str, float] | None) -> float:
        return self.cash + math.fsum(self.position_values(prices).values())

    def exposure(self, prices: dict[str, float] | None) -> float:
        equity = self.equity(prices)
        if equity <= 0:
            return 0.0
        return math.fsum(self.position_values(prices).values()) / equity

    def record(self, trade: SpotTrade) -> None:
        if trade.side == "buy":
            self.cash -= trade.value_usdt + trade.fee
            self.holdings[trade.symbol] = self.qty(trade.symbol) + trade.qty
        else:
            self.cash += trade.value_usdt - trade.fee
            left = self.qty(trade.symbol) - trade.qty
            if left <= 1e-12:
                self.holdings.pop(trade.symbol, None)
            else:
                self.holdings[trade.symbol] = left
        self.fees_total += trade.fee
        self.last_prices[trade.symbol] = trade.price
        self.trades.append(trade)

    def trades_in_month(self, month: str) -> int:
        return sum(1 for trade in self.trades if trade.day[:7] == month)

    def to_dict(self) -> dict:
        return {
            "start_capital": self.start_capital,
            "cash": self.cash,
            "holdings": dict(self.holdings),
            "last_prices": dict(self.last_prices),
            "fees_total": self.fees_total,
            "trades": [trade.to_dict() for trade in self.trades],
        }

    @classmethod
    def from_dict(cls, raw: dict | None, start_capital: float) -> "SpotLedger":
        if not raw:
            return cls.fresh(start_capital)
        return cls(
            start_capital=float(raw.get("start_capital", start_capital)),
            cash=float(raw.get("cash", start_capital)),
            holdings={str(k): float(v) for k, v in (raw.get("holdings") or {}).items() if float(v) > 0},
            last_prices={str(k): float(v) for k, v in (raw.get("last_prices") or {}).items()},
            trades=[SpotTrade.from_dict(item) for item in raw.get("trades") or []],
            fees_total=float(raw.get("fees_total") or 0.0),
        )
