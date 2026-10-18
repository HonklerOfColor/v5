#!/usr/bin/env python3
"""Funding-Fenster: Kursbewegung in den 30 Minuten vor und nach jedem Funding-Zeitpunkt.

    python3 -m research.funding_window

Bitget-Funding (data/research/funding/, 00:00, 08:00, 16:00 UTC) wird nach
Vorzeichen und Größe des Satzes gruppiert; die Größenklassen standen vorab fest:
|Satz| < 1 bp, genau 1 bp (Bitget-Standardsatz 0,01 %), 1 bis 3 bp, über 3 bp.
Kurs zu einem Zeitpunkt ist der Schluss der Minutenkerze, die dort endet.
Rendite vorher = P(t) / P(t − 30 min) − 1, nachher = P(t + 30 min) / P(t) − 1,
in Basispunkten. Dagegen stehen 16 bp Taker-Round-Trip (2 × 0,06 % + 2 × 2 bp
Slippage). Zwei Handelsideen ergeben sich direkt aus den Mitteln:
Fade: 30 Minuten vor dem Funding gegen das Vorzeichen des Satzes positionieren
(Short bei positivem Satz), Funding kassieren, 30 Minuten danach schließen.
Bounce: zum Funding mit dem Vorzeichen des Satzes (Long bei positivem Satz),
nach 30 Minuten schließen.
Kontrolle: dieselben Fenster um 4 Stunden versetzt (04:00, 12:00, 20:00 UTC), wo
kein Funding anfällt. Liegt die Bewegung dort genauso, ist es Tageszeit, nicht Funding.
"""

from __future__ import annotations

import argparse

from gridbot.candles import Candle
from research.funding import load_funding
from research.micro import MINUTE, available_minute_symbols, coverage, index_by_ts, load_minute_candles, mean_se, price_at, t_stat

WINDOW_MIN = 30
CONTROL_OFFSET_H = 4  # Kontrolle: dieselben Fenster um 4 Stunden versetzt (04:00, 12:00, 20:00 UTC), dort fällt kein Funding an
TAKER_ROUND_TRIP_BP = 16.0
SIZE_BUCKETS = ("<1bp", "=1bp", "1-3bp", ">3bp")


def size_bucket(rate: float) -> str:
    bp = abs(rate) * 10_000
    if abs(bp - 1.0) < 1e-6:
        return "=1bp"
    if bp < 1.0:
        return "<1bp"
    if bp <= 3.0:
        return "1-3bp"
    return ">3bp"


def sign_bucket(rate: float) -> str:
    return "pos" if rate > 0 else "neg" if rate < 0 else "null"


def funding_windows(candles: list[Candle], rates: dict[int, float], window_min: int = WINDOW_MIN) -> list[dict]:
    """Je Funding-Zeitpunkt mit vollständigen Kursen: Satz, Rendite vorher und nachher."""
    if not candles:
        return []
    index = index_by_ts(candles)
    first, last = candles[0].ts, candles[-1].ts
    out = []
    for ts in sorted(rates):
        if ts - window_min * MINUTE < first + MINUTE or ts + window_min * MINUTE > last + MINUTE:
            continue
        p0 = price_at(candles, ts - window_min * MINUTE, index)
        p1 = price_at(candles, ts, index)
        p2 = price_at(candles, ts + window_min * MINUTE, index)
        if p0 is None or p1 is None or p2 is None:
            continue
        rate = rates[ts]
        out.append(
            {
                "ts": ts,
                "rate": rate,
                "sign": sign_bucket(rate),
                "size": size_bucket(rate),
                "before": p1 / p0 - 1,
                "after": p2 / p1 - 1,
            }
        )
    return out


