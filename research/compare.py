#!/usr/bin/env python3
"""Vergleich aller Kandidaten auf denselben Kerzen.

    python3 -m research.compare --oos-days 120 --equity 50

Jedes Symbol bekommt eigene 50 USDT. Drei Abschnitte: In-Sample (alles vor den
letzten oos_days Tagen), Out-of-Sample (die letzten oos_days Tage, Indikatoren
dürfen die Zeit davor als Warmup sehen) und das ganze Fenster. Die Kandidaten
und ihre Parameter stehen fest in CANDIDATES — kein Suchlauf über Parameter.
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from research.costs import Costs
from research.data import available_symbols, load_candles, load_specs, split_index
from research.grid_variants import (
    default_variant,
    run_grid_variant,
    winddown_hysteresis_variant,
    winddown_variant,
)
from research.meanrev import MeanRevParams, run_meanrev
from research.trend import TrendParams, run_trend

MD_PATH = Path("backtest/strategy_comparison.md")
JSON_PATH = Path("backtest/strategy_comparison.json")

COSTS = Costs()


def _grid(variant):
    return lambda candles, spec, equity, lev, start: run_grid_variant(candles, spec, variant, equity, lev, start)


def _trend(params: TrendParams):
    return lambda candles, spec, equity, lev, start: run_trend(candles, spec, params, COSTS, equity, lev, start)


def _meanrev(params: MeanRevParams):
    return lambda candles, spec, equity, lev, start: run_meanrev(candles, spec, params, COSTS, equity, lev, start)


# Vor dem Lauf festgelegt. Trend: zwei Kanal-Längen, zwei Stop-Weiten. Mean-Reversion: mit und ohne Trendfilter.
CANDIDATES = {
    "grid_default": _grid(default_variant()),
    "grid_winddown_48h": _grid(winddown_variant(48)),
    "grid_winddown_48h_hyst": _grid(winddown_hysteresis_variant(48)),
    "trend_4h_20_10_atr3": _trend(TrendParams("trend_4h_20_10_atr3", 4, 20, 10, 14, 3.0)),
    "trend_4h_40_20_atr3": _trend(TrendParams("trend_4h_40_20_atr3", 4, 40, 20, 14, 3.0)),
    "trend_4h_40_20_atr2": _trend(TrendParams("trend_4h_40_20_atr2", 4, 40, 20, 14, 2.0)),
    "trend_4h_40_20_atr3_long": _trend(TrendParams("trend_4h_40_20_atr3_long", 4, 40, 20, 14, 3.0, allow_short=False)),
    "trend_1d_20_10_atr3": _trend(TrendParams("trend_1d_20_10_atr3", 24, 20, 10, 14, 3.0)),
    "meanrev_bb20_atr1.5": _meanrev(MeanRevParams("meanrev_bb20_atr1.5")),
    "meanrev_bb20_atr1.5_adx25": _meanrev(MeanRevParams("meanrev_bb20_atr1.5_adx25", adx_filter=25.0)),
}


def _agg(rows: list[dict]) -> dict:
    nets = [row["net"] for row in rows]
    pf_num = sum(max(0.0, row["net"]) for row in rows)
    pf_den = sum(max(0.0, -row["net"]) for row in rows)
    return {
        "sum": sum(nets),
        "median": statistics.median(nets) if nets else 0.0,
        "positive": sum(1 for net in nets if net > 0),
        "n": len(nets),
        "fees": sum(row["fees"] for row in rows),
        "taker_fees": sum(row["taker_fees"] for row in rows),
        "funding": sum(row["funding"] for row in rows),
        "trades": sum(row["trades"] for row in rows),
        "avg_dd": statistics.mean(row["max_drawdown_pct"] for row in rows) if rows else 0.0,
        "worst_dd": max((row["max_drawdown_pct"] for row in rows), default=0.0),
        "pf_cross": (pf_num / pf_den) if pf_den > 0 else None,
    }


def _fmt(value, digits=2, sign=False):
    if value is None:
        return "–"
    if isinstance(value, float):
        return f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oos-days", type=int, default=120)
    parser.add_argument("--equity", type=float, default=50.0)
    parser.add_argument("--leverage", type=int, default=2)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--only", default="", help="Komma-Liste von Kandidaten")
    args = parser.parse_args()

    specs = load_specs()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or available_symbols()
    names = [n.strip() for n in args.only.split(",") if n.strip()] or list(CANDIDATES)
    results: dict[str, dict[str, dict[str, dict]]] = {name: {"is": {}, "oos": {}, "full": {}} for name in names}
    buy_hold: dict[str, dict[str, float]] = {}
    window = {}
    for symbol in symbols:
        if symbol not in specs:
            print(f"{symbol}: keine Spec, übersprungen")
            continue
        candles = load_candles(symbol)
        split = split_index(candles, args.oos_days)
        if split < 500 or len(candles) - split < 200:
            print(f"{symbol}: zu kurz ({len(candles)} Kerzen), übersprungen")
            continue
        window[symbol] = {
            "from": candles[0].ts,
            "split": candles[split].ts,
            "to": candles[-1].ts,
            "bars": len(candles),
        }
        buy_hold[symbol] = {
            "is": 100.0 * (candles[split - 1].close / candles[0].close - 1.0),
            "oos": 100.0 * (candles[-1].close / candles[split].close - 1.0),
            "full": 100.0 * (candles[-1].close / candles[0].close - 1.0),
        }
        spec = specs[symbol]
        for name in names:
            fn = CANDIDATES[name]
            results[name]["is"][symbol] = fn(candles[:split], spec, args.equity, args.leverage, 0)
            results[name]["oos"][symbol] = fn(candles, spec, args.equity, args.leverage, split)
            results[name]["full"][symbol] = fn(candles, spec, args.equity, args.leverage, 0)
        print(f"{symbol}: " + ", ".join(f"{n}={results[n]['full'][symbol]['net']:+.2f}" for n in names), flush=True)

    summary = {
        name: {section: _agg(list(results[name][section].values())) for section in ("is", "oos", "full")}
        for name in names
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "equity": args.equity,
        "leverage": args.leverage,
        "oos_days": args.oos_days,
        "costs": COSTS.__dict__,
        "symbols": list(window),
        "window": window,
        "buy_hold_pct": buy_hold,
        "summary": summary,
        "results": results,
    }
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(report, indent=1), encoding="utf-8")
    MD_PATH.write_text(render_markdown(report), encoding="utf-8")
    print(f"\nReport: {MD_PATH}")


def _stamp(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def render_markdown(report: dict) -> str:
    symbols = report["symbols"]
    any_window = report["window"][symbols[0]]
    lines = [
        "# Strategie-Vergleich",
        "",
        f"Erzeugt {report['generated_at'][:16]}Z. {len(symbols)} Symbole, jedes mit eigenen {report['equity']:.0f} USDT, Hebel {report['leverage']}×. "
        f"Fenster {_stamp(any_window['from'])} bis {_stamp(any_window['to'])}, Out-of-Sample ab {_stamp(any_window['split'])} ({report['oos_days']} Tage). "
        f"Maker {report['costs']['maker_fee']*100:.2f} %, Taker {report['costs']['taker_fee']*100:.2f} % plus {report['costs']['taker_slippage_pct']*1e4:.0f} bp Slippage, "
        f"Funding-Pauschale {report['costs']['funding_rate_8h']*100:.2f} % je 8h auf die Nettoposition.",
        "",
        "Alle Kandidaten und Parameter waren vor dem Lauf festgelegt. Kein Suchlauf. Jede Zeile ist die Summe über alle Symbole ohne Auswahl.",
        "",
        "Symbole: " + ", ".join(symbols),
        "",
    ]
    for section, title in (("is", "In-Sample"), ("oos", "Out-of-Sample"), ("full", "Ganzes Fenster")):
        lines += [
            f"## {title}",
            "",
            "| Kandidat | Summe | Median | positiv | PF (Summen) | Trades | Fees (Taker) | Funding | Ø DD | max DD |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        rows = sorted(report["summary"].items(), key=lambda kv: kv[1][section]["sum"], reverse=True)
        for name, sections in rows:
            a = sections[section]
            lines.append(
                f"| {name} | {a['sum']:+.2f} | {a['median']:+.2f} | {a['positive']}/{a['n']} | {_fmt(a['pf_cross'])} | {a['trades']} | "
                f"{a['fees']:.2f} ({a['taker_fees']:.2f}) | {a['funding']:.2f} | {a['avg_dd']:.1f} % | {a['worst_dd']:.1f} % |"
            )
        bh = [report["buy_hold_pct"][s][section] for s in symbols]
        lines += ["", f"Buy & Hold im Abschnitt: Median {statistics.median(bh):+.1f} %, Mittel {statistics.mean(bh):+.1f} %, positiv {sum(1 for x in bh if x > 0)}/{len(bh)}.", ""]

    lines += ["## Je Symbol, ganzes Fenster (Netto USDT)", ""]
    names = list(report["summary"])
    lines.append("| Symbol | B&H % | " + " | ".join(names) + " |")
    lines.append("| --- | ---: | " + " | ".join("---:" for _ in names) + " |")
    for symbol in symbols:
        cells = [f"{report['results'][n]['full'][symbol]['net']:+.2f}" for n in names]
        lines.append(f"| {symbol} | {report['buy_hold_pct'][symbol]['full']:+.0f} | " + " | ".join(cells) + " |")
    lines += ["", "## Je Symbol, Out-of-Sample (Netto USDT)", ""]
    lines.append("| Symbol | B&H % | " + " | ".join(names) + " |")
    lines.append("| --- | ---: | " + " | ".join("---:" for _ in names) + " |")
    for symbol in symbols:
        cells = [f"{report['results'][n]['oos'][symbol]['net']:+.2f}" for n in names]
        lines.append(f"| {symbol} | {report['buy_hold_pct'][symbol]['oos']:+.0f} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
