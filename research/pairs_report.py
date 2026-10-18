#!/usr/bin/env python3
"""Pairs-Trading auf vorab festgelegten Sektor-Paaren. python3 -m research.pairs_report"""

from __future__ import annotations

import json
import statistics
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from research.costs import Costs
from research.data import load_candles, load_specs, split_index
from research.funding import load_binance_funding
from research.pairs import PairsParams, run_pair

MD_PATH = Path("backtest/pairs.md")
JSON_PATH = Path("backtest/pairs.json")
# Nach Sektor gewählt, nicht nach Ergebnis.
PAIRS = [
    ("BTCUSDT", "ETHUSDT", "die beiden Großen"),
    ("ETHUSDT", "SOLUSDT", "Smart-Contract-Plattformen"),
    ("OPUSDT", "ARBUSDT", "Ethereum-L2"),
    ("UNIUSDT", "AAVEUSDT", "DeFi"),
    ("DOGEUSDT", "PEPEUSDT", "Memes"),
    ("NEARUSDT", "APTUSDT", "Alt-L1"),
    ("ADAUSDT", "DOTUSDT", "Alt-L1, ältere Generation"),
    ("LTCUSDT", "ZECUSDT", "Payment / Privacy"),
    ("SUIUSDT", "APTUSDT", "Move-L1"),
    ("LINKUSDT", "INJUSDT", "Infrastruktur"),
]
BASE = PairsParams()


def _stamp(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def main() -> None:
    specs = load_specs()
    symbols = sorted({s for a, b, _ in PAIRS for s in (a, b)})
    candles = {s: load_candles(s) for s in symbols}
    costs = Costs(funding_books={s: load_binance_funding(s) for s in symbols})
    ref = candles["BTCUSDT"]
    split = split_index(ref, 120)
    split_ts = ref[split].ts
    quarter = len(ref) // 4
    quarter_ts = [ref[q * quarter].ts for q in range(4)] + [ref[-1].ts + 1]
    report: dict = {"generated_at": datetime.now(timezone.utc).isoformat(), "pairs": PAIRS, "base": BASE.__dict__}

    def run(a: str, b: str, p: PairsParams, section: str, equity: float = 50.0) -> dict:
        ca, cb = candles[a], candles[b]
        if section == "is":
            ca, cb = [c for c in ca if c.ts < split_ts], [c for c in cb if c.ts < split_ts]
            return run_pair(ca, cb, specs[a], specs[b], p, costs, equity)
        if section == "oos":
            return run_pair(ca, cb, specs[a], specs[b], p, costs, equity, start_ts=split_ts)
        return run_pair(ca, cb, specs[a], specs[b], p, costs, equity)

    L = [
        "# Pairs-Trading auf Sektor-Paaren",
        "",
        f"Erzeugt {report['generated_at'][:16]}Z. 4h-Schlüsse, Spread = log(A) − log(B), z über 30 Tage, Einstieg |z| ≥ 2, Ausstieg |z| ≤ 0,5, Stop |z| ≥ 4, Zeitstopp 15 Tage. "
        f"Je Bein 40 % des Kapitals (50 USDT), beide Beine Taker, echtes Funding je Bein. Out-of-Sample ab {_stamp(split_ts)}. Paare nach Sektor festgelegt, nicht nach Ergebnis.",
        "",
        "## Je Paar",
        "",
        "| Paar | Sektor | Halbwertszeit (Tage) | IS | OOS | Jahr | Trades Jahr | Gewinner | Ziel/Stop/Zeit | Fees | Funding | max DD |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |",
    ]
    rows = []
    for a, b, sector in PAIRS:
        r_is, r_oos, r_full = run(a, b, BASE, "is"), run(a, b, BASE, "oos"), run(a, b, BASE, "full")
        ex = r_full["exits"]
        hl = r_full["half_life_bars"]
        rows.append({"pair": f"{a}/{b}", "sector": sector, "half_life_days": None if hl is None else hl / 6, "is": r_is["net"], "oos": r_oos["net"], "full": r_full["net"], "trades": r_full["trades"], "wins": r_full["wins"], "exits": ex, "fees": r_full["fees"], "funding": r_full["funding"], "dd": r_full["max_drawdown_pct"]})
        L.append(
            f"| {a}/{b} | {sector} | {'–' if hl is None else f'{hl/6:.1f}'} | {r_is['net']:+.2f} | {r_oos['net']:+.2f} | {r_full['net']:+.2f} | {r_full['trades']} | {r_full['wins']} | "
            f"{ex.get('ziel',0)}/{ex.get('stop',0)}/{ex.get('zeit',0)} | {r_full['fees']:.2f} | {r_full['funding']:+.2f} | {r_full['max_drawdown_pct']:.1f} % |"
        )
    for section in ("is", "oos", "full"):
        nets = [r[section] for r in rows]
        L.append(f"| **Summe {section.upper()}** | | | " + ("| " * {"is": 0, "oos": 1, "full": 2}[section]) + f"**{sum(nets):+.2f}** ({sum(1 for n in nets if n > 0)}/{len(nets)} positiv) |" + " |" * (8 - {"is": 0, "oos": 1, "full": 2}[section]))
    report["pairs_result"] = rows

    L += ["", "## Nachbarschaft (Summe über 10 Paare)", "", "| Lookback | Einstieg z | IS | OOS | Jahr | positiv Jahr | Trades |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    neigh = []
    for look_days in (15, 30, 60):
        for entry in (1.5, 2.0, 2.5):
            p = replace(BASE, lookback_bars=look_days * 6, entry_z=entry)
            agg = {}
            for section in ("is", "oos", "full"):
                res = [run(a, b, p, section) for a, b, _ in PAIRS]
                agg[section] = {"sum": sum(r["net"] for r in res), "positive": sum(1 for r in res if r["net"] > 0), "trades": sum(r["trades"] for r in res)}
            neigh.append({"lookback_days": look_days, "entry_z": entry, **agg})
            L.append(f"| {look_days} T | {entry:.1f} | {agg['is']['sum']:+.2f} | {agg['oos']['sum']:+.2f} | {agg['full']['sum']:+.2f} | {agg['full']['positive']}/10 | {agg['full']['trades']} |")
    report["neighborhood"] = neigh

    L += ["", "## Quartale (Summe über 10 Paare, Basis-Parameter)", "", "| Quartal | Netto | positiv |", "| --- | ---: | ---: |"]
    quarters = []
    for q in range(4):
        a_ts, b_ts = quarter_ts[q], quarter_ts[q + 1] - 1
        nets = []
        for a, b, _ in PAIRS:
            ca = [c for c in candles[a] if c.ts <= b_ts]
            cb = [c for c in candles[b] if c.ts <= b_ts]
            nets.append(run_pair(ca, cb, specs[a], specs[b], BASE, costs, 50.0, start_ts=a_ts)["net"])
        quarters.append({"label": f"{_stamp(a_ts)} – {_stamp(b_ts)}", "net": sum(nets), "positive": sum(1 for n in nets if n > 0)})
        L.append(f"| {_stamp(a_ts)} – {_stamp(b_ts)} | {sum(nets):+.2f} | {sum(1 for n in nets if n > 0)}/10 |")
    report["quarters"] = quarters
    L.append("")
    MD_PATH.write_text("\n".join(L), encoding="utf-8")
    JSON_PATH.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
