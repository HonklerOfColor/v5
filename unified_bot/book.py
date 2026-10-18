"""Virtuelle Unterkonten. PnL, Fees und Funding hängen an der Strategie, nicht am Symbol allein."""

from __future__ import annotations

from dataclasses import dataclass, field

from unified_bot.models import ClosedTrade, Fill, Position, WorkingOrder


@dataclass
class Ledger:
    strategy_id: str
    allocation: float
    realized: float = 0.0
    fees: float = 0.0
    funding: float = 0.0
    entries_today: dict[str, int] = field(default_factory=dict)
    last_stop_ms: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "allocation": self.allocation,
            "realized": self.realized,
            "fees": self.fees,
            "funding": self.funding,
            "entries_today": self.entries_today,
            "last_stop_ms": self.last_stop_ms,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Ledger":
        return cls(
            strategy_id=raw["strategy_id"],
            allocation=float(raw.get("allocation") or 0),
            realized=float(raw.get("realized") or 0),
            fees=float(raw.get("fees") or 0),
            funding=float(raw.get("funding") or 0),
            entries_today={str(k): int(v) for k, v in (raw.get("entries_today") or {}).items()},
            last_stop_ms={str(k): int(v) for k, v in (raw.get("last_stop_ms") or {}).items()},
        )


