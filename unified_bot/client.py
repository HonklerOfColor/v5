"""Bitget USDT-M REST. Öffentliche Kerzen ohne Key. Signatur wie die alten Bots."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from unified_bot.gridcore.specs import FALLBACK_SPECS, ContractSpec

BASE_URL = "https://api.bitget.com"


class BitgetClient:
    def __init__(
        self,
        api_key: str = "",
        secret_key: str = "",
        passphrase: str = "",
        product_type: str = "USDT-FUTURES",
        margin_coin: str = "USDT",
        margin_mode: str = "isolated",
        demo_mode: bool = False,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.product_type = product_type
        self.margin_coin = margin_coin
        self.margin_mode = margin_mode
        self.demo_mode = demo_mode
        self._sleep = sleep
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.4,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=8, pool_maxsize=8)
        self.session.mount("https://", adapter)
        self.session.trust_env = False

    def _sign(self, timestamp: str, method: str, path: str, body: str) -> str:
        message = f"{timestamp}{method.upper()}{path}{body}"
        mac = hmac.new(self.secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    def _headers(self, method: str, path: str, body: str) -> dict:
        timestamp = str(int(time.time() * 1000))
        headers = {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": self._sign(timestamp, method, path, body),
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "locale": "en-US",
        }
        if self.demo_mode:
            headers["paptrading"] = "1"
        return headers

    def public_get(self, path: str, params: dict | None = None) -> dict:
        query = ""
        if params:
            query = "?" + "&".join(f"{key}={value}" for key, value in params.items())
        try:
            response = self.session.get(BASE_URL + path + query, timeout=15)
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            return {"code": "error", "msg": str(exc), "data": []}
        if not isinstance(data, dict):
            return {"code": "error", "msg": "unexpected response", "data": []}
        return data

    def _get(self, path: str, params: dict | None = None) -> dict:
        full = path
        if params:
            full = path + "?" + "&".join(f"{key}={value}" for key, value in params.items())
        try:
            response = self.session.get(BASE_URL + full, headers=self._headers("GET", full, ""), timeout=15)
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            return {"code": "error", "msg": str(exc), "data": []}
        if not isinstance(data, dict):
            return {"code": "error", "msg": "unexpected response", "data": []}
        return data

    def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload, separators=(",", ":"))
        try:
            response = self.session.post(
                BASE_URL + path, headers=self._headers("POST", path, body), data=body, timeout=15
            )
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            return {"code": "error", "msg": str(exc)}
        if not isinstance(data, dict):
            return {"code": "error", "msg": "unexpected response"}
        return data

    def get_candles(self, symbol: str, granularity: str, limit: int = 200) -> list:
        data = self.public_get(
            "/api/v2/mix/market/candles",
            {
                "symbol": symbol,
                "productType": self.product_type,
                "granularity": granularity,
                "limit": str(limit),
            },
        )
        rows = data.get("data") or []
        return rows if isinstance(rows, list) else []

    def get_ticker(self, symbol: str) -> dict:
        data = self.public_get(
            "/api/v2/mix/market/ticker",
            {"symbol": symbol, "productType": self.product_type},
        )
        body = data.get("data") or {}
        if isinstance(body, list):
            return body[0] if body else {}
        return body if isinstance(body, dict) else {}

    def get_orderbook(self, symbol: str, limit: int = 15) -> dict:
        return self.public_get(
            "/api/v2/mix/market/merge-depth",
            {"symbol": symbol, "productType": self.product_type, "limit": str(limit)},
        )

    def get_contract(self, symbol: str) -> dict:
        data = self.public_get(
            "/api/v2/mix/market/contracts",
            {"symbol": symbol, "productType": self.product_type},
        )
        items = data.get("data") or []
        if isinstance(items, list) and items:
            return items[0]
        return {}

    def get_spec(self, symbol: str) -> ContractSpec:
        row = self.get_contract(symbol)
        if row:
            spec = ContractSpec.from_bitget(row)
            if spec.symbol:
                return spec
        fallback = FALLBACK_SPECS.get(symbol)
        if fallback is None:
            raise RuntimeError(f"kein Kontrakt für {symbol}")
        return fallback

    def get_account(self) -> dict:
        data = self._get("/api/v2/mix/account/accounts", {"productType": self.product_type})
        accounts = data.get("data") or []
        if isinstance(accounts, list) and accounts:
            return accounts[0]
        return {}

    @staticmethod
    def _amount(row: dict, keys: tuple[str, ...]) -> float | None:
        for key in keys:
            if row.get(key) not in (None, ""):
                try:
                    return float(row[key])
                except (TypeError, ValueError):
                    continue
        return None

    def get_equity(self) -> float | None:
        return self._amount(self.get_account(), ("usdtEquity", "accountEquity", "equity", "available"))

    def get_user_id(self) -> str:
        """UID des Keys. Bitget liefert sie unter spot/account/info als userId."""
        data = self._get("/api/v2/spot/account/info", {})
        body = data.get("data") or {}
        if isinstance(body, list):
            body = body[0] if body else {}
        if not isinstance(body, dict):
            return ""
        return str(body.get("userId") or body.get("uid") or "")

    def get_spot_assets(self) -> list:
        data = self._get("/api/v2/spot/account/assets", {})
        rows = data.get("data") or []
        return rows if isinstance(rows, list) else []

    def set_position_mode(self) -> dict:
        return self._post(
            "/api/v2/mix/account/set-position-mode",
            {"productType": self.product_type, "posMode": "hedge_mode"},
        )

    def set_leverage(self, symbol: str, leverage: int, hold_side: str) -> dict:
        return self._post(
            "/api/v2/mix/account/set-leverage",
            {
                "symbol": symbol,
                "productType": self.product_type,
                "marginCoin": self.margin_coin,
                "leverage": str(leverage),
                "holdSide": hold_side,
            },
        )

    def set_margin_mode(self, symbol: str) -> dict:
        return self._post(
            "/api/v2/mix/account/set-margin-mode",
            {
                "symbol": symbol,
                "productType": self.product_type,
                "marginCoin": self.margin_coin,
                "marginMode": self.margin_mode,
            },
        )

    def get_positions(self, symbol: str | None = None) -> list[dict]:
        data = self._get(
            "/api/v2/mix/position/all-position",
            {"productType": self.product_type, "marginCoin": self.margin_coin},
        )
        rows = data.get("data") or []
        if not isinstance(rows, list):
            return []
        out = []
        for row in rows:
            qty = float(row.get("total") or 0)
            if qty <= 0:
                continue
            if symbol and row.get("symbol") != symbol:
                continue
            out.append(
                {
                    "symbol": row.get("symbol"),
                    "side": str(row.get("holdSide") or "").lower(),
                    "qty": qty,
                    "entry": float(row.get("openPriceAvg") or 0),
                    "leverage": int(float(row.get("leverage") or 0)),
                    "raw": row,
                }
            )
        return out

    def place_order(self, payload: dict) -> dict:
        return self._post("/api/v2/mix/order/place-order", payload)

    def cancel_order(self, symbol: str, order_id: str | None = None, client_oid: str | None = None) -> dict:
        payload = {
            "symbol": symbol,
            "productType": self.product_type,
            "marginCoin": self.margin_coin,
        }
        if order_id:
            payload["orderId"] = str(order_id)
        if client_oid:
            payload["clientOid"] = client_oid
        return self._post("/api/v2/mix/order/cancel-order", payload)

    def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        params = {"productType": self.product_type}
        if symbol:
            params["symbol"] = symbol
        data = self._get("/api/v2/mix/order/orders-pending", params)
        rows = data.get("data") or []
        if isinstance(rows, dict):
            rows = rows.get("entrustedList") or rows.get("orderList") or []
        if not isinstance(rows, list):
            return []
        out = []
        for row in rows:
            out.append(
                {
                    "clientOid": str(row.get("clientOid") or ""),
                    "orderId": str(row.get("orderId") or ""),
                    "symbol": row.get("symbol"),
                    "state": str(row.get("status") or row.get("state") or "live").lower(),
                    "price": float(row.get("price") or 0),
                    "size": float(row.get("size") or 0),
                    "filled": float(row.get("baseVolume") or 0),
                    "avg": float(row.get("priceAvg") or 0),
                }
            )
        return out

    def get_order_detail(self, symbol: str, order_id: str | None = None, client_oid: str | None = None) -> dict:
        params = {"symbol": symbol, "productType": self.product_type}
        if order_id:
            params["orderId"] = str(order_id)
        if client_oid:
            params["clientOid"] = client_oid
        data = self._get("/api/v2/mix/order/detail", params)
        body = data.get("data") or {}
        if isinstance(body, list):
            body = body[0] if body else {}
        if not isinstance(body, dict):
            return {}
        return {
            "clientOid": str(body.get("clientOid") or client_oid or ""),
            "orderId": str(body.get("orderId") or ""),
            "symbol": body.get("symbol") or symbol,
            "state": str(body.get("state") or "").lower(),
            "price": float(body.get("price") or 0),
            "size": float(body.get("size") or 0),
            "filled": float(body.get("baseVolume") or 0),
            "avg": float(body.get("priceAvg") or 0),
        }

    def place_position_stop(self, symbol: str, hold_side: str, stop_price: str, tp_price: str | None = None) -> dict:
        payload = {
            "symbol": symbol,
            "productType": self.product_type,
            "marginCoin": self.margin_coin,
            "holdSide": hold_side,
            "stopLossTriggerPrice": stop_price,
            "stopLossTriggerType": "mark_price",
        }
        if tp_price:
            payload["stopSurplusTriggerPrice"] = tp_price
            payload["stopSurplusTriggerType"] = "mark_price"
        return self._post("/api/v2/mix/order/place-pos-tpsl", payload)
