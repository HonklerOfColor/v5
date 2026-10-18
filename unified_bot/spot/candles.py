"""Tageskerzen und Tagesnummern. Die laufende Kerze wird hier verworfen, nirgends sonst."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone

from unified_bot.spot.params import DAY_MS

NAN = float("nan")


@dataclass(frozen=True)
class DailyCandle:
    ts: int          # Startzeit der Kerze, 00:00 UTC, ms
    open: float
    high: float
    low: float
    close: float
    quote_volume: float   # USDT-Umsatz des Tages

    @property
    def day(self) -> int:
        return self.ts // DAY_MS


def parse_spot_candle(row: list) -> DailyCandle:
    """Bitget Spot: [ts, open, high, low, close, baseVol, usdtVol, quoteVol]."""
    quote = 0.0
    for index in (6, 7):
        if len(row) > index and row[index] not in (None, ""):
            try:
                quote = float(row[index])
                break
            except (TypeError, ValueError):
                continue
    return DailyCandle(
        ts=int(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        quote_volume=quote,
    )


def closed_only(candles: list[DailyCandle], now_ms: int) -> list[DailyCandle]:
    """Nur Kerzen, deren Tag vollständig vorbei ist: Start + 1 Tag <= jetzt.

    Eine Kerze mit Startzeit heute 00:00 UTC ist die laufende Kerze und fliegt raus,
    auch wenn Bitget sie schon mit Schlusskurs liefert.
    """
    by_day: dict[int, DailyCandle] = {}
    for candle in candles:
        if candle.ts % DAY_MS != 0:
            continue  # keine Tageskerze mit 00:00-UTC-Start, nicht verwenden
        if candle.ts + DAY_MS > now_ms:
            continue
        by_day[candle.day] = candle
    return [by_day[day] for day in sorted(by_day)]


def day_of_ms(ts_ms: int) -> int:
    return int(ts_ms) // DAY_MS


def day_to_date(day: int) -> date:
    return datetime.fromtimestamp(day * DAY_MS / 1000, tz=timezone.utc).date()


def day_iso(day: int) -> str:
    return day_to_date(day).isoformat()


def day_from_iso(text: str) -> int:
    year, month, day = (int(part) for part in text.split("-"))
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp() * 1000) // DAY_MS


def is_month_end(day: int) -> bool:
    return day_to_date(day + 1).day == 1


def previous_month_end(day: int) -> int:
    """Letzter Tag des Monats vor dem Monat, in dem `day` liegt."""
    current = day_to_date(day)
    first = datetime(current.year, current.month, 1, tzinfo=timezone.utc)
    return int(first.timestamp() * 1000) // DAY_MS - 1


def weekday(day: int) -> int:
    """0 = Montag … 6 = Sonntag, wie pandas dayofweek."""
    return day_to_date(day).weekday()


@dataclass
class DailySeries:
    """Lückenlose Tagesreihe ab `first_day`. Fehlende Tage sind NaN, wie im Pandas-Panel."""

    symbol: str
    first_day: int
    closes: list[float]
    quote_volumes: list[float]

    @property
    def last_day(self) -> int:
        return self.first_day + len(self.closes) - 1

    def index_of(self, day: int) -> int | None:
        offset = day - self.first_day
        if offset < 0 or offset >= len(self.closes):
            return None
        return offset

    def close_at(self, day: int) -> float:
        index = self.index_of(day)
        if index is None:
            return NAN
        return self.closes[index]

    def last_close_before(self, day: int) -> float | None:
        """Letzter bekannter Schlusskurs bis einschließlich `day` (für Delisting)."""
        index = self.index_of(min(day, self.last_day))
        if index is None:
            if day < self.first_day:
                return None
            index = len(self.closes) - 1
        for position in range(index, -1, -1):
            value = self.closes[position]
            if not math.isnan(value):
                return value
        return None

    def count_closes_until(self, day: int) -> int:
        index = self.index_of(min(day, self.last_day))
        if index is None:
            return 0
        return sum(1 for value in self.closes[: index + 1] if not math.isnan(value))


def series_from_candles(symbol: str, candles: list[DailyCandle], until_day: int) -> DailySeries | None:
    """Ordnet geschlossene Kerzen in eine lückenlose Tagesreihe bis `until_day`."""
    usable = [candle for candle in candles if candle.day <= until_day]
    if not usable:
        return None
    first = usable[0].day
    length = until_day - first + 1
    closes = [NAN] * length
    volumes = [NAN] * length
    for candle in usable:
        closes[candle.day - first] = candle.close
        volumes[candle.day - first] = candle.quote_volume
    return DailySeries(symbol, first, closes, volumes)
