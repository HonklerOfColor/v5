#!/usr/bin/env python3
"""Zweite Runde: strukturelle Quellen und weitere Familien, mit echten Funding-Raten.

    python3 -m research.alternatives_report

Braucht data/research/ (research.fetch) und data/research/funding_binance/
(research.funding.fetch_all_binance). Kandidaten und Raster sind vor dem Lauf
festgelegt. Kapital-Skalierung der Trendfolge zeigt, ab welchem Konto die
Strategie überhaupt handelbar ist — das ist keine Auswahl, sondern eine
Mindestgrößen-Frage.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from research.carry import CarryParams, run_carry
from research.costs import Costs
from research.data import available_symbols, load_candles, load_specs, split_index
from research.funding import load_binance_funding, load_funding
from research.momentum import MomentumParams, run_momentum
from research.portfolio import run_trend_portfolio
from research.pullback import PullbackParams, run_pullback
from research.trend import TrendParams, run_trend

MD_PATH = Path("backtest/alternatives.md")
JSON_PATH = Path("backtest/alternatives.json")
OOS_DAYS = 120
LEVERAGE = 2
LIQUID = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT", "ADAUSDT", "SUIUSDT", "LINKUSDT", "AVAXUSDT"]
TREND = TrendParams("trend_4h_40_20_atr3", 4, 40, 20, 14, 3.0)


def _stamp(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _pf(value) -> str:
    return "–" if value is None else f"{value:.2f}"


def main() -> None:
    specs = load_specs()
    symbols = [s for s in available_symbols() if s in specs]
    candles = {s: load_candles(s) for s in symbols}
    books = {s: load_binance_funding(s) for s in symbols}
    costs = Costs(funding_books=books)
    split = {s: split_index(candles[s], OOS_DAYS) for s in symbols}
    ref = candles[symbols[0]]
    split_ts = ref[split[symbols[0]]].ts
    start_ts, end_ts = ref[0].ts, ref[-1].ts
    quarter = len(ref) // 4
    quarter_ts = [ref[q * quarter].ts for q in range(4)] + [end_ts + 1]
    report: dict = {"generated_at": datetime.now(timezone.utc).isoformat(), "symbols": symbols}
    L: list[str] = [
        "# Alternativen, zweite Runde: Funding, Carry, Momentum, Pullback, Kapital",
        "",
        f"Erzeugt {report['generated_at'][:16]}Z. Gleiche Kerzen und Kosten wie im Strategie-Vergleich (28 Coins, {_stamp(start_ts)} bis {_stamp(end_ts)}, "
        f"Out-of-Sample ab {_stamp(split_ts)}), aber mit **echten Funding-Raten** statt der Pauschale: Long zahlt, Short bekommt.",
        "",
    ]

    # 1. Funding-Proxy
    L += [
        "## Funding-Raten: Bitget (90 Tage verfügbar) gegen Binance als Jahres-Proxy",
        "",
        "Bitget liefert nur 90 Tage Historie. Für das Jahr dient Binance als Näherung. In den 90 gemeinsamen Tagen lag Bitget im Mittel höher; die Backtests mit Binance-Raten sind für Short-Seiten eher zu pessimistisch, für Long-Seiten eher zu optimistisch.",
        "",
        "| Coin | Bitget % p.a. (90 T) | Binance % p.a. (90 T) | Korrelation | Binance % p.a. (Jahr) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    proxy_rows = []
    for s in symbols:
        bg, bn = load_funding(s), books[s]
        common = [t for t in bg if t in bn]
        if len(common) < 50:
            continue
        a = [bg[t] for t in common]
        b = [bn[t] for t in common]
        ma, mb = statistics.mean(a), statistics.mean(b)
        cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        sa = sum((x - ma) ** 2 for x in a) ** 0.5
        sb = sum((y - mb) ** 2 for y in b) ** 0.5
        days = (max(common) - min(common)) / 86_400_000
        year_days = (max(bn) - min(bn)) / 86_400_000 if bn else 1
        row = {
            "symbol": s,
            "bitget_pa": 100 * sum(a) / days * 365,
            "binance_pa": 100 * sum(b) / days * 365,
            "corr": (cov / (sa * sb)) if sa and sb else None,
            "binance_year_pa": 100 * sum(bn.values()) / year_days * 365,
        }
        proxy_rows.append(row)
        L.append(f"| {s} | {row['bitget_pa']:+.1f} | {row['binance_pa']:+.1f} | {_pf(row['corr'])} | {row['binance_year_pa']:+.1f} |")
    L.append(
        f"| **Mittel** | {statistics.mean(r['bitget_pa'] for r in proxy_rows):+.1f} | {statistics.mean(r['binance_pa'] for r in proxy_rows):+.1f} | "
        f"{statistics.mean(r['corr'] for r in proxy_rows if r['corr'] is not None):.2f} | {statistics.mean(r['binance_year_pa'] for r in proxy_rows):+.1f} |"
    )
    report["funding_proxy"] = proxy_rows

    # 2. Carry
    L += [
        "",
        "## Cash-and-Carry (Spot long, Perp short), 50 USDT",
        "",
        "Kein Kursrisiko. Kapital halb Spot, halb Perp-Margin, also 25 USDT Perp-Notional. Kosten je Wechsel: Spot-Fee und Perp-Taker plus 2 bp auf jeder Seite.",
        "",
        "| Variante | Spot-Fee | Abschnitt | Netto | Funding-Ertrag | Fees | Wechsel | Wochen in Cash |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    carry_rows = []
    for spot_fee in (0.001, 0.002):
        for label, cands, lookback in (("Rotation wöchentlich, 10 liquide", LIQUID, 7), ("Rotation wöchentlich, 28 Coins", symbols, 7), ("Rotation 28-Tage-Fenster, 10 liquide", LIQUID, 28)):
            params = CarryParams(f"carry_{lookback}d", spot_fee=spot_fee, lookback_days=lookback)
            for section, a, b in (("IS", start_ts, split_ts - 1), ("OOS", split_ts, end_ts), ("Jahr", start_ts, end_ts)):
                res = run_carry(books, params, 50.0, a, b, cands)
                carry_rows.append({"variant": label, "spot_fee": spot_fee, "section": section, **{k: v for k, v in res.items() if k != "per_symbol"}})
                L.append(f"| {label} | {spot_fee*100:.1f} % | {section} | {res['net']:+.2f} | {res['income']:.2f} | {res['fees']:.2f} | {res['switches']} | {res['weeks_in_cash']}/{res['weeks']} |")
    # Kaufen-und-halten je Coin: nur ein Einstieg, ein Ausstieg
    L += ["", "Ein Coin, ein Jahr gehalten, Spot-Fee 0,1 %: Funding-Summe × 25 USDT minus zwei Wechselkosten.", "", "| Coin | Funding-Ertrag | Netto Jahr |", "| --- | ---: | ---: |"]
    hold_rows = []
    for s in LIQUID:
        income = sum(books[s].values()) * 25.0
        net = income - 2 * 25.0 * (0.001 + 0.0006 + 0.0002)
        hold_rows.append({"symbol": s, "income": income, "net": net})
        L.append(f"| {s} | {income:+.2f} | {net:+.2f} |")
    report["carry"] = {"rotation": carry_rows, "hold": hold_rows}

    # 3. Momentum
    L += [
        "",
        "## Querschnitts-Momentum, wöchentlich, 28 Coins, gemeinsames Kapital",
        "",
        "Top 3 long, Flop 3 short (oder nur long), Brutto-Exposure 100 % des Kapitals, kein Stop in der Woche, echtes Funding.",
        "",
        "| Lookback | Richtung | Kapital | IS | OOS | Jahr | max DD Jahr | Trades | Fees Jahr |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    momentum_rows = []
    for lookback in (14, 28, 56):
        for long_short in (True, False):
            for equity in (50.0, 1000.0):
                p = MomentumParams(f"xs_{lookback}d", lookback_days=lookback, long_short=long_short)
                is_res = run_momentum({s: candles[s][: split[s]] for s in symbols}, specs, p, costs, equity, LEVERAGE)
                oos = run_momentum(candles, specs, p, costs, equity, LEVERAGE, start_ts=split_ts)
                full = run_momentum(candles, specs, p, costs, equity, LEVERAGE)
                momentum_rows.append({"lookback": lookback, "long_short": long_short, "equity": equity, "is": is_res["net"], "oos": oos["net"], "full": full["net"], "dd": full["max_drawdown_pct"], "trades": full["trades"], "fees": full["fees"]})
                L.append(
                    f"| {lookback} T | {'long+short' if long_short else 'nur long'} | {equity:.0f} | {is_res['net']:+.2f} | {oos['net']:+.2f} | {full['net']:+.2f} | "
                    f"{full['max_drawdown_pct']:.1f} % | {full['trades']} | {full['fees']:.2f} |"
                )
    report["momentum"] = momentum_rows

    # 4. Pullback
    L += [
        "",
        "## Pullback im Trend (4h, RSI(2) unter 10 über SMA 200), je Symbol 50 USDT",
        "",
        "| Variante | IS Summe | IS positiv | OOS Summe | OOS positiv | Jahr Summe | Jahr positiv | Trades | Fees |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    pullback_rows = []
    for label, p in (("long+short", PullbackParams()), ("nur long", PullbackParams(allow_short=False)), ("long+short, RSI 5/95", PullbackParams(rsi_low=5, rsi_high=95))):
        agg = {}
        for section in ("is", "oos", "full"):
            nets, trades, fees = [], 0, 0.0
            for s in symbols:
                if section == "is":
                    res = run_pullback(candles[s][: split[s]], specs[s], p, costs, 50.0, LEVERAGE)
                elif section == "oos":
                    res = run_pullback(candles[s], specs[s], p, costs, 50.0, LEVERAGE, split[s])
                else:
                    res = run_pullback(candles[s], specs[s], p, costs, 50.0, LEVERAGE)
                nets.append(res["net"])
                trades += res["trades"]
                fees += res["fees"]
            agg[section] = {"sum": sum(nets), "positive": sum(1 for n in nets if n > 0), "trades": trades, "fees": fees}
        pullback_rows.append({"variant": label, **agg})
        L.append(
            f"| {label} | {agg['is']['sum']:+.2f} | {agg['is']['positive']}/28 | {agg['oos']['sum']:+.2f} | {agg['oos']['positive']}/28 | "
            f"{agg['full']['sum']:+.2f} | {agg['full']['positive']}/28 | {agg['full']['trades']} | {agg['full']['fees']:.2f} |"
        )
    report["pullback"] = pullback_rows

    # 5. Trendfolge mit echtem Funding
    L += [
        "",
        "## Trendfolge 40/20 auf 4h mit echtem Funding",
        "",
        "### Je Symbol eigene 50 USDT, Risiko 1 %",
        "",
        "| Funding | IS Summe | IS positiv | OOS Summe | OOS positiv | Jahr Summe | Jahr positiv | Funding Jahr |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    trend_rows = []
    for label, c in (("Pauschale 0,01 %/8h", Costs()), ("echt (Binance-Proxy)", costs)):
        agg = {}
        for section in ("is", "oos", "full"):
            nets, funding = [], 0.0
            for s in symbols:
                if section == "is":
                    res = run_trend(candles[s][: split[s]], specs[s], TREND, c, 50.0, LEVERAGE)
                elif section == "oos":
                    res = run_trend(candles[s], specs[s], TREND, c, 50.0, LEVERAGE, split[s])
                else:
                    res = run_trend(candles[s], specs[s], TREND, c, 50.0, LEVERAGE)
                nets.append(res["net"])
                funding += res["funding"]
            agg[section] = {"sum": sum(nets), "positive": sum(1 for n in nets if n > 0), "funding": funding}
        trend_rows.append({"funding": label, **agg})
        L.append(
            f"| {label} | {agg['is']['sum']:+.2f} | {agg['is']['positive']}/28 | {agg['oos']['sum']:+.2f} | {agg['oos']['positive']}/28 | "
            f"{agg['full']['sum']:+.2f} | {agg['full']['positive']}/28 | {agg['full']['funding']:+.2f} |"
        )
    report["trend_per_symbol"] = trend_rows

    L += [
        "",
        "### Portfolio mit gemeinsamem Kapital: Skalierung über das Konto",
        "",
        "Höchstens 5 Positionen, Signal-Rangfolge nach Ausbruchsstärke, Risiko 1 % je Trade, echtes Funding. Dieselbe Strategie, nur das Konto wächst. Prozent bezogen auf das Startkapital.",
        "",
        "| Universum | Kapital | IS | OOS | Jahr | Jahr % | max DD Jahr | Trades Jahr | zu klein | PF Jahr |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    scale_rows = []
    for universe_name, universe in (("28 Coins", symbols), ("10 liquide", LIQUID)):
        sub = {s: candles[s] for s in universe}
        for equity in (50.0, 200.0, 500.0, 1000.0, 3000.0, 10000.0):
            is_res = run_trend_portfolio({s: sub[s][: split[s]] for s in universe}, specs, TREND, costs, equity, LEVERAGE, 5, rank_signals=True)
            oos = run_trend_portfolio(sub, specs, TREND, costs, equity, LEVERAGE, 5, start_ts=split_ts, rank_signals=True)
            full = run_trend_portfolio(sub, specs, TREND, costs, equity, LEVERAGE, 5, rank_signals=True)
            scale_rows.append({"universe": universe_name, "equity": equity, "is": is_res["net"], "oos": oos["net"], "full": full["net"], "dd": full["max_drawdown_pct"], "trades": full["trades"], "zu_klein": full["exits"].get("zu_klein", 0), "pf": full["profit_factor"]})
            L.append(
                f"| {universe_name} | {equity:.0f} | {is_res['net']:+.2f} | {oos['net']:+.2f} | {full['net']:+.2f} | {100*full['net']/equity:+.1f} % | "
                f"{full['max_drawdown_pct']:.1f} % | {full['trades']} | {full['exits'].get('zu_klein', 0)} | {_pf(full['profit_factor'])} |"
            )
    report["trend_scale"] = scale_rows

    L += [
        "",
        "### Alle Signale nehmen: kein Platzlimit, gemeinsames Margin-Budget",
        "",
        "Trendfolge lebt von wenigen großen Gewinnern. Mit 5 Plätzen verfallen Signale, und genau die fehlen dann. Hier gibt es kein Platzlimit; die Grenze ist nur das Margin-Budget (50 % des Kapitals bei Hebel 2). Risiko je Trade variiert, weil bis zu 28 Positionen gleichzeitig offen sein können und Krypto stark korreliert.",
        "",
        "| Universum | Kapital | Risiko | IS | OOS | Jahr | Jahr % | max DD Jahr | Trades | zu klein | PF |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    all_rows = []
    for universe_name, universe in (("28 Coins", symbols), ("10 liquide", LIQUID)):
        sub = {s: candles[s] for s in universe}
        n = len(universe)
        for equity in (300.0, 1000.0, 3000.0):
            for risk in (0.0025, 0.005, 0.01):
                p = replace(TREND, risk_pct=risk)
                is_res = run_trend_portfolio({s: sub[s][: split[s]] for s in universe}, specs, p, costs, equity, LEVERAGE, n, shared_margin=True)
                oos = run_trend_portfolio(sub, specs, p, costs, equity, LEVERAGE, n, start_ts=split_ts, shared_margin=True)
                full = run_trend_portfolio(sub, specs, p, costs, equity, LEVERAGE, n, shared_margin=True)
                all_rows.append({"universe": universe_name, "equity": equity, "risk": risk, "is": is_res["net"], "oos": oos["net"], "full": full["net"], "dd": full["max_drawdown_pct"], "trades": full["trades"], "zu_klein": full["exits"].get("zu_klein", 0), "pf": full["profit_factor"]})
                L.append(
                    f"| {universe_name} | {equity:.0f} | {risk*100:.2f} % | {is_res['net']:+.2f} | {oos['net']:+.2f} | {full['net']:+.2f} | {100*full['net']/equity:+.1f} % | "
                    f"{full['max_drawdown_pct']:.1f} % | {full['trades']} | {full['exits'].get('zu_klein', 0)} | {_pf(full['profit_factor'])} |"
                )
    report["trend_all_signals"] = all_rows

    # 6. Quartale
    L += [
        "",
        "## Quartale, 1000 USDT gemeinsames Kapital, echtes Funding",
        "",
        "| Quartal | B&H Median | Trend 28 Coins | Trend 10 liquide | Momentum 28 T l/s | Carry 10 liquide (50 USDT) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    quarter_rows = []
    for q in range(4):
        a, b = quarter_ts[q], quarter_ts[q + 1] - 1
        cut = {s: [c for c in candles[s] if c.ts <= b] for s in symbols}
        bh = [100.0 * (cut[s][-1].close / next(c for c in cut[s] if c.ts >= a).close - 1.0) for s in symbols]
        t28 = run_trend_portfolio(cut, specs, TREND, costs, 1000.0, LEVERAGE, 5, start_ts=a, rank_signals=True)["net"]
        t10 = run_trend_portfolio({s: cut[s] for s in LIQUID}, specs, TREND, costs, 1000.0, LEVERAGE, 5, start_ts=a, rank_signals=True)["net"]
        mom = run_momentum(cut, specs, MomentumParams(), costs, 1000.0, LEVERAGE, start_ts=a)["net"]
        carry = run_carry(books, CarryParams(), 50.0, a, b, LIQUID)["net"]
        label = f"{_stamp(a)} – {_stamp(b)}"
        quarter_rows.append({"label": label, "bh": statistics.median(bh), "trend28": t28, "trend10": t10, "momentum": mom, "carry": carry})
        L.append(f"| {label} | {statistics.median(bh):+.0f} % | {t28:+.2f} | {t10:+.2f} | {mom:+.2f} | {carry:+.2f} |")
    report["quarters"] = quarter_rows
    L.append("")
    MD_PATH.write_text("\n".join(L), encoding="utf-8")
    JSON_PATH.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
