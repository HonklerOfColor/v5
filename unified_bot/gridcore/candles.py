"""Kerzen-Hilfen. Bitget liefert [ts, open, high, low, close, baseVol, quoteVol]."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candle:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


def parse_candle(row: list) -> Candle:
    vol = float(row[5]) if len(row) > 5 and row[5] not in (None, "") else 0.0
    return Candle(
        ts=int(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=vol,
    )


def sort_unique(candles: list[Candle]) -> list[Candle]:
    by_ts: dict[int, Candle] = {}
    for candle in candles:
        by_ts[candle.ts] = candle
    return [by_ts[ts] for ts in sorted(by_ts)]


def aggregate(candles: list[Candle], hours: int = 4) -> list[Candle]:
    """Fasst 1h-Kerzen zu abgeschlossenen N-Stunden-Kerzen zusammen."""
    ms = hours * 3_600_000
    buckets: dict[int, list[Candle]] = {}
    order: list[int] = []
    for candle in candles:
        bucket = candle.ts - (candle.ts % ms)
        if bucket not in buckets:
            buckets[bucket] = []
            order.append(bucket)
        buckets[bucket].append(candle)
    out: list[Candle] = []
    for bucket in order:
        group = buckets[bucket]
        if len(group) < hours:
            continue
        out.append(
            Candle(
                ts=bucket,
                open=group[0].open,
                high=max(item.high for item in group),
                low=min(item.low for item in group),
                close=group[-1].close,
                volume=sum(item.volume for item in group),
            )
        )
    return out
