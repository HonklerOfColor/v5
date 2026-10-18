"""Broker ohne Netz. Zeichnet Payloads auf und kann Börsenstände vortäuschen."""

from __future__ import annotations


class FakeBroker:
    def __init__(self):
        self.placed: list[dict] = []
        self.cancelled: list[dict] = []
        self.remote_orders: list[dict] = []
        self.remote_positions: list[dict] = []
        self.details: dict[str, dict] = {}
        self._seq = 0

    def place(self, intent, payload, mark: float = 0.0) -> dict:
        self._seq += 1
        self.placed.append({"intent": intent, "payload": payload, "mark": mark})
        if intent.order_type == "market":
            return {
                "code": "00000",
                "data": {
                    "orderId": f"fake{self._seq}",
                    "clientOid": intent.client_oid,
                    "state": "filled",
                    "fillPrice": mark,
                    "fillQty": intent.size,
                },
            }
        return {
            "code": "00000",
            "data": {"orderId": f"fake{self._seq}", "clientOid": intent.client_oid, "state": "live"},
        }

    def cancel(self, symbol, client_oid, order_id=None) -> dict:
        self.cancelled.append({"symbol": symbol, "clientOid": client_oid, "orderId": order_id})
        self.remote_orders = [row for row in self.remote_orders if row.get("clientOid") != client_oid]
        return {"code": "00000"}

    def list_open_orders(self) -> list[dict]:
        return list(self.remote_orders)

    def list_positions(self) -> list[dict]:
        return list(self.remote_positions)

    def get_order(self, symbol, client_oid) -> dict:
        return dict(self.details.get(client_oid) or {})
