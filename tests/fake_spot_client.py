"""Spot-Client ohne Netz. Liefert feste Kerzen, Specs und Ticker; zeichnet Aufrufe auf."""

from __future__ import annotations

import math
import random

from unified_bot.spot.candles import DailyCandle, closed_only
from unified_bot.spot.client import SpotApiError
from unified_bot.spot.params import DAY_MS
from unified_bot.spot.specs import SpotSpec, load_fallback_specs


def candles_from_closes(first_day: int, closes: list[float], quote_volume: float | list[float] = 5e6) -> list[DailyCandle]:
    out: list[DailyCandle] = []
    for offset, close in enumerate(closes):
        if close is None or (isinstance(close, float) and math.isnan(close)):
            continue
        volume = quote_volume[offset] if isinstance(quote_volume, list) else quote_volume
        ts = (first_day + offset) * DAY_MS
        out.append(DailyCandle(ts, close, close * 1.01, close * 0.99, close, float(volume)))
    return out


def random_walk(n: int, start: float = 100.0, drift: float = 0.0005, vol: float = 0.03, seed: int = 1) -> list[float]:
    rng = random.Random(seed)
    closes = [start]
    for _ in range(n - 1):
        closes.append(closes[-1] * math.exp(drift + vol * rng.gauss(0, 1)))
    return closes


class FakeSpotClient:
    def __init__(self, specs: dict[str, SpotSpec] | None = None, candles: dict[str, list[DailyCandle]] | None = None,
                 tickers: dict[str, dict] | None = None):
        self.specs = specs if specs is not None else load_fallback_specs()
        self.candles = candles or {}
        self.tickers = tickers or {}
        self.calls: list[tuple] = []
        self.symbols_error: SpotApiError | None = None
        self.tickers_error: SpotApiError | None = None
        self.candle_errors: dict[str, SpotApiError] = {}
        self.account_info: dict = {}
        self.assets: list[dict] = []
        self.signed_calls: list[str] = []

    # Marktdaten
    def get_symbols(self) -> dict[str, SpotSpec]:
        self.calls.append(("symbols",))
        if self.symbols_error is not None:
            raise self.symbols_error
        return dict(self.specs)

    def get_tickers(self) -> dict[str, dict]:
        self.calls.append(("tickers",))
        if self.tickers_error is not None:
            raise self.tickers_error
        return {symbol: dict(row) for symbol, row in self.tickers.items()}

    def get_daily_history(self, symbol: str, days: int, now_ms: int) -> list[DailyCandle]:
        self.calls.append(("history", symbol, days, now_ms))
        if symbol in self.candle_errors:
            raise self.candle_errors[symbol]
        if symbol not in self.candles:
            raise SpotApiError("40034", f"Parameter {symbol} does not exist", "/api/v2/spot/market/candles")
        candles = closed_only(list(self.candles[symbol]), now_ms)
        return candles[-days:] if len(candles) > days else candles

    # Signierte Leseabfragen (Konto-Check)
    def get_account_info(self) -> dict:
        self.signed_calls.append("account/info")
        return dict(self.account_info)

    def get_spot_assets(self) -> list[dict]:
        self.signed_calls.append("account/assets")
        return list(self.assets)
