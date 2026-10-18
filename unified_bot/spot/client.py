"""Bitget Spot REST v2, nur lesend. Es gibt hier absichtlich keine Order-Methode.

Fehler sind Fehler: Eine API-Antwort mit Fehlercode oder ein Netzfehler wirft SpotApiError.
Eine leere Liste bedeutet "Bitget hat nichts", nicht "Bitget war nicht erreichbar".
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from unified_bot.spot.candles import DailyCandle, closed_only, parse_spot_candle
from unified_bot.spot.params import DAY_MS, GRANULARITY
from unified_bot.spot.specs import SpotSpec, specs_from_rows

BASE_URL = "https://api.bitget.com"
PAGE_LIMIT = 200          # history-candles erlaubt höchstens 200
REQUEST_PAUSE = 0.06      # Sekunden zwischen Kerzenabfragen (öffentliches Limit 20/s)
UNKNOWN_SYMBOL_CODE = "40034"
NO_CANDLES_CODES = {"40034", "48001"}   # 48001: Bitget liefert für dieses Symbol keine Kerzen (z. B. Tokenized Stocks)


class SpotApiError(RuntimeError):
    def __init__(self, code: str, msg: str, path: str = ""):
        super().__init__(f"{path} -> {code}: {msg}")
        self.code = str(code)
        self.msg = str(msg)
        self.path = path

    @property
    def unknown_symbol(self) -> bool:
        """Symbol unbekannt oder ohne Kerzendaten. Kein Transportfehler."""
        return self.code in NO_CANDLES_CODES


class BitgetSpotClient:
    def __init__(
        self,
        api_key: str = "",
        secret_key: str = "",
        passphrase: str = "",
        sleep: Callable[[float], None] = time.sleep,
        session: requests.Session | None = None,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self._sleep = sleep
        self.session = session or requests.Session()
        if session is None:
            retries = Retry(
                total=3,
                backoff_factor=0.4,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"],
            )
            adapter = HTTPAdapter(max_retries=retries, pool_connections=4, pool_maxsize=4)
            self.session.mount("https://", adapter)
            self.session.trust_env = False

    # ── Transport ────────────────────────────────────────────────────────────
    @staticmethod
    def _query(params: dict | None) -> str:
        if not params:
            return ""
        return "?" + "&".join(f"{key}={value}" for key, value in params.items())

    def _request(self, path: str, params: dict | None, headers: dict | None) -> dict:
        full = path + self._query(params)
        try:
            response = self.session.get(BASE_URL + full, headers=headers, timeout=20)
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise SpotApiError("transport", str(exc), path) from exc
        if not isinstance(data, dict):
            raise SpotApiError("unexpected", "Antwort ist kein Objekt", path)
        code = str(data.get("code", ""))
        if code != "00000":
            raise SpotApiError(code or "unknown", str(data.get("msg") or "Fehler ohne Text"), path)
        return data

    def public_get(self, path: str, params: dict | None = None) -> dict:
        return self._request(path, params, None)

    def _sign(self, timestamp: str, method: str, path: str, body: str) -> str:
        message = f"{timestamp}{method.upper()}{path}{body}"
        mac = hmac.new(self.secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    def signed_get(self, path: str, params: dict | None = None) -> dict:
        """Signiertes GET. Nur für Kontoabfragen (Spot-Fähigkeit prüfen). Keine Orders."""
        full = path + self._query(params)
        timestamp = str(int(time.time() * 1000))
        headers = {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": self._sign(timestamp, "GET", full, ""),
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "locale": "en-US",
        }
        return self._request(path, params, headers)

    # ── Öffentliche Marktdaten ───────────────────────────────────────────────
    def get_symbols(self) -> dict[str, SpotSpec]:
        data = self.public_get("/api/v2/spot/public/symbols")
        rows = data.get("data") or []
        if not isinstance(rows, list) or not rows:
            raise SpotApiError("empty", "Symbolliste leer", "/api/v2/spot/public/symbols")
        return specs_from_rows(rows)

    def get_tickers(self) -> dict[str, dict]:
        data = self.public_get("/api/v2/spot/market/tickers")
        rows = data.get("data") or []
        out: dict[str, dict] = {}
        for row in rows if isinstance(rows, list) else []:
            symbol = str(row.get("symbol") or "")
            if not symbol:
                continue
            out[symbol] = {
                "last": _f(row.get("lastPr")),
                "bid": _f(row.get("bidPr")),
                "ask": _f(row.get("askPr")),
                "usdt_volume": _f(row.get("usdtVolume") or row.get("quoteVolume")),
                "ts": int(_f(row.get("ts"))),
            }
        return out

    def get_ticker(self, symbol: str) -> dict:
        data = self.public_get("/api/v2/spot/market/tickers", {"symbol": symbol})
        rows = data.get("data") or []
        row = rows[0] if isinstance(rows, list) and rows else {}
        return {
            "last": _f(row.get("lastPr")),
            "bid": _f(row.get("bidPr")),
            "ask": _f(row.get("askPr")),
            "usdt_volume": _f(row.get("usdtVolume") or row.get("quoteVolume")),
        }

    def get_candles_raw(self, symbol: str, limit: int = PAGE_LIMIT, end_time_ms: int | None = None) -> list[DailyCandle]:
        """Eine Seite Tageskerzen (UTC-Tag). Mit endTime die Historie davor."""
        params = {"symbol": symbol, "granularity": GRANULARITY, "limit": str(min(limit, PAGE_LIMIT))}
        path = "/api/v2/spot/market/candles"
        if end_time_ms is not None:
            path = "/api/v2/spot/market/history-candles"
            params["endTime"] = str(int(end_time_ms))
        data = self.public_get(path, params)
        rows = data.get("data") or []
        return [parse_spot_candle(row) for row in rows if isinstance(row, list) and len(row) >= 5]

    def get_daily_history(self, symbol: str, days: int, now_ms: int) -> list[DailyCandle]:
        """Bis zu `days` ABGESCHLOSSENE Tageskerzen, älteste zuerst. Die laufende Kerze ist nicht dabei."""
        collected: dict[int, DailyCandle] = {}
        page = self.get_candles_raw(symbol, PAGE_LIMIT)
        for candle in page:
            collected[candle.ts] = candle
        while page and len(collected) < days + 1:
            oldest = min(collected)
            self._sleep(REQUEST_PAUSE)
            page = self.get_candles_raw(symbol, PAGE_LIMIT, end_time_ms=oldest)
            new = [candle for candle in page if candle.ts not in collected]
            if not new:
                break
            for candle in new:
                collected[candle.ts] = candle
        candles = closed_only(list(collected.values()), now_ms)
        if len(candles) > days:
            candles = candles[-days:]
        return candles

    # ── Signierte Leseabfragen (nur für den Konto-Check) ─────────────────────
    def get_account_info(self) -> dict:
        data = self.signed_get("/api/v2/spot/account/info", {})
        body = data.get("data") or {}
        if isinstance(body, list):
            body = body[0] if body else {}
        return body if isinstance(body, dict) else {}

    def get_spot_assets(self) -> list[dict]:
        data = self.signed_get("/api/v2/spot/account/assets", {})
        rows = data.get("data") or []
        return rows if isinstance(rows, list) else []


def _f(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def day_start_ms(day: int) -> int:
    return day * DAY_MS