class Book:
    def __init__(self, anchor: float, allocations: dict[str, float]):
        self.anchor = anchor
        self.ledgers = {
            strategy_id: Ledger(strategy_id, allocation)
            for strategy_id, allocation in allocations.items()
        }
        self.positions: list[Position] = []
        self.orders: dict[str, WorkingOrder] = {}
        self.closed: list[ClosedTrade] = []
        self.locks: dict[str, str] = {}
        self.oid_seq: dict[str, int] = {strategy_id: 0 for strategy_id in allocations}

    def ledger(self, strategy_id: str) -> Ledger:
        return self.ledgers[strategy_id]

    def next_seq(self, strategy_id: str) -> int:
        self.oid_seq[strategy_id] = self.oid_seq.get(strategy_id, 0) + 1
        return self.oid_seq[strategy_id]

    def sleeve_cash(self, strategy_id: str) -> float:
        ledger = self.ledger(strategy_id)
        return self.anchor * ledger.allocation + ledger.realized - ledger.fees - ledger.funding

    def used_margin(self, strategy_id: str, marks: dict[str, float]) -> float:
        margin = 0.0
        for pos in self.positions:
            if pos.strategy_id != strategy_id or pos.qty <= 0:
                continue
            mark = marks.get(pos.symbol) or pos.entry
            margin += pos.qty * mark / max(pos.leverage, 1)
        for order in self.orders.values():
            if order.strategy_id != strategy_id or order.purpose != "open":
                continue
            price = order.price or marks.get(order.symbol) or 0.0
            margin += order.size * price / max(order.leverage, 1)
        return margin

    def free_margin(self, strategy_id: str, marks: dict[str, float]) -> float:
        return self.sleeve_cash(strategy_id) - self.used_margin(strategy_id, marks)

    def unrealized(self, strategy_id: str | None, marks: dict[str, float]) -> float:
        total = 0.0
        for pos in self.positions:
            if strategy_id is not None and pos.strategy_id != strategy_id:
                continue
            if pos.qty <= 0:
                continue
            mark = marks.get(pos.symbol)
            if mark is None or mark <= 0:
                continue
            if pos.side == "long":
                total += (mark - pos.entry) * pos.qty
            else:
                total += (pos.entry - mark) * pos.qty
        return total

    def account_equity(self, marks: dict[str, float]) -> float:
        pnl = 0.0
        for ledger in self.ledgers.values():
            pnl += ledger.realized - ledger.fees - ledger.funding
        return self.anchor + pnl + self.unrealized(None, marks)

    def open_notional(self, marks: dict[str, float]) -> float:
        total = 0.0
        for pos in self.positions:
            mark = marks.get(pos.symbol) or pos.entry
            total += abs(pos.qty * mark)
        for order in self.orders.values():
            if order.purpose != "open":
                continue
            price = order.price or marks.get(order.symbol) or 0.0
            total += abs(order.size * price)
        return total

    def positions_of(self, strategy_id: str) -> list[Position]:
        return [pos for pos in self.positions if pos.strategy_id == strategy_id and pos.qty > 0]

    def find_position(self, strategy_id: str, symbol: str, side: str) -> Position | None:
        for pos in self.positions:
            if pos.strategy_id == strategy_id and pos.symbol == symbol and pos.side == side and pos.qty > 0:
                return pos
        return None

    def rebuild_locks(self) -> None:
        locks: dict[str, str] = {}
        for pos in self.positions:
            if pos.qty <= 0:
                continue
            locks.setdefault(pos.symbol, pos.strategy_id)
        for order in self.orders.values():
            if order.purpose != "open":
                continue
            locks.setdefault(order.symbol, order.strategy_id)
        self.locks = locks

    def symbol_owner(self, symbol: str) -> str | None:
        return self.locks.get(symbol)

    def entries_today(self, strategy_id: str, day: str) -> int:
        return int(self.ledger(strategy_id).entries_today.get(day, 0))

    def note_entry(self, strategy_id: str, day: str) -> None:
        ledger = self.ledger(strategy_id)
        ledger.entries_today[day] = ledger.entries_today.get(day, 0) + 1

    def note_stop(self, strategy_id: str, symbol: str, ts_ms: int) -> None:
        self.ledger(strategy_id).last_stop_ms[symbol] = ts_ms

    def add_order(self, order: WorkingOrder) -> None:
        self.orders[order.client_oid] = order
        if order.purpose == "open":
            self.locks[order.symbol] = order.strategy_id

    def drop_order(self, client_oid: str) -> None:
        self.orders.pop(client_oid, None)
        self.rebuild_locks()

    def apply_fill(self, fill: Fill) -> ClosedTrade | None:
        order = self.orders.get(fill.client_oid)
        stop = order.stop if order is not None else None
        take_profit = order.take_profit if order is not None else None
        if order is not None:
            order.filled += fill.qty
            left = order.size - order.filled
            if left <= max(1e-12, order.size * 1e-8):
                self.orders.pop(fill.client_oid, None)
            else:
                order.size = left
        ledger = self.ledger(fill.strategy_id)
        ledger.fees += fill.fee
        trade: ClosedTrade | None = None
        if fill.purpose == "open":
            self._add_open(fill, stop, take_profit)
            self.note_entry(fill.strategy_id, _day(fill.ts_ms))
        else:
            trade = self._reduce(fill)
        self.rebuild_locks()
        return trade

    def _add_open(self, fill: Fill, stop: float | None, take_profit: float | None) -> None:
        pos = self.find_position(fill.strategy_id, fill.symbol, fill.position_side)
        if pos is None:
            self.positions.append(
                Position(
                    strategy_id=fill.strategy_id,
                    symbol=fill.symbol,
                    side=fill.position_side,
                    qty=fill.qty,
                    entry=fill.price,
                    leverage=fill.leverage,
                    opened_ms=fill.ts_ms,
                    initial_qty=fill.qty,
                    client_oid=fill.client_oid,
                    market=fill.market,
                    stop=stop,
                    take_profit=take_profit,
                )
            )
            return
        new_qty = pos.qty + fill.qty
        pos.entry = (pos.entry * pos.qty + fill.price * fill.qty) / new_qty
        pos.qty = new_qty
        pos.initial_qty += fill.qty
        if stop is not None:
            pos.stop = stop
        if take_profit is not None:
            pos.take_profit = take_profit

    def remember_protection(
        self,
        strategy_id: str,
        symbol: str,
        side: str,
        stop: float | None,
        take_profit: float | None,
    ) -> None:
        pos = self.find_position(strategy_id, symbol, side)
        if pos is None:
            return
        if stop is not None:
            pos.stop = stop
        if take_profit is not None:
            pos.take_profit = take_profit

    def _reduce(self, fill: Fill) -> ClosedTrade | None:
        pos = self.find_position(fill.strategy_id, fill.symbol, fill.position_side)
        if pos is None or pos.qty <= 0 or fill.qty <= 0:
            return None
        take = min(fill.qty, pos.qty)
        if pos.side == "long":
            gross = (fill.price - pos.entry) * take
        else:
            gross = (pos.entry - fill.price) * take
        funding = 0.0
        if pos.qty > 0 and pos.funding_accrued:
            funding = pos.funding_accrued * (take / pos.qty)
            pos.funding_accrued -= funding
        self.ledger(fill.strategy_id).realized += gross
        net = gross - fill.fee - funding
        trade = ClosedTrade(
            strategy=fill.strategy_id,
            symbol=fill.symbol,
            side=pos.side,
            qty=take,
            entry=pos.entry,
            exit=fill.price,
            gross_pnl=gross,
            fees=fill.fee,
            funding=funding,
            net_pnl=net,
            opened_ms=pos.opened_ms,
            closed_ms=fill.ts_ms,
            exit_reason=fill.reason or fill.purpose,
            client_oid=fill.client_oid,
            market=fill.market,
        )
        self.closed.append(trade)
        if len(self.closed) > 2000:
            self.closed = self.closed[-2000:]
        pos.qty -= take
        if pos.qty <= 1e-12:
            if fill.reason in ("sl", "stop", "time_stop") or gross < 0:
                self.note_stop(fill.strategy_id, fill.symbol, fill.ts_ms)
            self.positions = [
                item for item in self.positions
                if not (
                    item.strategy_id == pos.strategy_id
                    and item.symbol == pos.symbol
                    and item.side == pos.side
                )
            ]
        return trade

    def replace_strategy_symbol(self, strategy_id: str, symbol: str, positions: list[Position]) -> None:
        self.positions = [
            pos for pos in self.positions
            if not (pos.strategy_id == strategy_id and pos.symbol == symbol)
        ]
        self.positions.extend(positions)
        self.rebuild_locks()

    def note_funding(self, strategy_id: str, symbol: str, charge: float) -> None:
        if charge <= 0:
            return
        self.ledger(strategy_id).funding += charge
        attributed = [
            pos for pos in self.positions
            if pos.strategy_id == strategy_id and pos.symbol == symbol and pos.qty > 0
        ]
        base = sum(pos.qty for pos in attributed) or 1.0
        for pos in attributed:
            pos.funding_accrued += charge * (pos.qty / base)

    def accrue_funding(self, strategy_id: str, symbol: str, mark: float, rate: float) -> float:
        longs = sum(
            pos.qty for pos in self.positions
            if pos.strategy_id == strategy_id and pos.symbol == symbol and pos.side == "long"
        )
        shorts = sum(
            pos.qty for pos in self.positions
            if pos.strategy_id == strategy_id and pos.symbol == symbol and pos.side == "short"
        )
        net = abs(longs - shorts)
        charge = net * mark * rate
        if charge <= 0:
            return 0.0
        self.ledger(strategy_id).funding += charge
        attributed = [pos for pos in self.positions if pos.strategy_id == strategy_id and pos.symbol == symbol and pos.qty > 0]
        base = sum(pos.qty for pos in attributed) or 1.0
        for pos in attributed:
            pos.funding_accrued += charge * (pos.qty / base)
        return charge

    def sync_allocations(self, allocations: dict[str, float]) -> None:
        for strategy_id, allocation in allocations.items():
            if strategy_id not in self.ledgers:
                self.ledgers[strategy_id] = Ledger(strategy_id, allocation)
            else:
                self.ledgers[strategy_id].allocation = allocation

    def to_dict(self) -> dict:
        return {
            "anchor": self.anchor,
            "ledgers": {key: ledger.to_dict() for key, ledger in self.ledgers.items()},
            "positions": [pos.to_dict() for pos in self.positions],
            "orders": [order.to_dict() for order in self.orders.values()],
            "closed": [trade.to_dict() for trade in self.closed],
            "locks": self.locks,
            "oid_seq": self.oid_seq,
        }

    @classmethod
    def from_dict(cls, raw: dict, allocations: dict[str, float]) -> "Book":
        book = cls(float(raw.get("anchor") or 0), allocations)
        ledgers = raw.get("ledgers") or {}
        for strategy_id, allocation in allocations.items():
            if strategy_id in ledgers:
                book.ledgers[strategy_id] = Ledger.from_dict(ledgers[strategy_id])
                book.ledgers[strategy_id].allocation = allocation
        book.positions = [Position.from_dict(item) for item in raw.get("positions") or []]
        for item in raw.get("orders") or []:
            order = WorkingOrder.from_dict(item)
            book.orders[order.client_oid] = order
        book.closed = [ClosedTrade.from_dict(item) for item in raw.get("closed") or []]
        book.oid_seq = {str(k): int(v) for k, v in (raw.get("oid_seq") or {}).items()}
        book.rebuild_locks()
        return book


def _day(ts_ms: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date().isoformat()
