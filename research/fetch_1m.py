#!/usr/bin/env python3
"""Lädt 1-Minuten-Kerzen von Bitget nach data/research/1m/<SYMBOL>.json (gitignored).

    python3 -m research.fetch_1m --days 90
    python3 -m research.fetch_1m --symbols TSLAUSDT,NVDAUSDT --workers 2

Öffentlicher Endpunkt, 200 Kerzen je Aufruf, 0,12 s Pause je Aufruf und Worker.
Der Stand wird alle 25 Aufrufe gespeichert; ein Abbruch kann mit demselben
Aufruf fortgesetzt werden, es werden nur fehlende Ränder und Lücken nachgeladen.
Bitgets endTime ist die Schlusszeit der letzten gelieferten Kerze (inklusiv).
Zeilenformat wie die 1h-Dateien: [ts, open, high, low, close, baseVol, quoteVol].
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bitget_client import BitgetClient
from research.data import DATA_DIR

DIR_1M = DATA_DIR / "1m"
MINUTE = 60_000
DEFAULT_SYMBOLS = "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT,SUIUSDT,TSLAUSDT,NVDAUSDT,MSTRUSDT,INTCUSDT,SNDKUSDT"
SAVE_EVERY = 25


def path_for(symbol: str) -> Path:
    return DIR_1M / f"{symbol}.json"


def load_rows(symbol: str) -> dict[int, list]:
    path = path_for(symbol)
    if not path.exists():
        return {}
    return {int(row[0]): row for row in json.loads(path.read_text(encoding="utf-8"))}


def save_rows(symbol: str, rows: dict[int, list]) -> None:
    DIR_1M.mkdir(parents=True, exist_ok=True)
    path = path_for(symbol)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps([rows[ts] for ts in sorted(rows)]), encoding="utf-8")
    tmp.replace(path)


def _page(client: BitgetClient, symbol: str, end_ms: int) -> list:
    """Eine Seite (bis 200 Kerzen) mit Ende end_ms. Bei Fehlern mit Pause erneut."""
    for attempt in range(6):
        data = client.public_get(
            "/api/v2/mix/market/history-candles",
            {"symbol": symbol, "productType": client.product_type, "granularity": "1m", "limit": "200", "endTime": str(end_ms)},
        )
        code = str(data.get("code", ""))
        if code in ("00000", ""):
            batch = data.get("data") or []
            return batch if isinstance(batch, list) else []
        client._sleep(1.0 + attempt)  # Rate-Limit oder Störung: warten und nochmal
    return []


def _walk_down(client: BitgetClient, symbol: str, rows: dict[int, list], end_ms: int, start_ms: int, log) -> None:
    """Lädt rückwärts von end_ms bis start_ms und sichert alle SAVE_EVERY Aufrufe."""
    end = end_ms
    calls = 0
    total = max(1, (end_ms - start_ms) // MINUTE)
    while end > start_ms:
        batch = _page(client, symbol, end)
        calls += 1
        if not batch:
            break
        oldest = min(int(row[0]) for row in batch)
        for row in batch:
            ts = int(row[0])
            if start_ms <= ts <= end_ms:
                rows[ts] = row
        if oldest >= end:
            break
        end = oldest  # endTime ist die Schlusszeit (inklusiv): die Kerze vor `oldest` schließt genau dort
        if calls % SAVE_EVERY == 0:
            save_rows(symbol, rows)
            done = min(1.0, (end_ms - oldest) / (total * MINUTE))
            log(f"{symbol}: {100 * done:5.1f} % (bis {_fmt(oldest)}), {len(rows)} Kerzen")
        client._sleep(0.12)
    save_rows(symbol, rows)


def _fill_gaps(client: BitgetClient, symbol: str, rows: dict[int, list], log) -> None:
    """Innere Lücken (mehr als eine Minute ohne Kerze) seitenweise nachladen.
    Eine Seite mit endTime = Lückenende liefert die 200 Minuten davor."""
    stamps = sorted(rows)
    gaps = [(stamps[k - 1], stamps[k]) for k in range(1, len(stamps)) if stamps[k] - stamps[k - 1] > MINUTE]
    if not gaps:
        return
    log(f"{symbol}: {len(gaps)} Lücken, lade nach")
    for n, (_, gap_end) in enumerate(gaps, 1):
        for row in _page(client, symbol, gap_end):
            rows[int(row[0])] = row
        if n % SAVE_EVERY == 0:
            save_rows(symbol, rows)
        client._sleep(0.12)
    save_rows(symbol, rows)


def fetch_symbol(symbol: str, start_ms: int, end_ms: int, log=print) -> dict:
    client = BitgetClient(product_type="USDT-FUTURES")
    rows = load_rows(symbol)
    if rows:
        oldest, newest = min(rows), max(rows)
        log(f"{symbol}: {len(rows)} Kerzen vorhanden ({_fmt(oldest)} bis {_fmt(newest)}), lade Ränder nach")
        if newest + MINUTE < end_ms:
            _walk_down(client, symbol, rows, end_ms, newest + 1, log)
        if oldest > start_ms + MINUTE:
            _walk_down(client, symbol, rows, oldest - 1, start_ms, log)
    else:
        _walk_down(client, symbol, rows, end_ms, start_ms, log)
    _fill_gaps(client, symbol, rows, log)
    if not rows:
        log(f"{symbol}: keine Kerzen")
        return {"symbol": symbol, "rows": 0}
    oldest, newest = min(rows), max(rows)
    expected = (newest - oldest) // MINUTE + 1
    log(f"{symbol}: fertig, {len(rows)} Kerzen, {_fmt(oldest)} bis {_fmt(newest)}, Lücken {expected - len(rows)}")
    return {"symbol": symbol, "rows": len(rows), "first": oldest, "last": newest, "missing": expected - len(rows)}


def _fmt(ts_ms: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts_ms / 1000))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument("--workers", type=int, default=3, help="parallele Symbole (Bitget erlaubt 20 Aufrufe/s)")
    args = parser.parse_args()
    end = int(time.time() * 1000)
    end -= end % MINUTE
    end -= MINUTE  # die laufende Minute ist noch offen
    start = end - args.days * 86_400_000
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    print(f"Lade {len(symbols)} Symbole, {_fmt(start)} bis {_fmt(end)}", flush=True)

    def log(msg: str) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        results = list(pool.map(lambda s: fetch_symbol(s, start, end, log), symbols))
    for r in results:
        print(r)
    print("fertig")


if __name__ == "__main__":
    main()
