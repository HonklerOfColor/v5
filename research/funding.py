"""Historische Funding-Raten von Bitget, je Symbol als Liste (fundingTime, rate), ältestes zuerst.

    python3 -m research.funding            # lädt für alle Symbole in data/research/

Ablage: data/research/funding/<SYMBOL>.json. Funding fällt alle 8 Stunden an
(00:00, 08:00, 16:00 UTC). Long zahlt bei positiver Rate, Short bekommt sie.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from research.data import DATA_DIR, available_symbols

FUNDING_DIR = DATA_DIR / "funding"
URL = "https://api.bitget.com/api/v2/mix/market/history-fund-rate"


def fetch_funding(symbol: str, max_pages: int = 40) -> list[tuple[int, float]]:
    rows: dict[int, float] = {}
    for page in range(1, max_pages + 1):
        resp = requests.get(
            URL,
            params={"symbol": symbol, "productType": "USDT-FUTURES", "pageSize": "100", "pageNo": str(page)},
            timeout=20,
        ).json()
        data = resp.get("data") or []
        if not data:
            break
        for item in data:
            rows[int(item["fundingTime"])] = float(item["fundingRate"])
        time.sleep(0.1)
    return sorted(rows.items())


def load_funding(symbol: str) -> dict[int, float]:
    path = FUNDING_DIR / f"{symbol}.json"
    if not path.exists():
        return {}
    return {int(ts): float(rate) for ts, rate in json.loads(path.read_text(encoding="utf-8"))}


class FundingBook:
    """Nachschlagen der Rate zu einem Funding-Zeitpunkt. Fehlt die Rate, gilt der Fallback."""

    def __init__(self, rates: dict[int, float], fallback: float = 0.0001):
        self.rates = rates
        self.fallback = fallback

    def rate_at(self, ts_ms: int) -> float:
        return self.rates.get(ts_ms, self.fallback)

    def has(self, ts_ms: int) -> bool:
        return ts_ms in self.rates


def main() -> None:
    FUNDING_DIR.mkdir(parents=True, exist_ok=True)
    for symbol in available_symbols():
        path = FUNDING_DIR / f"{symbol}.json"
        if path.exists():
            print(f"{symbol}: vorhanden", flush=True)
            continue
        rows = fetch_funding(symbol)
        path.write_text(json.dumps(rows), encoding="utf-8")
        first = time.strftime("%Y-%m-%d", time.gmtime(rows[0][0] / 1000)) if rows else "-"
        print(f"{symbol}: {len(rows)} Raten ab {first}", flush=True)
    print("fertig")


if __name__ == "__main__":
    main()


# ── Binance als Jahres-Proxy ─────────────────────────────────────────────────
# Bitget liefert nur 90 Tage Funding-Historie. Binance liefert ein Jahr, die Raten
# der großen Perps laufen zwischen den Börsen eng zusammen. Für den Backtest
# wird Binance als Näherung benutzt; Abweichungen sind Teil der Unschärfe.
BINANCE_DIR = DATA_DIR / "funding_binance"
BINANCE_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
BINANCE_ALIAS = {"PEPEUSDT": "1000PEPEUSDT"}


def fetch_binance_funding(symbol: str, days: int = 365) -> list[tuple[int, float]]:
    end = int(time.time() * 1000)
    start = end - days * 86_400_000
    rows: dict[int, float] = {}
    cursor = start
    for _ in range(20):
        resp = requests.get(
            BINANCE_URL,
            params={"symbol": BINANCE_ALIAS.get(symbol, symbol), "startTime": str(cursor), "endTime": str(end), "limit": "1000"},
            timeout=20,
        )
        data = resp.json()
        if not isinstance(data, list) or not data:
            break
        for item in data:
            ts = int(item["fundingTime"])
            ts -= ts % 60_000  # Binance stempelt gelegentlich +1 ms
            rows[ts] = float(item["fundingRate"])
        last = int(data[-1]["fundingTime"])
        if len(data) < 1000 or last >= end:
            break
        cursor = last + 1
        time.sleep(0.2)
    return sorted(rows.items())


def load_binance_funding(symbol: str) -> dict[int, float]:
    path = BINANCE_DIR / f"{symbol}.json"
    if not path.exists():
        return {}
    return {int(ts): float(rate) for ts, rate in json.loads(path.read_text(encoding="utf-8"))}


def fetch_all_binance() -> None:
    BINANCE_DIR.mkdir(parents=True, exist_ok=True)
    for symbol in available_symbols():
        path = BINANCE_DIR / f"{symbol}.json"
        if path.exists():
            continue
        rows = fetch_binance_funding(symbol)
        path.write_text(json.dumps(rows), encoding="utf-8")
        first = time.strftime("%Y-%m-%d", time.gmtime(rows[0][0] / 1000)) if rows else "-"
        print(f"binance {symbol}: {len(rows)} Raten ab {first}", flush=True)
