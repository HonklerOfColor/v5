"""Gemeinsames für die Mikrostruktur-Messungen auf 1-Minuten-Kerzen (research.fetch_1m).

Zeit ist überall UTC in Millisekunden. Eine Kerze mit ts=t deckt [t, t+1min) ab.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from gridbot.candles import Candle, parse_candle, sort_unique
from research.data import DATA_DIR
from research.trend import atr_series

DIR_1M = DATA_DIR / "1m"
MINUTE = 60_000
HOUR = 3_600_000
DAY = 86_400_000


def available_minute_symbols() -> list[str]:
    return sorted(path.stem for path in DIR_1M.glob("*.json"))


def load_minute_candles(symbol: str) -> list[Candle]:
    path = DIR_1M / f"{symbol}.json"
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    return sort_unique(parse_candle(row) for row in rows)


def coverage(candles: list[Candle]) -> dict:
    """Erste/letzte Kerze, Anzahl, fehlende Minuten."""
    if not candles:
        return {"rows": 0, "first": None, "last": None, "missing": 0, "days": 0.0}
    expected = (candles[-1].ts - candles[0].ts) // MINUTE + 1
    return {
        "rows": len(candles),
        "first": candles[0].ts,
        "last": candles[-1].ts,
        "missing": int(expected - len(candles)),
        "days": round((candles[-1].ts - candles[0].ts) / DAY, 1),
    }


def resample_hourly(candles: list[Candle]) -> list[Candle]:
    """1m → 1h, nach Stundenanfang gruppiert. Stunden ohne Kerzen fehlen."""
    out: list[Candle] = []
    for candle in candles:
        hour = candle.ts - candle.ts % HOUR
        if out and out[-1].ts == hour:
            last = out[-1]
            out[-1] = Candle(hour, last.open, max(last.high, candle.high), min(last.low, candle.low), candle.close, last.volume + candle.volume)
        else:
            out.append(Candle(hour, candle.open, candle.high, candle.low, candle.close, candle.volume))
    return out


def hourly_atr_per_minute(candles: list[Candle], period: int = 14) -> list[float | None]:
    """ATR(period) auf 1h-Basis, je Minutenkerze der Wert der letzten abgeschlossenen Stunde.

    Kein Blick nach vorn: Für eine Minute in Stunde H zählt die ATR bis einschließlich Stunde H-1.
    """
    hourly = resample_hourly(candles)
    atrs = atr_series(hourly, period)
    atr_by_hour_end: dict[int, float | None] = {h.ts: atrs[i] for i, h in enumerate(hourly)}
    out: list[float | None] = []
    hours = [h.ts for h in hourly]
    j = 0
    current: float | None = None
    for candle in candles:
        hour = candle.ts - candle.ts % HOUR
        # alle Stunden, die vor dieser Minute abgeschlossen sind, einlesen
        while j < len(hours) and hours[j] < hour:
            current = atr_by_hour_end[hours[j]]
            j += 1
        out.append(current)
    return out


def index_by_ts(candles: list[Candle]) -> dict[int, int]:
    return {c.ts: i for i, c in enumerate(candles)}


def price_at(candles: list[Candle], ts_ms: int, index: dict[int, int] | None = None, max_gap_min: int = 30) -> float | None:
    """Letzter Schluss zum Zeitpunkt ts_ms: Schluss der Kerze, die bei ts_ms endet,
    sonst der jüngste frühere Schluss, höchstens max_gap_min Minuten alt."""
    if not candles:
        return None
    index = index if index is not None else index_by_ts(candles)
    for back in range(1, max_gap_min + 1):
        i = index.get(ts_ms - back * MINUTE)
        if i is not None:
            return candles[i].close
    return None


def mean_se(values: list[float]) -> tuple[float | None, float | None]:
    """Mittel und Standardfehler (None bei n < 2)."""
    n = len(values)
    if n == 0:
        return None, None
    mean = sum(values) / n
    if n < 2:
        return mean, None
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(var / n)


def t_stat(values: list[float]) -> float | None:
    mean, se = mean_se(values)
    if mean is None or not se:
        return None
    return mean / se


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


def bp(x: float | None) -> float | None:
    return None if x is None else x * 10_000.0


def stamp(ts_ms: int | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    if ts_ms is None:
        return "-"
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime(fmt)
