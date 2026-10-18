"""Grid-Zustand ohne I/O. Backtest, Paper und Live benutzen dieselbe Logik."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from gridbot.candles import Candle
from gridbot.params import GridParams
from gridbot.payloads import Intent
from gridbot.specs import ContractSpec, ceil_to_step, floor_to_step, snap_price


@dataclass
class Lot:
    side: str
    qty: float
    entry: float
    level: int
    tp_level: int | None
    closed: bool = False

    def to_dict(self) -> dict:
        return {
            "side": self.side,
            "qty": self.qty,
            "entry": self.entry,
            "level": self.level,
            "tp_level": self.tp_level,
            "closed": self.closed,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Lot":
        tp = raw.get("tp_level")
        return cls(
            side=raw["side"],
            qty=float(raw["qty"]),
            entry=float(raw["entry"]),
            level=int(raw["level"]),
            tp_level=None if tp is None else int(tp),
            closed=bool(raw.get("closed", False)),
        )


@dataclass
class RestingOrder:
    client_oid: str
    order_id: str | None
    level: int
    book_side: str
    position_side: str
    purpose: str
    price: float
    size: float
    filled_ack: float = 0.0

    def to_dict(self) -> dict:
        return {
            "client_oid": self.client_oid,
            "order_id": self.order_id,
            "level": self.level,
            "book_side": self.book_side,
            "position_side": self.position_side,
            "purpose": self.purpose,
            "price": self.price,
            "size": self.size,
            "filled_ack": self.filled_ack,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "RestingOrder":
        return cls(
            client_oid=raw["client_oid"],
            order_id=raw.get("order_id"),
            level=int(raw["level"]),
            book_side=raw["book_side"],
            position_side=raw["position_side"],
            purpose=raw["purpose"],
            price=float(raw["price"]),
            size=float(raw["size"]),
            filled_ack=float(raw.get("filled_ack", 0) or 0),
        )

    def key(self) -> tuple:
        return (self.level, self.purpose, self.position_side)


@dataclass
class Plan:
    symbol: str
    lower: float
    upper: float
    levels: list[float]
    qty: float
    leverage: int
    spacing_pct: float
    min_spacing_pct: float
    hard_stop_usdt: float


@dataclass
class ActiveGrid:
    symbol: str
    lower: float
    upper: float
    levels: list[float]
    qty: float
    leverage: int
    spacing_pct: float
    hard_stop_usdt: float
    created_ms: int = 0
    realized: float = 0.0
    fees: float = 0.0
    funding: float = 0.0
    lots: list[Lot] = field(default_factory=list)
    orders: dict[str, RestingOrder] = field(default_factory=dict)
    oid_seq: int = 0

    @classmethod
    def from_plan(cls, plan: Plan, created_ms: int = 0) -> "ActiveGrid":
        return cls(
            symbol=plan.symbol,
            lower=plan.lower,
            upper=plan.upper,
            levels=list(plan.levels),
            qty=plan.qty,
            leverage=plan.leverage,
            spacing_pct=plan.spacing_pct,
            hard_stop_usdt=plan.hard_stop_usdt,
            created_ms=created_ms,
        )

    def next_oid(self, level: int, purpose: str) -> str:
        """Bitget lehnt doppelte clientOids ab. Symbol und Startzeit machen die Id je Grid eindeutig."""
        self.oid_seq += 1
        tag = {"open": "o", "close": "c", "emergency": "e"}.get(purpose, "x")
        return f"grd{self.oid_prefix()}{self.oid_seq:06d}{level:02d}{tag}"

    def oid_prefix(self) -> str:
        # Startzeit fest 7 Stellen breit, damit Kürzel und Zeit nicht ineinanderlaufen.
        root = self.symbol[:-4] if self.symbol.endswith("USDT") else self.symbol
        return f"{root[:6].lower()}{_base36(self.created_ms // 1000).rjust(7, '0')}"

    @property
    def long_qty(self) -> float:
        return sum(lot.qty for lot in self.lots if lot.side == "long" and not lot.closed)

    @property
    def short_qty(self) -> float:
        return sum(lot.qty for lot in self.lots if lot.side == "short" and not lot.closed)

    def open_lot_count(self, side: str) -> int:
        return sum(1 for lot in self.lots if lot.side == side and not lot.closed and lot.qty > 0)

    def unrealized(self, mark: float) -> float:
        pnl = 0.0
        for lot in self.lots:
            if lot.closed or lot.qty <= 0:
                continue
            if lot.side == "long":
                pnl += (mark - lot.entry) * lot.qty
            else:
                pnl += (lot.entry - mark) * lot.qty
        return pnl

    def net_pnl(self, mark: float) -> float:
        return self.realized + self.unrealized(mark) - self.fees - self.funding

    def outside(self, close: float, buffer_pct: float) -> bool:
        return close > self.upper * (1.0 + buffer_pct) or close < self.lower * (1.0 - buffer_pct)

    def _has_open_lot_at(self, side: str, level: int) -> bool:
        return any(
            lot.side == side and not lot.closed and lot.level == level and lot.qty > 0
            for lot in self.lots
        )

    def desired_intents(self, mark: float, equity: float, spec: ContractSpec, params: GridParams) -> list[Intent]:
        intents: list[Intent] = []
        occupied: set[int] = set()
        groups: dict[tuple[str, int], float] = {}
        for lot in self.lots:
            if lot.closed or lot.tp_level is None or lot.qty <= 0:
                continue
            key = (lot.side, lot.tp_level)
            groups[key] = groups.get(key, 0.0) + lot.qty
        for (side, level), qty in sorted(groups.items()):
            book = "sell" if side == "long" else "buy"
            intents.append(self._intent(book, "close", side, level, self.levels[level], qty))
            occupied.add(level)

        budget = max(0.0, equity * params.max_margin_fraction - equity * 0.01)
        pos_margin = (self.long_qty + self.short_qty) * mark / self.leverage
        free = budget - pos_margin

        def add_opens(side: str, book: str, indexes: list[int]) -> None:
            nonlocal free
            slots = params.max_inventory_levels - self.open_lot_count(side)
            indexes = sorted(indexes, key=lambda i: abs(self.levels[i] - mark))
            for level in indexes:
                if slots <= 0:
                    break
                if level in occupied or self._has_open_lot_at(side, level):
                    continue
                price = self.levels[level]
                notional = self.qty * price
                if notional + 1e-9 < spec.min_notional:
                    continue
                margin = notional / self.leverage
                if margin > free + 1e-9:
                    continue
                intents.append(self._intent(book, "open", side, level, price, self.qty))
                occupied.add(level)
                free -= margin
                slots -= 1

        buy_levels = [
            i for i in range(len(self.levels) - 1)
            if self.levels[i] < mark
        ]
        sell_levels = [
            i for i in range(1, len(self.levels))
            if self.levels[i] > mark
        ]
        add_opens("long", "buy", buy_levels)
        add_opens("short", "sell", sell_levels)
        return intents

    def _intent(self, book: str, purpose: str, position_side: str, level: int, price: float | None, size: float) -> Intent:
        return Intent(
            symbol=self.symbol,
            book_side=book,
            purpose=purpose,
            position_side=position_side,
            level=level,
            price=price,
            size=size,
            order_type="limit",
            client_oid="",
        )

    def sync_orders(self, mark: float, equity: float, spec: ContractSpec, params: GridParams) -> list[RestingOrder]:
        """Gleicht liegende Orders mit dem Soll ab. Neue Orders füllen erst später."""
        desired = self.desired_intents(mark, equity, spec, params)
        wanted: dict[tuple, Intent] = {}
        for intent in desired:
            wanted[intent_key(intent)] = intent
        have: dict[tuple, RestingOrder] = {}
        for order in list(self.orders.values()):
            have[order.key()] = order
        cancelled: list[RestingOrder] = []
        for key, order in have.items():
            intent = wanted.get(key)
            if intent is None or _changed(order, intent, spec):
                self.orders.pop(order.client_oid, None)
                cancelled.append(order)
                continue
            wanted.pop(key)
        for intent in wanted.values():
            intent.client_oid = self.next_oid(intent.level, intent.purpose)
            order = RestingOrder(
                client_oid=intent.client_oid,
                order_id=None,
                level=intent.level,
                book_side=intent.book_side,
                position_side=intent.position_side,
                purpose=intent.purpose,
                price=float(intent.price or 0),
                size=intent.size,
                filled_ack=0.0,
            )
            self.orders[order.client_oid] = order
        return cancelled

    def apply_fill(self, order: RestingOrder, fill_price: float, fill_qty: float, fee_rate: float) -> None:
        qty = min(fill_qty, order.size)
        if qty <= 0:
            return
        self.fees += fill_price * qty * fee_rate
        left = order.size - qty
        if left <= max(1e-12, order.size * 1e-8):
            self.orders.pop(order.client_oid, None)
        else:
            order.size = left
        if order.purpose == "open":
            tp = order.level + 1 if order.position_side == "long" else order.level - 1
            if tp < 0 or tp >= len(self.levels):
                tp_level = None
            else:
                tp_level = tp
            self.lots.append(
                Lot(
                    side=order.position_side,
                    qty=qty,
                    entry=fill_price,
                    level=order.level,
                    tp_level=tp_level,
                )
            )
            return
        remaining = qty
        for lot in self.lots:
            if remaining <= 1e-12:
                break
            if lot.closed or lot.side != order.position_side or lot.tp_level != order.level:
                continue
            take = min(remaining, lot.qty)
            if lot.side == "long":
                self.realized += (fill_price - lot.entry) * take
            else:
                self.realized += (lot.entry - fill_price) * take
            lot.qty -= take
            remaining -= take
            if lot.qty <= 1e-12:
                lot.closed = True
                lot.qty = 0.0

    def flatten(self, mark: float, slippage: float, taker_fee: float) -> None:
        """Notfall-Exit zum Taker-Preis. Grid-Orders werden verworfen."""
        self.orders.clear()
        for lot in self.lots:
            if lot.closed or lot.qty <= 0:
                continue
            if lot.side == "long":
                price = mark * (1.0 - slippage)
                self.realized += (price - lot.entry) * lot.qty
            else:
                price = mark * (1.0 + slippage)
                self.realized += (lot.entry - price) * lot.qty
            self.fees += price * lot.qty * taker_fee
            lot.closed = True
            lot.qty = 0.0

    def emergency_intents(self) -> list[Intent]:
        intents: list[Intent] = []
        if self.long_qty > 0:
            intents.append(
                Intent(
                    symbol=self.symbol,
                    book_side="sell",
                    purpose="emergency",
                    position_side="long",
                    level=-1,
                    price=None,
                    size=self.long_qty,
                    order_type="market",
                    client_oid=self.next_oid(0, "emergency"),
                )
            )
        if self.short_qty > 0:
            intents.append(
                Intent(
                    symbol=self.symbol,
                    book_side="buy",
                    purpose="emergency",
                    position_side="short",
                    level=-1,
                    price=None,
                    size=self.short_qty,
                    order_type="market",
                    client_oid=self.next_oid(0, "emergency"),
                )
            )
        return intents

    def charge_funding(self, mark: float, rate: float) -> None:
        net = abs(self.long_qty - self.short_qty)
        self.funding += net * mark * rate

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "lower": self.lower,
            "upper": self.upper,
            "levels": self.levels,
            "qty": self.qty,
            "leverage": self.leverage,
            "spacing_pct": self.spacing_pct,
            "hard_stop_usdt": self.hard_stop_usdt,
            "created_ms": self.created_ms,
            "realized": self.realized,
            "fees": self.fees,
            "funding": self.funding,
            "lots": [lot.to_dict() for lot in self.lots],
            "orders": [order.to_dict() for order in self.orders.values()],
            "oid_seq": self.oid_seq,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "ActiveGrid":
        grid = cls(
            symbol=raw["symbol"],
            lower=float(raw["lower"]),
            upper=float(raw["upper"]),
            levels=[float(item) for item in raw["levels"]],
            qty=float(raw["qty"]),
            leverage=int(raw["leverage"]),
            spacing_pct=float(raw["spacing_pct"]),
            hard_stop_usdt=float(raw["hard_stop_usdt"]),
            created_ms=int(raw.get("created_ms", 0)),
            realized=float(raw.get("realized", 0)),
            fees=float(raw.get("fees", 0)),
            funding=float(raw.get("funding", 0)),
            oid_seq=int(raw.get("oid_seq", 0)),
        )
        grid.lots = [Lot.from_dict(item) for item in raw.get("lots", [])]
        for item in raw.get("orders", []):
            order = RestingOrder.from_dict(item)
            grid.orders[order.client_oid] = order
        return grid


def _base36(value: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    value = max(0, int(value))
    out = ""
    while True:
        value, rest = divmod(value, 36)
        out = digits[rest] + out
        if value == 0:
            return out


def intent_key(intent: Intent) -> tuple:
    return (intent.level, intent.purpose, intent.position_side)


def _changed(order: RestingOrder, intent: Intent, spec: ContractSpec) -> bool:
    if abs(order.size - intent.size) > spec.qty_step * 0.5:
        return True
    if intent.price is None:
        return True
    return abs(order.price - intent.price) > spec.price_tick * 0.5


def _spacing_ok(levels: list[float], min_spacing_pct: float) -> bool:
    mid = (levels[0] + levels[-1]) / 2.0
    if mid <= 0:
        return False
    for left, right in zip(levels, levels[1:]):
        if (right - left) / mid + 1e-12 < min_spacing_pct:
            return False
    return True


def choose_levels(lower: float, upper: float, tick: float, requested: int, min_levels: int, min_spacing_pct: float) -> list[float] | None:
    mid = (lower + upper) / 2.0
    width = upper - lower
    if mid <= 0 or width <= 0:
        return None
    max_gaps = int(math.floor(width / (mid * min_spacing_pct) + 1e-12))
    need = min_levels - 1
    if max_gaps < need:
        return None
    gaps = min(requested - 1, max_gaps)
    raw = [lower + width * i / gaps for i in range(gaps + 1)]
    snapped = [snap_price(price, tick) for price in raw]
    for i in range(1, len(snapped)):
        if snapped[i] <= snapped[i - 1]:
            snapped[i] = snap_price(snapped[i - 1] + tick, tick)
    if snapped[-1] < upper - tick:
        # Oberkante nicht unter das Swing-High ziehen, wenn der Tick es erlaubt.
        snapped[-1] = snap_price(max(snapped[-1], upper), tick)
    if not _spacing_ok(snapped, min_spacing_pct * 0.98):
        return None
    return snapped


def select_qty(
    equity: float,
    lower: float,
    upper: float,
    mark: float,
    levels: list[float],
    spec: ContractSpec,
    params: GridParams,
    leverage: int,
) -> float | None:
    buys = [price for price in levels if price < mark]
    sells = [price for price in levels if price > mark]
    if not buys or not sells:
        return None
    nearest_buy = max(buys)
    nearest_sell = min(sells)
    budget = equity * params.max_margin_fraction
    if budget <= 0 or mark <= 0:
        return None
    target_notional = max(spec.min_notional, equity * params.level_notional_fraction)
    pair_cap = budget * leverage / 2.0
    target_notional = min(target_notional, pair_cap)
    if target_notional + 1e-9 < spec.min_notional:
        return None
    qty = floor_to_step(target_notional / mark, spec.qty_step)
    min_qty_notional = spec.min_notional / min(nearest_buy, lower if lower > 0 else nearest_buy)
    needed = max(spec.min_qty, min_qty_notional)
    if qty + 1e-12 < needed:
        qty = ceil_to_step(needed, spec.qty_step)
    if qty + 1e-12 < spec.min_qty:
        return None
    for price in (nearest_buy, nearest_sell):
        if qty * price + 1e-9 < spec.min_notional:
            qty = ceil_to_step(spec.min_notional / price, spec.qty_step)
    margin_pair = qty * nearest_buy / leverage + qty * nearest_sell / leverage
    if margin_pair > budget + 1e-8:
        return None
    if qty * nearest_buy + 1e-9 < spec.min_notional or qty * nearest_sell + 1e-9 < spec.min_notional:
        return None
    return qty


def build_plan(
    candles: list[Candle],
    spec: ContractSpec,
    equity: float,
    params: GridParams,
    leverage: int,
) -> tuple[Plan | None, str]:
    lookback = params.swing_lookback
    if len(candles) < lookback:
        return None, "zu_wenig_daten"
    window = candles[-lookback:]
    lower = min(item.low for item in window)
    upper = max(item.high for item in window)
    mark = candles[-1].close
    mid = (lower + upper) / 2.0
    if mid <= 0 or upper <= lower:
        return None, "range_ungueltig"
    width_pct = (upper - lower) / mid
    if width_pct < params.min_range_pct:
        return None, "range_zu_eng"
    if width_pct > params.max_range_pct:
        return None, "range_zu_weit"
    position = (mark - lower) / (upper - lower)
    if position < params.edge_inset or position > 1.0 - params.edge_inset:
        return None, "preis_am_rand"
    levels = choose_levels(
        lower, upper, spec.price_tick, params.grid_levels, params.min_grid_levels, params.min_spacing_pct,
    )
    if not levels:
        return None, "abstand_unter_fee"
    qty = select_qty(equity, lower, upper, mark, levels, spec, params, leverage)
    if qty is None:
        return None, "unter_mindestgroesse"
    span = levels[-1] - levels[0]
    spacing_pct = (span / (len(levels) - 1)) / ((levels[0] + levels[-1]) / 2.0)
    hard_stop = equity * params.hard_stop_pct
    return (
        Plan(
            symbol=spec.symbol,
            lower=levels[0],
            upper=levels[-1],
            levels=levels,
            qty=qty,
            leverage=leverage,
            spacing_pct=spacing_pct,
            min_spacing_pct=params.min_spacing_pct,
            hard_stop_usdt=hard_stop,
        ),
        "ok",
    )
