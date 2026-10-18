"""Order-Intents und Kontosätze. Strategien erzeugen Intents, sie senden keine Orders."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OrderIntent:
    strategy_id: str
    symbol: str
    market: str  # perp | spot
    book_side: str  # buy | sell
    position_side: str  # long | short
    purpose: str  # open | close | reduce | emergency
    order_type: str  # limit | market
    size: float
    price: float | None = None
    leverage: int = 1
    post_only: bool | None = None  # None = Limit ist Post-only
    client_oid: str = ""
    stop: float | None = None
    take_profit: float | None = None
    expected_tp_pct: float | None = None
    exit_is_maker: bool | None = None
    reason: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def reduce_only(self) -> bool:
        return self.purpose in ("close", "reduce", "emergency")

    @property
    def wants_post_only(self) -> bool:
        if self.order_type != "limit":
            return False
        if self.post_only is None:
            return True
        return bool(self.post_only)


@dataclass
class CancelIntent:
    strategy_id: str
    symbol: str
    client_oid: str
    order_id: str | None = None


@dataclass
class StopUpdate:
    strategy_id: str
    symbol: str
    position_side: str
    new_stop: float
    reason: str


@dataclass
class CyclePlan:
    orders: list[OrderIntent] = field(default_factory=list)
    cancels: list[CancelIntent] = field(default_factory=list)
    stops: list[StopUpdate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class Position:
    strategy_id: str
    symbol: str
    side: str
    qty: float
    entry: float
    leverage: int
    opened_ms: int
    stop: float | None = None
    take_profit: float | None = None
    peak_roe: float = 0.0
    initial_qty: float = 0.0
    partial_done: bool = False
    breakeven_armed: bool = False
    funding_accrued: float = 0.0
    client_oid: str = ""
    market: str = "perp"
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "entry": self.entry,
            "leverage": self.leverage,
            "opened_ms": self.opened_ms,
            "stop": self.stop,
            "take_profit": self.take_profit,
            "peak_roe": self.peak_roe,
            "initial_qty": self.initial_qty,
            "partial_done": self.partial_done,
            "breakeven_armed": self.breakeven_armed,
            "funding_accrued": self.funding_accrued,
            "client_oid": self.client_oid,
            "market": self.market,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Position":
        return cls(
            strategy_id=raw["strategy_id"],
            symbol=raw["symbol"],
            side=raw["side"],
            qty=float(raw["qty"]),
            entry=float(raw["entry"]),
            leverage=int(raw["leverage"]),
            opened_ms=int(raw.get("opened_ms") or 0),
            stop=None if raw.get("stop") in (None, "") else float(raw["stop"]),
            take_profit=None if raw.get("take_profit") in (None, "") else float(raw["take_profit"]),
            peak_roe=float(raw.get("peak_roe") or 0),
            initial_qty=float(raw.get("initial_qty") or raw.get("qty") or 0),
            partial_done=bool(raw.get("partial_done", False)),
            breakeven_armed=bool(raw.get("breakeven_armed", False)),
            funding_accrued=float(raw.get("funding_accrued") or 0),
            client_oid=str(raw.get("client_oid") or ""),
            market=str(raw.get("market") or "perp"),
            extra=dict(raw.get("extra") or {}),
        )


@dataclass
class WorkingOrder:
    strategy_id: str
    client_oid: str
    order_id: str | None
    symbol: str
    market: str
    book_side: str
    position_side: str
    purpose: str
    order_type: str
    price: float | None
    size: float
    filled: float
    leverage: int
    post_only: bool
    placed_ms: int
    stop: float | None = None
    take_profit: float | None = None
    expected_tp_pct: float | None = None
    reason: str = ""
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "client_oid": self.client_oid,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "market": self.market,
            "book_side": self.book_side,
            "position_side": self.position_side,
            "purpose": self.purpose,
            "order_type": self.order_type,
            "price": self.price,
            "size": self.size,
            "filled": self.filled,
            "leverage": self.leverage,
            "post_only": self.post_only,
            "placed_ms": self.placed_ms,
            "stop": self.stop,
            "take_profit": self.take_profit,
            "expected_tp_pct": self.expected_tp_pct,
            "reason": self.reason,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "WorkingOrder":
        return cls(
            strategy_id=raw["strategy_id"],
            client_oid=raw["client_oid"],
            order_id=raw.get("order_id"),
            symbol=raw["symbol"],
            market=str(raw.get("market") or "perp"),
            book_side=raw["book_side"],
            position_side=raw["position_side"],
            purpose=raw["purpose"],
            order_type=raw["order_type"],
            price=None if raw.get("price") in (None, "") else float(raw["price"]),
            size=float(raw["size"]),
            filled=float(raw.get("filled") or 0),
            leverage=int(raw.get("leverage") or 1),
            post_only=bool(raw.get("post_only", True)),
            placed_ms=int(raw.get("placed_ms") or 0),
            stop=None if raw.get("stop") in (None, "") else float(raw["stop"]),
            take_profit=None if raw.get("take_profit") in (None, "") else float(raw["take_profit"]),
            expected_tp_pct=None
            if raw.get("expected_tp_pct") in (None, "")
            else float(raw["expected_tp_pct"]),
            reason=str(raw.get("reason") or ""),
            meta=dict(raw.get("meta") or {}),
        )


@dataclass
class ClosedTrade:
    strategy: str
    symbol: str
    side: str
    qty: float
    entry: float
    exit: float
    gross_pnl: float
    fees: float
    funding: float
    net_pnl: float
    opened_ms: int
    closed_ms: int
    exit_reason: str
    client_oid: str
    market: str = "perp"

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "entry": self.entry,
            "exit": self.exit,
            "gross_pnl": self.gross_pnl,
            "fees": self.fees,
            "funding": self.funding,
            "net_pnl": self.net_pnl,
            "opened_ms": self.opened_ms,
            "closed_ms": self.closed_ms,
            "exit_reason": self.exit_reason,
            "client_oid": self.client_oid,
            "market": self.market,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "ClosedTrade":
        return cls(
            strategy=raw["strategy"],
            symbol=raw["symbol"],
            side=raw["side"],
            qty=float(raw["qty"]),
            entry=float(raw["entry"]),
            exit=float(raw["exit"]),
            gross_pnl=float(raw["gross_pnl"]),
            fees=float(raw.get("fees") or 0),
            funding=float(raw.get("funding") or 0),
            net_pnl=float(raw["net_pnl"]),
            opened_ms=int(raw.get("opened_ms") or 0),
            closed_ms=int(raw.get("closed_ms") or 0),
            exit_reason=str(raw.get("exit_reason") or ""),
            client_oid=str(raw.get("client_oid") or ""),
            market=str(raw.get("market") or "perp"),
        )


@dataclass
class Fill:
    strategy_id: str
    client_oid: str
    symbol: str
    book_side: str
    position_side: str
    purpose: str
    price: float
    qty: float
    fee: float
    fee_rate: float
    liquidity: str
    ts_ms: int
    leverage: int
    reason: str = ""
    market: str = "perp"


@dataclass
class SubmitResult:
    accepted: bool
    reason: str
    client_oid: str = ""
    payload: dict | None = None
    fill: Fill | None = None
