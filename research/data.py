"""Eingefrorene 1h-Kerzen aus data/research/, plus Kontraktspezifikationen."""

from __future__ import annotations

import json
from pathlib import Path

from gridbot.candles import Candle, parse_candle, sort_unique
from gridbot.specs import FALLBACK_SPECS, ContractSpec

DATA_DIR = Path("data/research")


def available_symbols() -> list[str]:
    return sorted(path.name[: -len("_1H.json")] for path in DATA_DIR.glob("*_1H.json"))


def load_candles(symbol: str) -> list[Candle]:
    rows = json.loads((DATA_DIR / f"{symbol}_1H.json").read_text(encoding="utf-8"))
    return sort_unique(parse_candle(row) for row in rows)


def load_specs() -> dict[str, ContractSpec]:
    path = DATA_DIR / "specs.json"
    out: dict[str, ContractSpec] = dict(FALLBACK_SPECS)
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        for symbol, row in raw.items():
            out[symbol] = ContractSpec.from_bitget(row)
    return out


def split_index(candles: list[Candle], oos_days: int) -> int:
    """Index der ersten Out-of-Sample-Kerze: die letzten oos_days Tage."""
    if not candles:
        return 0
    cutoff = candles[-1].ts - oos_days * 86_400_000
    for i, candle in enumerate(candles):
        if candle.ts >= cutoff:
            return i
    return len(candles)
