#!/usr/bin/env python3
"""Aktien-Perps am Wochenende: trägt die Wochenend-Bewegung des Perps Information
für die erste Handelsstunde des Montags, oder ist sie Rauschen, das die Kasse zurückdreht?

    python3 -m research.weekend

Fenster je Woche (UTC, Sommerzeit der US-Börse, gilt für den ganzen Datenzeitraum):
Freitag 20:00 (Kasse-Schluss) → Montag 13:30 (Kasse-Eröffnung) ist die
Wochenend-Bewegung des Perps. Dagegen gestellt: Montag 13:30 → 14:30 (erste
Handelsstunde) und Montag 13:30 → 20:00 (ganzer Handelstag). Kurs zu einem
Zeitpunkt ist der Schluss der Minutenkerze, die dort endet (bis 30 Minuten alt).

Simulation (vorab festgelegt): Montag 13:25 UTC als Taker **gegen** die bis dahin
gelaufene Wochenend-Bewegung positionieren (Fade), nur wenn sie über 1,5 % liegt,
Ausstieg 14:30 oder 20:00 als Taker. 50 USDT Notional, echtes Bitget-Funding
um 16:00 UTC bei Ausstieg 20:00. Das Spiegelbild (mit der Bewegung) ist der
negative Brutto-Wert bei gleichen Kosten und wird mit ausgewiesen.
US-Feiertage an Montagen (Kasse geschlossen) fallen heraus.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from gridbot.candles import Candle
from research.costs import Costs
from research.funding import load_funding
from research.micro import DAY, HOUR, MINUTE, coverage, index_by_ts, load_minute_candles, mean_se, pearson, price_at, t_stat

STOCK_SYMBOLS = ["TSLAUSDT", "NVDAUSDT", "MSTRUSDT", "INTCUSDT", "SNDKUSDT"]
FRIDAY_CLOSE = (20, 0)
MONDAY_OPEN = (13, 30)
MONDAY_FIRST_HOUR = (14, 30)
MONDAY_CLOSE = (20, 0)
ENTRY_TIME = (13, 25)
THRESHOLD = 0.015
NOTIONAL = 50.0
US_HOLIDAYS_MONDAY = {"2026-09-07"}  # Labor Day; Columbus Day ist Handelstag
FUNDING_INTERVAL = 8 * HOUR


def _at(day_ts: int, hm: tuple[int, int]) -> int:
    return day_ts + hm[0] * HOUR + hm[1] * MINUTE


def mondays_between(first_ts: int, last_ts: int) -> list[int]:
    """Mitternacht UTC jedes Montags, dessen Freitag-Schluss und Montag-Schluss im Bereich liegen."""
    start = datetime.fromtimestamp(first_ts / 1000, tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    while start.weekday() != 0:
        start += timedelta(days=1)
    out = []
    day = start
    while True:
        monday = int(day.timestamp() * 1000)
        if _at(monday, MONDAY_CLOSE) > last_ts + MINUTE:
            break
        if _at(monday - 3 * DAY, FRIDAY_CLOSE) >= first_ts:
            out.append(monday)
        day += timedelta(days=7)
    return out


def weekend_windows(candles: list[Candle]) -> list[dict]:
    if not candles:
        return []
    index = index_by_ts(candles)
    out = []
    for monday in mondays_between(candles[0].ts, candles[-1].ts):
        date = datetime.fromtimestamp(monday / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        if date in US_HOLIDAYS_MONDAY:
            continue
        friday = monday - 3 * DAY
        prices = {
            "fri": price_at(candles, _at(friday, FRIDAY_CLOSE), index),
            "entry": price_at(candles, _at(monday, ENTRY_TIME), index),
            "open": price_at(candles, _at(monday, MONDAY_OPEN), index),
            "h1": price_at(candles, _at(monday, MONDAY_FIRST_HOUR), index),
            "close": price_at(candles, _at(monday, MONDAY_CLOSE), index),
        }
        if any(v is None for v in prices.values()):
            continue
        out.append(
            {
                "monday": date,
                "monday_ts": monday,
                **{f"p_{k}": v for k, v in prices.items()},
                "move_weekend": prices["open"] / prices["fri"] - 1,
                "move_entry": prices["entry"] / prices["fri"] - 1,
                "move_h1": prices["h1"] / prices["open"] - 1,
                "move_day": prices["close"] / prices["open"] - 1,
            }
        )
    return out


def summarize_windows(windows: list[dict]) -> dict:
    we = [w["move_weekend"] for w in windows]
    h1 = [w["move_h1"] for w in windows]
    day = [w["move_day"] for w in windows]
    return {
        "weeks": len(windows),
        "corr_h1": pearson(we, h1),
        "corr_day": pearson(we, day),
        "same_sign_h1": _same_sign(we, h1),
        "same_sign_day": _same_sign(we, day),
        "mean_abs_weekend_bp": (sum(abs(x) for x in we) / len(we) * 10_000) if we else None,
        "mean_abs_h1_bp": (sum(abs(x) for x in h1) / len(h1) * 10_000) if h1 else None,
        "over_threshold": sum(1 for x in we if abs(x) > THRESHOLD),
    }


def _same_sign(xs: list[float], ys: list[float]) -> float | None:
    pairs = [(x, y) for x, y in zip(xs, ys) if x != 0 and y != 0]
    if not pairs:
        return None
    return sum(1 for x, y in pairs if (x > 0) == (y > 0)) / len(pairs)


def simulate(windows: list[dict], costs: Costs, rates: dict[int, float] | None = None, exit_key: str = "h1", direction: str = "fade") -> dict:
    """Taker-Einstieg 13:25 gegen (fade) oder mit (follow) der Wochenend-Bewegung, Taker-Ausstieg."""
    rates = rates or {}
    trades = []
    for w in windows:
        move = w["move_entry"]
        if abs(move) <= THRESHOLD:
            continue
        against = move > 0
        short = against if direction == "fade" else not against
        p_in, p_out = w["p_entry"], w[f"p_{exit_key}"]
        qty = NOTIONAL / p_in
        if short:
            entry, exit_px = costs.taker_sell(p_in), costs.taker_buy(p_out)
            gross = qty * (entry - exit_px)
        else:
            entry, exit_px = costs.taker_buy(p_in), costs.taker_sell(p_out)
            gross = qty * (exit_px - entry)
        fees = qty * (entry + exit_px) * costs.taker_fee
        funding = 0.0
        if exit_key == "close":
            start, end = _at(w["monday_ts"], ENTRY_TIME), _at(w["monday_ts"], MONDAY_CLOSE)
            ts = (start // FUNDING_INTERVAL + 1) * FUNDING_INTERVAL
            while ts <= end:
                rate = rates.get(ts)
                if rate is not None:
                    funding += NOTIONAL * (-rate if short else rate)
                ts += FUNDING_INTERVAL
        trades.append({"monday": w["monday"], "side": "short" if short else "long", "gross": gross, "fees": fees, "funding": funding, "net": gross - fees - funding})
    nets_bp = [t["net"] / NOTIONAL * 10_000 for t in trades]
    mean, se = mean_se(nets_bp)
    return {
        "trades": len(trades),
        "net": sum(t["net"] for t in trades),
        "gross": sum(t["gross"] for t in trades),
        "fees": sum(t["fees"] for t in trades),
        "funding": sum(t["funding"] for t in trades),
        "wins": sum(1 for t in trades if t["net"] > 0),
        "mean_bp": mean,
        "se_bp": se,
        "t": t_stat(nets_bp),
        "trade_list": trades,
    }


def analyze(symbols: list[str] | None = None, costs: Costs | None = None) -> dict:
    costs = costs or Costs()
    symbols = symbols or STOCK_SYMBOLS
    per_symbol: dict[str, dict] = {}
    all_windows: list[dict] = []
    for symbol in symbols:
        candles = load_minute_candles(symbol)
        windows = weekend_windows(candles)
        if not windows:
            continue
        rates = load_funding(symbol)
        all_windows.extend(windows)
        per_symbol[symbol] = {
            "coverage": coverage(candles),
            "summary": summarize_windows(windows),
            "windows": windows,
            "fade_h1": simulate(windows, costs, rates, "h1", "fade"),
            "fade_close": simulate(windows, costs, rates, "close", "fade"),
            "follow_h1": simulate(windows, costs, rates, "h1", "follow"),
            "follow_close": simulate(windows, costs, rates, "close", "follow"),
        }
    pooled = {
        "summary": summarize_windows(all_windows),
        **{key: _pool([v[key] for v in per_symbol.values()]) for key in ("fade_h1", "fade_close", "follow_h1", "follow_close")},
    }
    return {
        "params": {"threshold": THRESHOLD, "notional": NOTIONAL, "entry_utc": "Mo 13:25", "exits_utc": ["Mo 14:30", "Mo 20:00"], "holidays": sorted(US_HOLIDAYS_MONDAY)},
        "symbols": per_symbol,
        "total": pooled,
    }


def _pool(parts: list[dict]) -> dict:
    trades = [t for p in parts for t in p["trade_list"]]
    nets_bp = [t["net"] / NOTIONAL * 10_000 for t in trades]
    mean, se = mean_se(nets_bp)
    return {
        "trades": len(trades),
        "net": sum(t["net"] for t in trades),
        "gross": sum(t["gross"] for t in trades),
        "fees": sum(t["fees"] for t in trades),
        "funding": sum(t["funding"] for t in trades),
        "wins": sum(1 for t in trades if t["net"] > 0),
        "mean_bp": mean,
        "se_bp": se,
        "t": t_stat(nets_bp),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default=",".join(STOCK_SYMBOLS))
    args = parser.parse_args()
    result = analyze([s.strip().upper() for s in args.symbols.split(",") if s.strip()])
    for symbol, row in result["symbols"].items():
        s = row["summary"]
        print(
            f"{symbol:9s} Wochen {s['weeks']:2d}  corr h1 {_f(s['corr_h1'])} day {_f(s['corr_day'])}  "
            f"gleiches Vorzeichen h1 {_f(s['same_sign_h1'])}  >1,5 %: {s['over_threshold']}  "
            f"fade h1 net {row['fade_h1']['net']:+.2f} ({row['fade_h1']['trades']})  fade close net {row['fade_close']['net']:+.2f}"
        )
        for w in row["windows"]:
            print(f"    {w['monday']}  WE {w['move_weekend'] * 100:+6.2f} %  h1 {w['move_h1'] * 100:+6.2f} %  Tag {w['move_day'] * 100:+6.2f} %")
    t = result["total"]
    print("gesamt", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in t["summary"].items()})
    for key in ("fade_h1", "fade_close", "follow_h1", "follow_close"):
        p = t[key]
        print(f"  {key:12s} Trades {p['trades']:3d} net {p['net']:+7.2f} fees {p['fees']:.2f} mean {_f(p['mean_bp'])} bp t={_f(p['t'])}")


def _f(x: float | None) -> str:
    return "  -  " if x is None else f"{x:6.2f}"


if __name__ == "__main__":
    main()