def _stats(rows: list[dict]) -> dict:
    before = [r["before"] * 10_000 for r in rows]
    after = [r["after"] * 10_000 for r in rows]
    # Fade: Short bei positivem Satz über das ganze Fenster, Funding kassiert
    fade = [(-1 if r["rate"] > 0 else 1) * (r["before"] + r["after"]) * 10_000 + abs(r["rate"]) * 10_000 for r in rows if r["rate"] != 0]
    bounce = [(1 if r["rate"] > 0 else -1) * r["after"] * 10_000 for r in rows if r["rate"] != 0]
    mb, sb = mean_se(before)
    ma, sa = mean_se(after)
    mf, sf = mean_se(fade)
    mo, so = mean_se(bounce)
    return {
        "n": len(rows),
        "rate_bp": (sum(r["rate"] for r in rows) / len(rows) * 10_000) if rows else None,
        "before_bp": mb, "before_se": sb, "before_t": t_stat(before),
        "after_bp": ma, "after_se": sa, "after_t": t_stat(after),
        "fade_gross_bp": mf, "fade_se": sf, "fade_net_bp": (mf - TAKER_ROUND_TRIP_BP) if mf is not None else None,
        "bounce_gross_bp": mo, "bounce_se": so, "bounce_net_bp": (mo - TAKER_ROUND_TRIP_BP) if mo is not None else None,
    }


def summarize(rows: list[dict]) -> dict:
    out = {"all": _stats(rows)}
    for sign in ("pos", "neg", "null"):
        subset = [r for r in rows if r["sign"] == sign]
        out[sign] = _stats(subset)
        for size in SIZE_BUCKETS:
            sub2 = [r for r in subset if r["size"] == size]
            if sub2:
                out[f"{sign}/{size}"] = _stats(sub2)
    return out


def analyze(symbols: list[str] | None = None) -> dict:
    symbols = symbols or available_minute_symbols()
    per_symbol: dict[str, dict] = {}
    all_rows: list[dict] = []
    all_control: list[dict] = []
    for symbol in symbols:
        candles = load_minute_candles(symbol)
        rates = load_funding(symbol)
        rows = funding_windows(candles, rates)
        if not rows:
            continue
        all_rows.extend(rows)
        control = funding_windows(candles, {ts + CONTROL_OFFSET_H * 3_600_000: rate for ts, rate in rates.items()})
        all_control.extend(control)
        per_symbol[symbol] = {"coverage": coverage(candles), "funding_points": len(rates), "summary": summarize(rows), "control": _stats(control)}
    return {
        "params": {"window_min": WINDOW_MIN, "taker_round_trip_bp": TAKER_ROUND_TRIP_BP, "size_buckets": list(SIZE_BUCKETS), "control_offset_h": CONTROL_OFFSET_H},
        "symbols": per_symbol,
        "total": summarize(all_rows),
        "control": _stats(all_control),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="")
    args = parser.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or None
    result = analyze(symbols)
    for symbol, row in result["symbols"].items():
        a = row["summary"]["all"]
        p = row["summary"]["pos"]
        print(f"{symbol:9s} n {a['n']:3d}  vorher {_f(a['before_bp'])} nachher {_f(a['after_bp'])} bp | pos n {p['n']:3d} vorher {_f(p['before_bp'])} nachher {_f(p['after_bp'])} fade net {_f(p['fade_net_bp'])}")
    print("gesamt:")
    for key, s in result["total"].items():
        print(f"  {key:10s} n {s['n']:4d} Satz {_f(s['rate_bp'])} bp  vorher {_f(s['before_bp'])}±{_f(s['before_se'])}  nachher {_f(s['after_bp'])}±{_f(s['after_se'])}  fade net {_f(s['fade_net_bp'])}  bounce net {_f(s['bounce_net_bp'])}")
    c = result["control"]
    print(f"  Kontrolle +{CONTROL_OFFSET_H} h: n {c['n']} vorher {_f(c['before_bp'])}±{_f(c['before_se'])} nachher {_f(c['after_bp'])}±{_f(c['after_se'])}")


def _f(x: float | None) -> str:
    return "  -  " if x is None else f"{x:6.2f}"


if __name__ == "__main__":
    main()
