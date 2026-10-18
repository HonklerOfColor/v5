#!/usr/bin/env python3
"""Nachlauf zur Trendfolge: Portfolio mit gemeinsamem Kapital, Parameter-Nachbarschaft, Quartale.

    python3 -m research.trend_report

Baut auf research.compare auf (gleiche Kerzen, gleiche Kosten). Die Listen
und Raster hier sind vor dem Lauf festgelegt; die Nachbarschaft dient der
Robustheit, nicht der Auswahl: der Bot bekommt 40/20 mit 3 × ATR.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from gridbot.params import GridParams
from research.costs import Costs
from research.data import available_symbols, load_candles, load_specs, split_index
from research.grid_variants import default_variant, run_grid_variant
from research.portfolio import run_trend_portfolio
from research.trend import TrendParams, run_trend

MD_PATH = Path("backtest/trend_followup.md")
JSON_PATH = Path("backtest/trend_followup.json")
COSTS = Costs()
BASE = TrendParams("trend_4h_40_20_atr3", 4, 40, 20, 14, 3.0)
# Nach Marktkapitalisierung und Umsatz, nicht nach Backtest-Ergebnis.
LIQUID = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT", "ADAUSDT", "SUIUSDT", "LINKUSDT", "AVAXUSDT"]
OOS_DAYS = 120
EQUITY = 50.0
LEVERAGE = 2


def _stamp(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _row(result: dict) -> str:
    pf = result.get("profit_factor")
    return (
        f"{result['net']:+.2f} | {result['max_drawdown_pct']:.1f} % | {result['trades']} | {result['wins']} | "
        f"{'–' if pf is None else f'{pf:.2f}'} | {result['fees']:.2f} | {result['funding']:.2f} | "
        f"{result['exits'].get('zu_klein', 0)}"
    )


def main() -> None:
    specs = load_specs()
    symbols = [s for s in available_symbols() if s in specs]
    candles = {s: load_candles(s) for s in symbols}
    split = {s: split_index(candles[s], OOS_DAYS) for s in symbols}
    split_ts = candles[symbols[0]][split[symbols[0]]].ts
    report: dict = {"generated_at": datetime.now(timezone.utc).isoformat(), "base": BASE.__dict__, "liquid": LIQUID}

    # 1. Portfolio mit gemeinsamem Kapital
    lines = [
        "# Trendfolge: Portfolio, Nachbarschaft, Quartale",
        "",
        f"Erzeugt {report['generated_at'][:16]}Z. Basis: Donchian 40/20 auf 4h, Stop 3 × ATR(14), eine Position je Symbol, "
        f"Taker rein und raus. Kosten wie im Strategie-Vergleich. Out-of-Sample ab {_stamp(split_ts)}.",
        "",
        "## Portfolio: 50 USDT gemeinsam, höchstens N Positionen",
        "",
        "Signale werden in Listenreihenfolge geprüft; volle Plätze lassen Signale verfallen. Risiko je Trade in Prozent des aktuellen Kapitals.",
        "",
        "| Universum | N | Risiko | Abschnitt | Netto | max DD | Trades | Gewinner | PF | Fees | Funding | zu klein |",
        "| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    portfolio_rows = []
    for universe_name, universe in (("28 Coins", symbols), ("10 liquide", LIQUID)):
        for max_pos in (3, 5):
            for risk in (0.01, 0.02):
                params = replace(BASE, risk_pct=risk)
                sub = {s: candles[s] for s in universe}
                sections = {
                    "IS": run_trend_portfolio({s: sub[s][: split[s]] for s in universe}, specs, params, COSTS, EQUITY, LEVERAGE, max_pos),
                    "OOS": run_trend_portfolio(sub, specs, params, COSTS, EQUITY, LEVERAGE, max_pos, start_ts=split_ts),
                    "Full": run_trend_portfolio(sub, specs, params, COSTS, EQUITY, LEVERAGE, max_pos),
                }
                for name, result in sections.items():
                    lines.append(f"| {universe_name} | {max_pos} | {risk*100:.0f} % | {name} | {_row(result)} |")
                    portfolio_rows.append({"universe": universe_name, "max_positions": max_pos, "risk": risk, "section": name, **{k: v for k, v in result.items() if k != "per_symbol"}})
    # Zwei vorab begründete Zusätze: Signal-Rangfolge nach Ausbruchsstärke, und Tageskerzen (20/10) mit 2 % Risiko.
    lines += [
        "",
        "## Portfolio-Zusätze: Rangfolge nach Ausbruchsstärke, Tageskerzen",
        "",
        "| Variante | Universum | N | Risiko | Abschnitt | Netto | max DD | Trades | Gewinner | PF | Fees | Funding | zu klein |",
        "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    daily = TrendParams("trend_1d_20_10_atr3", 24, 20, 10, 14, 3.0, risk_pct=0.02)
    extras = [
        ("4h 40/20 ×3, Rang", replace(BASE, risk_pct=0.01), True),
        ("4h 40/20 ×3, Rang, 2 %", replace(BASE, risk_pct=0.02), True),
        ("1d 20/10 ×3, 2 %", daily, False),
        ("1d 20/10 ×3, 2 %, Rang", daily, True),
    ]
    for label, params, rank in extras:
        for universe_name, universe in (("28 Coins", symbols), ("10 liquide", LIQUID)):
            for max_pos in (3, 5):
                sub = {s: candles[s] for s in universe}
                sections = {
                    "IS": run_trend_portfolio({s: sub[s][: split[s]] for s in universe}, specs, params, COSTS, EQUITY, LEVERAGE, max_pos, rank_signals=rank),
                    "OOS": run_trend_portfolio(sub, specs, params, COSTS, EQUITY, LEVERAGE, max_pos, start_ts=split_ts, rank_signals=rank),
                    "Full": run_trend_portfolio(sub, specs, params, COSTS, EQUITY, LEVERAGE, max_pos, rank_signals=rank),
                }
                for name, result in sections.items():
                    lines.append(f"| {label} | {universe_name} | {max_pos} | {params.risk_pct*100:.0f} % | {name} | {_row(result)} |")
                    portfolio_rows.append({"variant": label, "universe": universe_name, "max_positions": max_pos, "risk": params.risk_pct, "section": name, **{k: v for k, v in result.items() if k != "per_symbol"}})
    report["portfolio"] = portfolio_rows

    # 2. Nachbarschaft: Summe je Symbol (eigene 50 USDT), 2 % Risiko
    lines += [
        "",
        "## Parameter-Nachbarschaft (je Symbol eigene 50 USDT, Risiko 2 %, Summe über 28 Coins)",
        "",
        "| Kanal ein/aus | Stop × ATR | IS Summe | IS positiv | OOS Summe | OOS positiv | Full Summe | Full positiv | Full Median |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    grid_rows = []
    for entry in (30, 40, 50):
        for mult in (2.5, 3.0, 3.5):
            params = replace(BASE, entry_lookback=entry, exit_lookback=entry // 2, atr_stop_mult=mult, risk_pct=0.02)
            agg = {}
            for section in ("is", "oos", "full"):
                nets = []
                for s in symbols:
                    if section == "is":
                        nets.append(run_trend(candles[s][: split[s]], specs[s], params, COSTS, EQUITY, LEVERAGE)["net"])
                    elif section == "oos":
                        nets.append(run_trend(candles[s], specs[s], params, COSTS, EQUITY, LEVERAGE, split[s])["net"])
                    else:
                        nets.append(run_trend(candles[s], specs[s], params, COSTS, EQUITY, LEVERAGE)["net"])
                agg[section] = {"sum": sum(nets), "positive": sum(1 for n in nets if n > 0), "median": statistics.median(nets)}
            lines.append(
                f"| {entry}/{entry // 2} | {mult:.1f} | {agg['is']['sum']:+.2f} | {agg['is']['positive']}/28 | {agg['oos']['sum']:+.2f} | "
                f"{agg['oos']['positive']}/28 | {agg['full']['sum']:+.2f} | {agg['full']['positive']}/28 | {agg['full']['median']:+.2f} |"
            )
            grid_rows.append({"entry": entry, "atr_mult": mult, **agg})
    report["neighborhood"] = grid_rows

    # 3. Quartale: Summe je Symbol, Trend (2 % Risiko) gegen Grid-Default
    quarter_len = len(candles[symbols[0]]) // 4
    lines += [
        "",
        "## Quartale (je Symbol eigene 50 USDT, Summe über 28 Coins)",
        "",
        "Jedes Quartal startet frisch mit 50 USDT je Symbol; Indikatoren sehen die Zeit davor als Warmup.",
        "",
        "| Quartal | Buy & Hold Median | Trend 40/20 ×3, 2 % | positiv | Grid Default | positiv |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    quarters = []
    trend_params = replace(BASE, risk_pct=0.02)
    for q in range(4):
        a = q * quarter_len
        b = len(candles[symbols[0]]) if q == 3 else (q + 1) * quarter_len
        trend_nets, grid_nets, bh = [], [], []
        for s in symbols:
            series = candles[s][:b]
            start = min(a, len(series) - 1)
            trend_nets.append(run_trend(series, specs[s], trend_params, COSTS, EQUITY, LEVERAGE, start)["net"])
            grid_nets.append(run_grid_variant(series, specs[s], default_variant(), EQUITY, LEVERAGE, start)["net"])
            bh.append(100.0 * (series[-1].close / series[start].close - 1.0))
        label = f"{_stamp(candles[symbols[0]][a].ts)} – {_stamp(candles[symbols[0]][b - 1].ts)}"
        lines.append(
            f"| {label} | {statistics.median(bh):+.0f} % | {sum(trend_nets):+.2f} | {sum(1 for n in trend_nets if n > 0)}/28 | "
            f"{sum(grid_nets):+.2f} | {sum(1 for n in grid_nets if n > 0)}/28 |"
        )
        quarters.append({"label": label, "bh_median": statistics.median(bh), "trend": sum(trend_nets), "grid": sum(grid_nets)})
    report["quarters"] = quarters
    lines.append("")
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    JSON_PATH.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
