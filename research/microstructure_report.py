#!/usr/bin/env python3
"""Mikrostruktur-Report: drei strukturelle Ineffizienzen auf 1-Minuten-Kerzen, nach Kosten.

    python3 -m research.microstructure_report

Braucht data/research/1m/ (research.fetch_1m) und data/research/funding/
(research.funding, auch für die Aktien-Perps). Schreibt backtest/microstructure.md
und backtest/microstructure.json. Alle Schwellen stehen in den drei Modulen fest.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from research import funding_window, weekend, wicks
from research.costs import Costs
from research.micro import available_minute_symbols, coverage, load_minute_candles, stamp

MD_PATH = Path("backtest/microstructure.md")
JSON_PATH = Path("backtest/microstructure.json")
CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "SUIUSDT"]
STOCKS = list(weekend.STOCK_SYMBOLS)


def _f(x: float | None, digits: int = 1, sign: bool = False) -> str:
    if x is None:
        return "–"
    s = f"{x:+.{digits}f}" if sign else f"{x:.{digits}f}"
    return s.replace(".", ",").replace("-", "−")


def _pct(x: float | None) -> str:
    return "–" if x is None else _f(100 * x, 0) + " %"


def data_section(symbols: list[str]) -> tuple[list[str], dict]:
    lines = ["| Symbol | Kerzen | von | bis | Tage | fehlende Minuten |", "| --- | ---: | --- | --- | ---: | ---: |"]
    cov: dict[str, dict] = {}
    for symbol in symbols:
        c = coverage(load_minute_candles(symbol))
        cov[symbol] = c
        lines.append(f"| {symbol} | {c['rows']} | {stamp(c['first'])} | {stamp(c['last'])} | {_f(c['days'])} | {c['missing']} |")
    return lines, cov


def wick_section(result: dict) -> list[str]:
    lines = [
        "| Symbol | Ereignisse | je Tag | Tiefs: 50 % zurück in 15 min | in 60 min | Hochs: 15 min | 60 min | Long-Trades | Long netto | Fees | Short-Trades | Short netto |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for symbol, row in result["symbols"].items():
        ev, lo, sh = row["events"], row["long"], row["short"]
        lines.append(
            f"| {symbol} | {ev['events']} | {_f(ev['per_day'], 2)} | {_pct(ev['low']['recovered_15m'])} | {_pct(ev['low']['recovered_60m'])} "
            f"| {_pct(ev['high']['recovered_15m'])} | {_pct(ev['high']['recovered_60m'])} "
            f"| {lo['trades']} | {_f(lo['net'], 2, True)} | {_f(lo['fees'], 2)} | {sh['trades']} | {_f(sh['net'], 2, True)} |"
        )
    t = result["total"]
    for side, label in (("long", "Long (Kauf in den Docht)"), ("short", "Short (Verkauf in die Spitze)")):
        s = t[side]
        lines.append("")
        lines.append(
            f"**{label}, gesamt:** {s['trades']} Trades, netto {_f(s['net'], 2, True)} USDT, brutto {_f(s['gross'], 2, True)}, "
            f"Fees {_f(s['fees'], 2)} (Maker {_f(s['maker_fees'], 2)}, Taker {_f(s['taker_fees'], 2)}), Funding {_f(s['funding'], 2, True)}, "
            f"Ausstiege {s['exits']}, Treffer {s['wins']}/{s['trades']}, Mittel je Trade {_f(s['mean_bp'])} bp ± {_f(s['se_bp'])} bp (t = {_f(s['t'], 2)})."
        )
    return lines


def weekend_section(result: dict) -> list[str]:
    lines = [
        "| Symbol | Wochen | Korrelation WE → 1. Stunde | WE → Tag | gleiches Vorzeichen 1. Std. | Tag | ⌀ |WE| bp | ⌀ |1. Std.| bp | Wochen > 1,5 % |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for symbol, row in result["symbols"].items():
        s = row["summary"]
        lines.append(
            f"| {symbol} | {s['weeks']} | {_f(s['corr_h1'], 2, True)} | {_f(s['corr_day'], 2, True)} | {_pct(s['same_sign_h1'])} | {_pct(s['same_sign_day'])} "
            f"| {_f(s['mean_abs_weekend_bp'], 0)} | {_f(s['mean_abs_h1_bp'], 0)} | {s['over_threshold']} |"
        )
    s = result["total"]["summary"]
    lines.append(
        f"| **alle** | {s['weeks']} | {_f(s['corr_h1'], 2, True)} | {_f(s['corr_day'], 2, True)} | {_pct(s['same_sign_h1'])} | {_pct(s['same_sign_day'])} "
        f"| {_f(s['mean_abs_weekend_bp'], 0)} | {_f(s['mean_abs_h1_bp'], 0)} | {s['over_threshold']} |"
    )
    lines.append("")
    lines.append("| Simulation (Taker 13:25, nur |WE| > 1,5 %) | Trades | netto USDT | brutto | Fees | Funding | Treffer | Mittel bp | t |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    labels = {
        "fade_h1": "gegen die WE-Bewegung, Ausstieg 14:30",
        "fade_close": "gegen die WE-Bewegung, Ausstieg 20:00",
        "follow_h1": "mit der WE-Bewegung, Ausstieg 14:30 (Spiegel)",
        "follow_close": "mit der WE-Bewegung, Ausstieg 20:00 (Spiegel)",
    }
    for key, label in labels.items():
        p = result["total"][key]
        lines.append(
            f"| {label} | {p['trades']} | {_f(p['net'], 2, True)} | {_f(p['gross'], 2, True)} | {_f(p['fees'], 2)} | {_f(p['funding'], 2, True)} "
            f"| {p['wins']}/{p['trades']} | {_f(p['mean_bp'], 0, True)} ± {_f(p['se_bp'], 0)} | {_f(p['t'], 2)} |"
        )
    lines.append("")
    lines.append("Einzelwochen (Wochenend-Bewegung / erste Stunde / Tag, in %):")
    lines.append("")
    lines.append("| Montag | " + " | ".join(result["symbols"]) + " |")
    lines.append("| --- | " + " | ".join("---" for _ in result["symbols"]) + " |")
    mondays = sorted({w["monday"] for row in result["symbols"].values() for w in row["windows"]})
    for monday in mondays:
        cells = []
        for row in result["symbols"].values():
            match = [w for w in row["windows"] if w["monday"] == monday]
            if match:
                w = match[0]
                cells.append(f"{_f(100 * w['move_weekend'], 1, True)} / {_f(100 * w['move_h1'], 1, True)} / {_f(100 * w['move_day'], 1, True)}")
            else:
                cells.append("–")
        lines.append(f"| {monday} | " + " | ".join(cells) + " |")
    return lines


def funding_section(result: dict) -> list[str]:
    lines = [
        "| Gruppe | n | ⌀ Satz bp | vorher bp | nachher bp | Fade brutto bp | Fade netto | Bounce brutto bp | Bounce netto |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, s in result["total"].items():
        lines.append(
            f"| {key} | {s['n']} | {_f(s['rate_bp'], 2, True)} | {_f(s['before_bp'], 1, True)} ± {_f(s['before_se'], 1)} | {_f(s['after_bp'], 1, True)} ± {_f(s['after_se'], 1)} "
            f"| {_f(s['fade_gross_bp'], 1, True)} ± {_f(s['fade_se'], 1)} | {_f(s['fade_net_bp'], 1, True)} | {_f(s['bounce_gross_bp'], 1, True)} ± {_f(s['bounce_se'], 1)} | {_f(s['bounce_net_bp'], 1, True)} |"
        )
    c = result["control"]
    lines.append(
        f"| Kontrolle +{result['params']['control_offset_h']} h (kein Funding) | {c['n']} | – | {_f(c['before_bp'], 1, True)} ± {_f(c['before_se'], 1)} | {_f(c['after_bp'], 1, True)} ± {_f(c['after_se'], 1)} | – | – | – | – |"
    )
    lines.append("")
    lines.append("| Symbol | n | vorher bp | nachher bp | positiv: n | vorher | nachher | Fade netto | negativ: n | vorher | nachher |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for symbol, row in result["symbols"].items():
        a, p, n = row["summary"]["all"], row["summary"]["pos"], row["summary"]["neg"]
        lines.append(
            f"| {symbol} | {a['n']} | {_f(a['before_bp'], 1, True)} | {_f(a['after_bp'], 1, True)} | {p['n']} | {_f(p['before_bp'], 1, True)} | {_f(p['after_bp'], 1, True)} | {_f(p['fade_net_bp'], 1, True)} "
            f"| {n['n']} | {_f(n['before_bp'], 1, True)} | {_f(n['after_bp'], 1, True)} |"
        )
    return lines


def verdict_wicks(result: dict) -> str:
    t = result["total"]
    lo, sh = t["long"], t["short"]
    ev_total = t["events"]
    sym = result["symbols"]
    per_day = sum(v["events"]["per_day"] or 0 for v in sym.values()) / max(1, len(sym))
    rec15 = [v["events"]["low"]["recovered_15m"] for v in sym.values() if v["events"]["low"]["recovered_15m"] is not None]
    rec_txt = f"{_pct(sum(rec15) / len(rec15))}" if rec15 else "–"
    parts = [
        f"3-ATR-Dochte sind selten: {ev_total} Ereignisse in {len(sym)} Symbolen, im Mittel {_f(per_day, 2)} je Symbol und Tag. "
        f"Wo sie auftreten, holt der Kurs im Mittel über die Symbole in {rec_txt} der Fälle binnen 15 Minuten die Hälfte des Dochts zurück, das ist die bekannte Mechanik. "
    ]
    for side, label, s in (("long", "Der Maker-Fade long", lo), ("short", "Short", sh)):
        if s["trades"] == 0:
            parts.append(f"{label} kommt nicht zum Fill. ")
            continue
        noise = "innerhalb des Rauschens" if s["t"] is None or abs(s["t"]) < 2 else "außerhalb des Rauschens (|t| ≥ 2)"
        parts.append(
            f"{label} ({s['trades']} Trades) endet netto bei {_f(s['net'], 2, True)} USDT auf 50 USDT Notional, "
            f"{_f(s['mean_bp'], 0, True)} ± {_f(s['se_bp'], 0)} bp je Trade, {noise}; Fees {_f(s['fees'], 2)} USDT, "
            f"Ausstiege {s['exits']}. "
        )
    both_neg = lo["net"] <= 0 and sh["net"] <= 0
    conclusion = (
        "Nach Kosten bleibt nichts übrig, und die Stichprobe ist zu klein, als dass ein anderes Vorzeichen etwas beweisen würde."
        if both_neg
        else "Ein positives Vorzeichen liegt nur auf einer Seite und innerhalb des Standardfehlers; das ist kein Nachweis, nur kein Gegenbeweis."
    )
    return "".join(parts) + conclusion


def verdict_weekend(result: dict) -> str:
    s = result["total"]["summary"]
    fh, fc = result["total"]["fade_h1"], result["total"]["fade_close"]
    corr_txt = (
        f"Die Korrelation zwischen Wochenend-Bewegung und erster Handelsstunde liegt bei {_f(s['corr_h1'], 2, True)}, zum ganzen Montag bei {_f(s['corr_day'], 2, True)} "
        f"(n = {s['weeks']} Symbol-Wochen; gleiches Vorzeichen in {_pct(s['same_sign_h1'])} bzw. {_pct(s['same_sign_day'])} der Wochen). "
    )
    size_txt = f"Die Wochenend-Bewegung ist im Mittel {_f(s['mean_abs_weekend_bp'], 0)} bp groß, die erste Stunde {_f(s['mean_abs_h1_bp'], 0)} bp; {s['over_threshold']} Wochen liegen über der 1,5-%-Schwelle. "
    sim_txt = (
        f"Der Fade (gegen die Bewegung, Taker) macht mit Ausstieg 14:30 netto {_f(fh['net'], 2, True)} USDT aus {fh['trades']} Trades "
        f"({_f(fh['mean_bp'], 0, True)} ± {_f(fh['se_bp'], 0)} bp, t = {_f(fh['t'], 2)}), mit Ausstieg 20:00 {_f(fc['net'], 2, True)} USDT "
        f"({_f(fc['mean_bp'], 0, True)} ± {_f(fc['se_bp'], 0)} bp, t = {_f(fc['t'], 2)}); Fees {_f(fh['fees'], 2)} bzw. {_f(fc['fees'], 2)} USDT. "
    )
    strong = any(p["t"] is not None and abs(p["t"]) >= 2 for p in (fh, fc))
    weeks = max((row["summary"]["weeks"] for row in result["symbols"].values()), default=0)
    n_sym = len(result["symbols"])
    mirror = result["total"]["follow_h1"]
    conclusion = (
        f"Mit {weeks} Wochen und {n_sym} Symbolen trägt kein Vorzeichen; |t| bleibt unter 2, und die Wochen sind über die Symbole hinweg korreliert, also sind es weniger unabhängige Beobachtungen, als die Tabelle zeigt. "
        f"Das Spiegelbild (mit der Bewegung, Ausstieg 14:30) steht bei {_f(mirror['net'], 2, True)} USDT und t = {_f(mirror['t'], 2)}: dieselben {mirror['trades']} Trades rückwärts gelesen, kein Befund."
        if not strong
        else f"Ein |t| über 2 bei {weeks} Wochen und {n_sym} korrelierten Symbolen ist nach einem Sommer Daten kein Nachweis, sondern ein Grund, dieselbe Messung ohne Änderung nach weiteren drei Monaten zu wiederholen."
    )
    return corr_txt + size_txt + sim_txt + conclusion


def verdict_funding(result: dict) -> str:
    t = result["total"]
    a, p, n = t["all"], t["pos"], t["neg"]
    best = max((abs(s["fade_gross_bp"] or 0), key) for key, s in t.items() if s["n"] >= 20)
    txt = (
        f"Über {a['n']} Funding-Zeitpunkte liegt die Bewegung in den 30 Minuten davor bei {_f(a['before_bp'], 1, True)} ± {_f(a['before_se'], 1)} bp, danach bei {_f(a['after_bp'], 1, True)} ± {_f(a['after_se'], 1)} bp. "
        f"Bei positivem Satz (n = {p['n']}, ⌀ {_f(p['rate_bp'], 2)} bp) sind es {_f(p['before_bp'], 1, True)} bp vorher und {_f(p['after_bp'], 1, True)} bp nachher, "
        f"bei negativem (n = {n['n']}) {_f(n['before_bp'], 1, True)} und {_f(n['after_bp'], 1, True)} bp. "
        f"Die größte Fade-Bruttobewegung einer Gruppe mit mindestens 20 Fällen ist {_f(best[0], 1)} bp ({best[1]}), gegen 16 bp Taker-Round-Trip. "
    )
    any_net = [(key, s) for key, s in t.items() if s["n"] >= 20 and ((s["fade_net_bp"] or -1) > 0 or (s["bounce_net_bp"] or -1) > 0)]
    if any_net:
        txt += "Netto positiv nach 16 bp bleibt nur " + ", ".join(f"{k} (Fade {_f(s['fade_net_bp'], 1, True)}, Bounce {_f(s['bounce_net_bp'], 1, True)} bp)" for k, s in any_net) + "; das sind kleine Gruppen mit Standardfehlern in derselben Größenordnung. "
    else:
        txt += "Keine Gruppe mit mindestens 20 Fällen bleibt nach 16 bp netto positiv. "
    c = result["control"]
    txt += (
        f"Die Kontrolle um {result['params']['control_offset_h']} Stunden versetzt (kein Funding) zeigt vorher {_f(c['before_bp'], 1, True)} ± {_f(c['before_se'], 1)} und nachher {_f(c['after_bp'], 1, True)} ± {_f(c['after_se'], 1)} bp"
        + (": die Aufwärtsbewegung nach dem Funding ist also mehr als Tageszeit, aber mit wenigen Basispunkten weit unter den Kosten. " if c["after_bp"] is not None and t["all"]["after_bp"] is not None and t["all"]["after_bp"] - c["after_bp"] > 2 * ((t["all"]["after_se"] or 0) ** 2 + (c["after_se"] or 0) ** 2) ** 0.5 else ": die Bewegung um das Funding unterscheidet sich nicht vom Rest des Tages. ")
    )
    txt += "Die Funding-Sätze auf Bitget sind im Sommer 2026 klein (meist der Standardsatz 1 bp); was um den Zeitpunkt passiert, ist in der Größe eines einzelnen Spreads und trägt keinen Taker-Trade."
    return txt


def main() -> None:
    costs = Costs()
    symbols = [s for s in CRYPTO + STOCKS if s in available_minute_symbols()]
    data_lines, cov = data_section(symbols)
    wick = wicks.analyze(symbols, costs)
    wend = weekend.analyze([s for s in STOCKS if s in symbols], costs)
    fund = funding_window.analyze(symbols)
    now = datetime.now(tz=timezone.utc).strftime("%d.%m.%Y")
    gaps = [f"{s}: {c['missing']}" for s, c in cov.items() if c["missing"]]

    md = [
        f"# Mikrostruktur auf Bitget: drei Ineffizienzen mit 1-Minuten-Kerzen ({now})",
        "",
        "Drei Messungen, die nicht auf Kursprognose, sondern auf Marktmechanik zielen: Liquidations-Dochte, Aktien-Perps am Wochenende, Kursverlauf um den Funding-Zeitpunkt. "
        "Alle Schwellen und Regeln standen vor dem Lauf fest (siehe `research/wicks.py`, `research/weekend.py`, `research/funding_window.py`), keine Parametersuche. "
        "Kostenmodell wie überall im Projekt: Maker 0,02 %, Taker 0,06 % + 2 bp Slippage, echtes Bitget-Funding. Erzeugt mit `python3 -m research.microstructure_report`.",
        "",
        "## Datenbasis",
        "",
        "1-Minuten-Kerzen von Bitget (`research.fetch_1m`, Endpunkt history-candles, 200 Kerzen je Aufruf). Bitget liefert für 1m mindestens 180 Tage; geladen sind 90 Tage. "
        "Funding-Sätze von Bitget (90 Tage, drei je Tag). Fehlende Minuten sind Minuten ohne Kerze an der Börse.",
        "",
        *data_lines,
        "",
        "## 1. Liquidations-Dochte",
        "",
        "Ereignis: Minutentief mehr als 3 × ATR(14, 1h) unter dem Schluss der Vorminute (spiegelbildlich Hochs). Rückholung: Schluss der Ereigniskerze oder späteres Hoch über der Hälfte des Dochts innerhalb von 15 bzw. 60 Minuten. "
        "Simulation: Maker-Limit jede Minute bei Vorschluss ∓ 2 × ATR, Fill nur bei Tief/Hoch jenseits des Limits und Eröffnung diesseits; Ziel ∓ 0,5 × ATR (Maker), Stop ∓ 4 × ATR (Taker), Zeitstopp 60 Minuten (Taker); 50 USDT Notional, eine Position je Symbol.",
        "",
        *wick_section(wick),
        "",
        verdict_wicks(wick),
        "",
        "## 2. Aktien-Perps am Wochenende",
        "",
        "Für jede Woche: Bewegung des Perps Freitag 20:00 UTC → Montag 13:30 UTC (Kasse-Eröffnung) gegen Montag 13:30 → 14:30 (erste Handelsstunde) und 13:30 → 20:00 UTC. "
        f"Simulation: Montag 13:25 UTC als Taker gegen die bis dahin gelaufene Wochenend-Bewegung, nur wenn sie über 1,5 % liegt, Ausstieg 14:30 oder 20:00 als Taker, 50 USDT Notional, Funding 16:00 UTC eingerechnet. US-Feiertage: {', '.join(wend['params']['holidays'])} ausgelassen.",
        "",
        *weekend_section(wend),
        "",
        verdict_weekend(wend),
        "",
        "## 3. Funding-Fenster",
        "",
        "Kursbewegung in den 30 Minuten vor und nach jedem Bitget-Funding-Zeitpunkt (00:00, 08:00, 16:00 UTC), gruppiert nach Vorzeichen und Größe des Satzes (Klassen vorab: < 1 bp, genau 1 bp, 1 bis 3 bp, > 3 bp). "
        "Fade: 30 Minuten vorher gegen das Vorzeichen des Satzes (Short bei positivem Satz), Funding kassieren, 30 Minuten danach schließen. Bounce: zum Funding mit dem Vorzeichen des Satzes, nach 30 Minuten schließen. Netto = brutto minus 16 bp Taker-Round-Trip.",
        "",
        *funding_section(fund),
        "",
        verdict_funding(fund),
        "",
        "## Datenlücken und Grenzen",
        "",
        f"- Zeitraum {stamp(min(c['first'] for c in cov.values()))} bis {stamp(max(c['last'] for c in cov.values()))} UTC, also ein Sommer- und Frühherbstquartal 2026. Das ist eine Marktphase, kein Zyklus.",
        f"- Fehlende Minuten je Symbol: {', '.join(gaps) if gaps else 'keine'}.",
        "- Minutenkerzen zeigen nicht, in welcher Reihenfolge Tief und Hoch innerhalb der Minute lagen. Die Simulation nimmt den Stop vor dem Ziel und zählt das Ziel in der Einstiegskerze nur über den Schluss. Fills am Limit sind angenommen, wenn der Kurs darunter handelte; in einem Liquidations-Sturz steht man in der Warteschlange, der echte Fill ist seltener.",
        "- Funding-Sätze gibt es von Bitget nur 90 Tage; sie sind in diesem Zeitraum klein und eng um den Standardsatz.",
        f"- {len(wend['symbols'])} Aktien-Perps über {max((r['summary']['weeks'] for r in wend['symbols'].values()), default=0)} Wochen sind {wend['total']['summary']['weeks']} Symbol-Wochen, die untereinander korreliert sind (gleicher Markt, gleiche Nachrichten). Jede Aussage dazu hat die Trennschärfe von etwa einem Dutzend Beobachtungen.",
        "- Bitgets history-candles liefert mit `endTime` die Kerzen bis zu dieser Schlusszeit einschließlich; wer wie `bitget_client.get_history_candles` mit `endTime = ältester − 1` weiterblättert, verliert je Seite eine Kerze. `research.fetch_1m` blättert mit `endTime = ältester` und füllt Lücken nach.",
    ]
    MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    MD_PATH.write_text("\n".join(md) + "\n", encoding="utf-8")

    def slim_weekend(res: dict) -> dict:
        out = json.loads(json.dumps(res, default=str))
        for row in out["symbols"].values():
            for key in ("fade_h1", "fade_close", "follow_h1", "follow_close"):
                row[key].pop("trade_list", None)
        return out

    JSON_PATH.write_text(
        json.dumps({"generated": now, "coverage": cov, "wicks": wick, "weekend": slim_weekend(wend), "funding_window": fund}, indent=1, default=str),
        encoding="utf-8",
    )
    print(MD_PATH, JSON_PATH)


if __name__ == "__main__":
    main()
