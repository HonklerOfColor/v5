"""
Bitget USDT-M Client.

Auth wie V2: ACCESS-KEY / ACCESS-SIGN / ACCESS-TIMESTAMP / ACCESS-PASSPHRASE.
Signatur = Base64(HMAC_SHA256(secret, timestamp + METHOD + path + body)).
GET-Query hängt am signierten Pfad. DEMO_MODE setzt den Header paptrading=1.

Market-Data-GETs laufen ohne Signatur, damit Paper und Backtest keine Keys brauchen.
"""

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
            backoff_factor=0.6,
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
        url = BASE_URL + path + query
        try:
            response = self.session.get(url, timeout=15)
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
        headers = self._headers("GET", full, "")
        try:
            response = self.session.get(BASE_URL + full, headers=headers, timeout=15)
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            return {"code": "error", "msg": str(exc), "data": []}
        if not isinstance(data, dict):
            return {"code": "error", "msg": "unexpected response", "data": []}
        return data

    def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload)
        headers = self._headers("POST", path, body)
        try:
            response = self.session.post(BASE_URL + path, headers=headers, data=body, timeout=15)
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

    def get_history_candles(self, symbol: str, granularity: str, start_ms: int, end_ms: int) -> list:
        rows: list = []
        seen: set[int] = set()
        end = end_ms
        while True:
            data = self.public_get(
                "/api/v2/mix/market/history-candles",
                {
                    "symbol": symbol,
                    "productType": self.product_type,
                    "granularity": granularity,
                    "limit": "200",
                    "endTime": str(end),
                },
            )
            if str(data.get("code", "")) not in ("00000", ""):
                break
            batch = data.get("data") or []
            if not isinstance(batch, list) or not batch:
                break
            for row in batch:
                ts = int(row[0])
                if ts in seen or ts < start_ms or ts > end_ms:
                    continue
                seen.add(ts)
                rows.append(row)
            oldest = min(int(row[0]) for row in batch)
            if oldest <= start_ms or oldest >= end:
                break
            end = oldest  # endTime ist die Schlusszeit der letzten Kerze (inklusiv): die Kerze vor `oldest` schließt genau dort
            self._sleep(0.12)
        rows.sort(key=lambda row: int(row[0]))
        return rows

    def get_ticker(self, symbol: str) -> dict:
        data = self.public_get(
            "/api/v2/mix/market/ticker",
            {"symbol": symbol, "productType": self.product_type},
        )
        body = data.get("data") or {}
        if isinstance(body, list):
            return body[0] if body else {}
        return body if isinstance(body, dict) else {}

    def get_contract(self, symbol: str) -> dict:
        data = self.public_get(
            "/api/v2/mix/market/contracts",
            {"symbol": symbol, "productType": self.product_type},
        )
        items = data.get("data") or []
        if isinstance(items, list) and items:
            return items[0]
        return {}

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
                return float(row[key])
        return None

    def get_equity(self) -> float | None:
        return self._amount(self.get_account(), ("usdtEquity", "accountEquity", "equity", "available"))

    def get_available(self) -> float | None:
        return self._amount(self.get_account(), ("available", "crossedMaxAvailable", "isolatedMaxAvailable"))

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

    def set_margin_mode(self, symbol: str, mode: str) -> dict:
        return self._post(
            "/api/v2/mix/account/set-margin-mode",
            {
                "symbol": symbol,
                "productType": self.product_type,
                "marginCoin": self.margin_coin,
                "marginMode": mode,
            },
        )

    def set_position_mode(self, pos_mode: str) -> dict:
        bitget_mode = "hedge_mode" if pos_mode == "hedge" else "one_way_mode"
        return self._post(
            "/api/v2/mix/account/set-position-mode",
            {"productType": self.product_type, "posMode": bitget_mode},
        )

    def get_positions(self, symbol: str | None = None) -> list[dict]:
        params = {"productType": self.product_type, "marginCoin": self.margin_coin}
        data = self._get("/api/v2/mix/position/all-position", params)
        rows = data.get("data") or []
        if not isinstance(rows, list):
            return []
        if symbol:
            rows = [row for row in rows if row.get("symbol") == symbol]
        return [row for row in rows if float(row.get("total") or 0) > 0]

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

    def get_open_orders(self, symbol: str) -> list[dict]:
        data = self._get(
            "/api/v2/mix/order/orders-pending",
            {"symbol": symbol, "productType": self.product_type},
        )
        rows = data.get("data") or []
        if isinstance(rows, dict):
            rows = rows.get("entrustedList") or rows.get("orderList") or []
        return rows if isinstance(rows, list) else []

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
        return body if isinstance(body, dict) else {}

    def place_position_stop(self, symbol: str, hold_side: str, stop_price: str) -> dict:
        return self._post(
            "/api/v2/mix/order/place-pos-tpsl",
            {
                "symbol": symbol,
                "productType": self.product_type,
                "marginCoin": self.margin_coin,
                "holdSide": hold_side,
                "stopLossTriggerPrice": stop_price,
                "stopLossTriggerType": "mark_price",
            },
        )
