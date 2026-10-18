"""Kontraktregeln, Rundung und Zahlenformat für Bitget-Orders."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    min_qty: float
    min_notional: float
    qty_step: float
    price_tick: float
    price_place: int
    qty_place: int
    maker_fee: float = 0.0002
    taker_fee: float = 0.0006

    @classmethod
    def from_bitget(cls, row: dict) -> "ContractSpec":
        price_place = int(row.get("pricePlace", 2))
        end_step = float(row.get("priceEndStep") or 1)
        tick = end_step * (10 ** (-price_place))
        vol_place = int(row.get("volumePlace", 4))
        step = float(row.get("sizeMultiplier") or (10 ** (-vol_place)))
        return cls(
            symbol=str(row.get("symbol", "")),
            min_qty=float(row.get("minTradeNum") or step),
            min_notional=float(row.get("minTradeUSDT") or 5),
            qty_step=step,
            price_tick=tick,
            price_place=price_place,
            qty_place=vol_place,
            maker_fee=float(row.get("makerFeeRate") or 0.0002),
            taker_fee=float(row.get("takerFeeRate") or 0.0006),
        )


# Öffentliche Kontraktwerte, Stand Abfrage 2026-10. Live überschreibt sie.
FALLBACK_SPECS: dict[str, ContractSpec] = {
    "BTCUSDT": ContractSpec("BTCUSDT", 0.0001, 5.0, 0.0001, 0.1, 1, 4),
    "ETHUSDT": ContractSpec("ETHUSDT", 0.01, 5.0, 0.01, 0.01, 2, 2),
    "BNBUSDT": ContractSpec("BNBUSDT", 0.01, 5.0, 0.01, 0.01, 2, 2),
    "SOLUSDT": ContractSpec("SOLUSDT", 0.1, 5.0, 0.1, 0.001, 3, 1),
    "DOGEUSDT": ContractSpec("DOGEUSDT", 1.0, 5.0, 1.0, 0.00001, 5, 0),
    "SUIUSDT": ContractSpec("SUIUSDT", 0.1, 5.0, 0.1, 0.0001, 4, 1),
    "HYPEUSDT": ContractSpec("HYPEUSDT", 0.01, 5.0, 0.01, 0.001, 3, 2),
    # Aktien-Perps. Live überschreibt mit /mix/market/contracts.
    "SNDKUSDT": ContractSpec("SNDKUSDT", 0.01, 5.0, 0.01, 0.01, 2, 2),
    "INTCUSDT": ContractSpec("INTCUSDT", 0.01, 5.0, 0.01, 0.01, 2, 2),
    "ANTHROPICUSDT": ContractSpec("ANTHROPICUSDT", 0.01, 5.0, 0.01, 0.01, 2, 2),
}


def _decimals(step: float) -> int:
    if step <= 0:
        return 8
    return max(0, -int(math.floor(math.log10(step) + 1e-12)))


def floor_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    n = math.floor((value / step) + 1e-9)
    return round(n * step, _decimals(step) + 2)


def ceil_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    n = math.ceil((value / step) - 1e-9)
    return round(n * step, _decimals(step) + 2)


def snap_price(price: float, tick: float) -> float:
    if tick <= 0:
        return price
    n = round(price / tick)
    return round(n * tick, _decimals(tick) + 2)


def format_number(value: float, places: int) -> str:
    text = f"{value:.{places}f}"
    if "e" in text.lower():
        raise ValueError(f"scientific notation in order number: {value}")
    return text
