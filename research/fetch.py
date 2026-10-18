#!/usr/bin/env python3
"""Lädt 1h-Kerzen und Kontraktdaten für den Strategie-Vergleich nach data/research/ (gitignored).

    python3 -m research.fetch --days 365 --symbols BTCUSDT,ETHUSDT,...

Vorhandene Dateien werden nicht neu geladen. Öffentliche Endpunkte, kein Key nötig.
"""

from __future__ import annotations

import argparse
import json
import time

from bitget_client import BitgetClient
from research.data import DATA_DIR

DEFAULT_SYMBOLS = (
    "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,SUIUSDT,LINKUSDT,DOTUSDT,AVAXUSDT,NEARUSDT,"
    "PEPEUSDT,UNIUSDT,INJUSDT,TIAUSDT,ENAUSDT,ARBUSDT,HYPEUSDT,ZECUSDT,FILUSDT,WLDUSDT,ONDOUSDT,LTCUSDT,"
    "TRXUSDT,AAVEUSDT,OPUSDT,APTUSDT"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    args = parser.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    client = BitgetClient(product_type="USDT-FUTURES")
    end = int(time.time() * 1000)
    end -= end % 3_600_000
    start = end - args.days * 86_400_000
    spec_path = DATA_DIR / "specs.json"
    specs = json.loads(spec_path.read_text(encoding="utf-8")) if spec_path.exists() else {}
    for symbol in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
        path = DATA_DIR / f"{symbol}_1H.json"
        if path.exists():
            print(f"{symbol}: vorhanden", flush=True)
        else:
            rows = client.get_history_candles(symbol, "1H", start, end)
            path.write_text(json.dumps(rows), encoding="utf-8")
            print(f"{symbol}: {len(rows)} Kerzen", flush=True)
        row = client.get_contract(symbol)
        if row:
            specs[symbol] = row
            spec_path.write_text(json.dumps(specs), encoding="utf-8")
    print("fertig")


if __name__ == "__main__":
    main()
