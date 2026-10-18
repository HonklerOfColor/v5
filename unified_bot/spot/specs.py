"""Spot-Symbolregeln. Live von /api/v2/spot/public/symbols, offline aus docs/spot_modules/code/bitget_spot.json."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

FALLBACK_PATH = Path(__file__).resolve().parents[2] / "docs" / "spot_modules" / "code" / "bitget_spot.json"


@dataclass(frozen=True)
class SpotSpec:
    symbol: str
    base: str
    quote: str
    min_trade_usdt: float
    quantity_precision: int
    price_precision: int
    status: str
    open_time_ms: int = 0
    taker_fee: float = 0.001
    maker_fee: float = 0.001

    @property
    def online(self) -> bool:
        return self.status == "online"

    @classmethod
    def from_bitget(cls, row: dict) -> "SpotSpec":
        return cls(
            symbol=str(row.get("symbol") or ""),
            base=str(row.get("baseCoin") or ""),
            quote=str(row.get("quoteCoin") or ""),
            min_trade_usdt=float(row.get("minTradeUSDT") or 0),
            quantity_precision=int(row.get("quantityPrecision") or 0),
            price_precision=int(row.get("pricePrecision") or 0),
            status=str(row.get("status") or ""),
            open_time_ms=int(float(row.get("openTime") or 0)),
            taker_fee=float(row.get("takerFeeRate") or 0.001),
            maker_fee=float(row.get("makerFeeRate") or 0.001),
        )


def specs_from_rows(rows: list) -> dict[str, SpotSpec]:
    out: dict[str, SpotSpec] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        spec = SpotSpec.from_bitget(row)
        if spec.symbol:
            out[spec.symbol] = spec
    return out


def load_fallback_specs(path: Path | None = None) -> dict[str, SpotSpec]:
    """Offline-Stand vom 18.10.2026. Nur Fallback für Tests und wenn die Börse nicht antwortet."""
    raw = json.loads((path or FALLBACK_PATH).read_text(encoding="utf-8"))
    rows = raw.get("data") if isinstance(raw, dict) else raw
    return specs_from_rows(rows or [])


def floor_quantity(quantity: float, precision: int) -> float:
    """Abrunden auf quantityPrecision Nachkommastellen, nie aufrunden."""
    if quantity <= 0 or math.isnan(quantity):
        return 0.0
    factor = 10 ** max(0, int(precision))
    return math.floor(quantity * factor + 1e-9) / factor


def round_price(price: float, precision: int) -> float:
    return round(price, max(0, int(precision)))
