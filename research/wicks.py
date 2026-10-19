#!/usr/bin/env python3
"""Liquidations-Dochte auf 1-Minuten-Kerzen: Häufigkeit, Rückkehr, und ein Maker-Fade.

    python3 -m research.wicks                 # alle Symbole in data/research/1m/
    python3 -m research.wicks --symbols BTCUSDT,ETHUSDT

Alle Schwellen standen vor dem Lauf fest (keine Parametersuche):

Ereignis: Minutentief mehr als 3 × ATR(14, 1h-Basis) unter dem Schluss der
Vorminute, spiegelbildlich für Hochs. Die ATR ist die der letzten
abgeschlossenen Stunde. Gemessen wird der Anteil der Ereignisse, bei denen der
Kurs innerhalb von 15 bzw. 60 Minuten mindestens 50 % des Dochts zurückholt
(Schluss der Ereigniskerze oder ein späteres Hoch über der Hälfte).

Simulation (long): Jede Minute liegt ein Maker-Limit-Kauf bei Vorschluss − 2 × ATR.
Fill nur, wenn das Minutentief unter dem Limit liegt und die Kerze über dem Limit
eröffnet (sonst wäre die Post-only-Order abgelehnt oder Taker). Ziel Vorschluss −
0,5 × ATR als Maker, Stop Vorschluss − 4 × ATR als Taker (mit Slippage), Zeitstopp
60 Minuten zum Schluss als Taker. In derselben Kerze gilt der Stop vor dem Ziel;
das Ziel zählt in der Einstiegskerze nur, wenn die Kerze darüber schließt. Eine
Position je Symbol, 50 USDT Notional, echtes Bitget-Funding, wenn ein
Funding-Zeitpunkt in die Haltezeit fällt. Short ist das Spiegelbild.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from gridbot.candles import Candle
from research.costs import Costs
from research.funding import load_funding
from research.micro import (
    DAY,
    MINUTE,
    available_minute_symbols,
    coverage,
    hourly_atr_per_minute,
    load_minute_candles,
    mean_se,
    t_stat,
)

EVENT_MULT = 3.0
RECOVER_SHARE = 0.5
WINDOWS_MIN = (15, 60)
MAX_GAP_MIN = 5  # Vorminute muss höchstens 5 Minuten zurückliegen, sonst ist der Sprung kein Docht

ENTRY_MULT = 2.0
TARGET_MULT = 0.5
STOP_MULT = 4.0
TIME_STOP_MIN = 60
NOTIONAL = 50.0
FUNDING_INTERVAL = 8 * 3_600_000


@dataclass(frozen=True)
class WickEvent:
    index: int
    ts: int
    side: str  # "low" oder "high"
    prev_close: float
    atr: float
    depth: float  # Docht in Preis (positiv)

    @property
    def depth_atr(self) -> float:
        return self.depth / self.atr


def detect_wicks(candles: list[Candle], atrs: list[float | None], mult: float = EVENT_MULT) -> list[WickEvent]:
    events: list[WickEvent] = []
    for i in range(1, len(candles)):
        atr = atrs[i]
        if atr is None or atr <= 0:
            continue
        prev = candles[i - 1]
        if candles[i].ts - prev.ts > MAX_GAP_MIN * MINUTE:
            continue
        c = candles[i]
        if c.low < prev.close - mult * atr:
            events.append(WickEvent(i, c.ts, "low", prev.close, atr, prev.close - c.low))
        if c.high > prev.close + mult * atr:
            events.append(WickEvent(i, c.ts, "high", prev.close, atr, c.high - prev.close))
    return events


def recovered(candles: list[Candle], event: WickEvent, window_min: int, share: float = RECOVER_SHARE) -> bool:
    """Holt der Kurs innerhalb von window_min Minuten mindestens share des Dochts zurück?"""
    c = candles[event.index]
    deadline = event.ts + window_min * MINUTE
    if event.side == "low":
        threshold = c.low + share * event.depth
        if c.close >= threshold:
            return True
        for k in range(event.index + 1, len(candles)):
            if candles[k].ts > deadline:
                break
            if candles[k].high >= threshold:
                return True
        return False
    threshold = c.high - share * event.depth
    if c.close <= threshold:
        return True
    for k in range(event.index + 1, len(candles)):
        if candles[k].ts > deadline:
            break
        if candles[k].low <= threshold:
            return True
    return False


def measure_events(candles: list[Candle], atrs: list[float | None]) -> dict:
    events = detect_wicks(candles, atrs)
    cov = coverage(candles)
    out: dict = {"events": len(events), "per_day": (len(events) / cov["days"]) if cov["days"] else None}
    for side in ("low", "high"):
        subset = [e for e in events if e.side == side]
        row: dict = {"events": len(subset), "median_depth_atr": _median([e.depth_atr for e in subset])}
        for window in WINDOWS_MIN:
            hits = sum(1 for e in subset if recovered(candles, e, window))
            row[f"recovered_{window}m"] = (hits / len(subset)) if subset else None
        out[side] = row
    return out


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def _funding_between(rates: dict[int, float], start_ts: int, end_ts: int, side: str, notional: float) -> float:
    """Funding-Kosten (positiv) zwischen start (exkl.) und end (inkl.)."""
    total = 0.0
    first = (start_ts // FUNDING_INTERVAL + 1) * FUNDING_INTERVAL
    ts = first
    while ts <= end_ts:
        rate = rates.get(ts)
        if rate is not None:
            total += notional * (rate if side == "long" else -rate)
        ts += FUNDING_INTERVAL
    return total


def simulate_fade(
    candles: list[Candle],
    atrs: list[float | None],
    costs: Costs,
    rates: dict[int, float] | None = None,
    side: str = "long",
    notional: float = NOTIONAL,
) -> dict:
    rates = rates or {}
    sign = 1.0 if side == "long" else -1.0
    trades: list[dict] = []
    pos: dict | None = None
    i = 1
    n = len(candles)
    while i < n:
        c = candles[i]
        if pos is None:
            atr = atrs[i]
            prev = candles[i - 1]
            if atr is None or atr <= 0 or c.ts - prev.ts > MAX_GAP_MIN * MINUTE:
                i += 1
                continue
            limit = prev.close - sign * ENTRY_MULT * atr
            opened_ok = c.open > limit if side == "long" else c.open < limit
            touched = c.low < limit if side == "long" else c.high > limit
            if not (opened_ok and touched):
                i += 1
                continue
            pos = {
                "entry_ts": c.ts,
                "entry": limit,
                "qty": notional / limit,
                "target": prev.close - sign * TARGET_MULT * atr,
                "stop": prev.close - sign * STOP_MULT * atr,
                "deadline": c.ts + TIME_STOP_MIN * MINUTE,
                "fee_in": notional * costs.maker_fee,
            }
            # Einstiegskerze: Stop zuerst, Ziel nur über den Schluss
            stop_hit = c.low <= pos["stop"] if side == "long" else c.high >= pos["stop"]
            target_hit = c.close >= pos["target"] if side == "long" else c.close <= pos["target"]
        else:
            stop_hit = c.low <= pos["stop"] if side == "long" else c.high >= pos["stop"]
            target_hit = c.high >= pos["target"] if side == "long" else c.low <= pos["target"]
        if stop_hit:
            px = costs.taker_sell(pos["stop"]) if side == "long" else costs.taker_buy(pos["stop"])
            trades.append(_close(pos, c.ts, px, "stop", True, costs, rates, side, sign))
            pos = None
        elif target_hit:
            trades.append(_close(pos, c.ts, pos["target"], "ziel", False, costs, rates, side, sign))
            pos = None
        elif c.ts >= pos["deadline"]:
            px = costs.taker_sell(c.close) if side == "long" else costs.taker_buy(c.close)
            trades.append(_close(pos, c.ts, px, "zeit", True, costs, rates, side, sign))
            pos = None
        i += 1
    return summarize_trades(trades, notional)


def _close(pos: dict, ts: int, px: float, reason: str, taker: bool, costs: Costs, rates: dict[int, float], side: str, sign: float) -> dict:
    gross = pos["qty"] * (px - pos["entry"]) * sign
    fee_out = pos["qty"] * px * (costs.taker_fee if taker else costs.maker_fee)
    funding = _funding_between(rates, pos["entry_ts"], ts, side, pos["qty"] * pos["entry"])
    fees = pos["fee_in"] + fee_out
    return {
        "entry_ts": pos["entry_ts"],
        "exit_ts": ts,
        "entry": pos["entry"],
        "exit": px,
        "reason": reason,
        "gross": gross,
        "fees": fees,
        "maker_fees": pos["fee_in"] + (0.0 if taker else fee_out),
        "taker_fees": fee_out if taker else 0.0,
        "funding": funding,
        "net": gross - fees - funding,
    }


def summarize_trades(trades: list[dict], notional: float) -> dict:
    nets_bp = [t["net"] / notional * 10_000 for t in trades]
    mean, se = mean_se(nets_bp)
    exits: dict[str, int] = {}
    for t in trades:
        exits[t["reason"]] = exits.get(t["reason"], 0) + 1
    return {
        "trades": len(trades),
        "net": sum(t["net"] for t in trades),
        "gross": sum(t["gross"] for t in trades),
        "fees": sum(t["fees"] for t in trades),
        "maker_fees": sum(t["maker_fees"] for t in trades),
        "taker_fees": sum(t["taker_fees"] for t in trades),
        "funding": sum(t["funding"] for t in trades),
        "wins": sum(1 for t in trades if t["net"] > 0),
        "exits": exits,
        "mean_bp": mean,
        "se_bp": se,
        "t": t_stat(nets_bp),
    }


def merge_summaries(parts: list[dict]) -> dict:
    """Summen über Symbole; mean/se/t aus den Einzel-Trades lassen sich hier nicht
    rekonstruieren, deshalb trades-gewichtet aus mean und se."""
    trades = sum(p["trades"] for p in parts)
    out = {
        "trades": trades,
        "net": sum(p["net"] for p in parts),
        "gross": sum(p["gross"] for p in parts),
        "fees": sum(p["fees"] for p in parts),
        "maker_fees": sum(p["maker_fees"] for p in parts),
        "taker_fees": sum(p["taker_fees"] for p in parts),
        "funding": sum(p["funding"] for p in parts),
        "wins": sum(p["wins"] for p in parts),
        "exits": {},
    }
    for p in parts:
        for k, v in p["exits"].items():
            out["exits"][k] = out["exits"].get(k, 0) + v
    out["mean_bp"] = (sum(p["mean_bp"] * p["trades"] for p in parts if p["mean_bp"] is not None) / trades) if trades else None
    # Varianz der Summe aus den Einzel-SEs (unabhängige Symbole angenommen)
    var_sum = sum((p["se_bp"] * p["trades"]) ** 2 for p in parts if p["se_bp"] is not None)
    out["se_bp"] = (var_sum ** 0.5 / trades) if trades and var_sum > 0 else None
    out["t"] = (out["mean_bp"] / out["se_bp"]) if out["se_bp"] else None
    return out


def analyze(symbols: list[str], costs: Costs | None = None) -> dict:
    costs = costs or Costs()
    per_symbol: dict[str, dict] = {}
    for symbol in symbols:
        candles = load_minute_candles(symbol)
        if len(candles) < 20 * 60:
            continue
        atrs = hourly_atr_per_minute(candles, 14)
        rates = load_funding(symbol)
        per_symbol[symbol] = {
            "coverage": coverage(candles),
            "events": measure_events(candles, atrs),
            "long": simulate_fade(candles, atrs, costs, rates, "long"),
            "short": simulate_fade(candles, atrs, costs, rates, "short"),
        }
    total = {
        "events": sum(v["events"]["events"] for v in per_symbol.values()),
        "long": merge_summaries([v["long"] for v in per_symbol.values()]),
        "short": merge_summaries([v["short"] for v in per_symbol.values()]),
    }
    return {
        "params": {
            "event_mult": EVENT_MULT, "recover_share": RECOVER_SHARE, "windows_min": list(WINDOWS_MIN),
            "entry_mult": ENTRY_MULT, "target_mult": TARGET_MULT, "stop_mult": STOP_MULT,
            "time_stop_min": TIME_STOP_MIN, "notional": NOTIONAL, "max_gap_min": MAX_GAP_MIN,
        },
        "symbols": per_symbol,
        "total": total,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="")
    args = parser.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or available_minute_symbols()
    result = analyze(symbols)
    for symbol, row in result["symbols"].items():
        ev, lo, sh = row["events"], row["long"], row["short"]
        print(
            f"{symbol:9s} Ereignisse {ev['events']:4d} ({ev['per_day'] or 0:.2f}/Tag)  "
            f"Tief 15m {_pct(ev['low']['recovered_15m'])} 60m {_pct(ev['low']['recovered_60m'])}  "
            f"long {lo['trades']:4d} Trades net {lo['net']:+7.2f} fees {lo['fees']:.2f}  "
            f"short {sh['trades']:4d} net {sh['net']:+7.2f}"
        )
    t = result["total"]
    print(f"gesamt   long net {t['long']['net']:+.2f} ({t['long']['trades']} Trades, t={t['long']['t']})  short net {t['short']['net']:+.2f}")
    print(json.dumps(t, indent=1, default=str)[:400])


def _pct(x: float | None) -> str:
    return "  -  " if x is None else f"{100 * x:4.0f} %"


if __name__ == "__main__":
    main()
