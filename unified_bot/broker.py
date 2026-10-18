"""Paper-Broker und Live-Adapter. Paper füllt Market sofort, Limits bleiben liegen."""

from __future__ import annotations

from unified_bot.models import OrderIntent
from unified_bot.settings import Settings


class PaperBroker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.orders: dict[str, dict] = {}
        self.positions: list[dict] = []
        self.placed: list[dict] = []
        self.cancelled: list[dict] = []
        self._seq = 0

    def place(self, intent: OrderIntent, payload: dict, mark: float = 0.0) -> dict:
        self._seq += 1
        order_id = f"paper{self._seq}"
        self.placed.append({"intent": intent, "payload": payload})
        if intent.order_type == "market":
            slip = self.settings.taker_slippage_pct
            if intent.book_side == "sell":
                price = mark * (1.0 - slip) if mark else 0.0
            else:
                price = mark * (1.0 + slip) if mark else 0.0
            return {
                "code": "00000",
                "data": {
                    "orderId": order_id,
                    "clientOid": intent.client_oid,
                    "state": "filled",
                    "fillPrice": price,
                    "fillQty": intent.size,
                },
            }
        self.orders[intent.client_oid] = {
            "clientOid": intent.client_oid,
            "orderId": order_id,
            "symbol": intent.symbol,
            "state": "live",
            "price": intent.price,
            "size": intent.size,
            "filled": 0.0,
            "avg": 0.0,
            "book_side": intent.book_side,
            "strategy_id": intent.strategy_id,
            "purpose": intent.purpose,
            "position_side": intent.position_side,
        }
        return {"code": "00000", "data": {"orderId": order_id, "clientOid": intent.client_oid, "state": "live"}}

    def cancel(self, symbol: str, client_oid: str, order_id: str | None = None) -> dict:
        self.cancelled.append({"symbol": symbol, "clientOid": client_oid, "orderId": order_id})
        self.orders.pop(client_oid, None)
        return {"code": "00000"}

    def list_open_orders(self) -> list[dict]:
        return list(self.orders.values())

    def list_positions(self) -> list[dict]:
        return list(self.positions)

    def get_order(self, symbol: str, client_oid: str) -> dict:
        return self.orders.get(client_oid, {})

    def match(self, symbol: str, last: float) -> list[dict]:
        """Limit füllt, wenn der letzte Preis die Order erreicht."""
        fills = []
        for oid, order in list(self.orders.items()):
            if order["symbol"] != symbol or order.get("state") != "live":
                continue
            price = float(order.get("price") or 0)
            if price <= 0 or last <= 0:
                continue
            hit = (order["book_side"] == "buy" and last <= price) or (
                order["book_side"] == "sell" and last >= price
            )
            if not hit:
                continue
            order["state"] = "filled"
            order["filled"] = order["size"]
            order["avg"] = price
            fills.append(order)
            self.orders.pop(oid, None)
        return fills

    def mirror_positions(self, rows: list[dict]) -> None:
        self.positions = rows

    def adopt(self, book) -> None:
        """Lokale Paper-Orders in den Broker spiegeln, damit der Abgleich nicht ins Leere läuft."""
        for order in book.orders.values():
            if order.client_oid in self.orders:
                continue
            self.orders[order.client_oid] = {
                "clientOid": order.client_oid,
                "orderId": order.order_id or "",
                "symbol": order.symbol,
                "state": "live",
                "price": order.price,
                "size": order.size,
                "filled": order.filled,
                "avg": 0.0,
                "book_side": order.book_side,
                "strategy_id": order.strategy_id,
                "purpose": order.purpose,
                "position_side": order.position_side,
            }


class LiveBroker:
    def __init__(self, client, settings: Settings):
        self.client = client
        self.settings = settings

    def place(self, intent: OrderIntent, payload: dict, mark: float = 0.0) -> dict:
        return self.client.place_order(payload)

    def cancel(self, symbol: str, client_oid: str, order_id: str | None = None) -> dict:
        return self.client.cancel_order(symbol, order_id=order_id, client_oid=client_oid)

    def list_open_orders(self) -> list[dict]:
        return self.client.get_open_orders()

    def list_positions(self) -> list[dict]:
        return self.client.get_positions()

    def get_order(self, symbol: str, client_oid: str) -> dict:
        return self.client.get_order_detail(symbol, client_oid=client_oid)
