# Vorab-Registrierung bt3 (fixiert am 18.10.2026, 20:25 Uhr Wien, VOR dem ersten Lauf)

## Gemeinsam
- Daten: Binance-Vision-Spot-Tageskerzen BTCUSDT/ETHUSDT (verfügbar ab 17.08.2017), Schlusskurs 00:00 UTC.
- Hauptfenster: IS 01.01.2020–31.12.2023, OOS 01.01.2024–30.09.2026, Gesamt 2020–09/2026.
- Längere Robustheit: Vorperiode ab dem ersten Tag mit vollständigen Indikatoren (TF: 05.03.2018; DCA: 01.09.2018, wegen 365-Tage-MA) bis 31.12.2019, sowie Gesamt ab diesem Datum.
- Kosten: Bitget Spot 0,10 % Gebühr + 0,05 % Slippage je Trade. Cash (USDT) unverzinst.
- Mindestorder Bitget Spot: 1 USDT (BTC/ETH, Specs 18.10.2026).
- Signale nur aus Daten bis Schlusskurs t, Ausführung zum Schlusskurs t (Annahme: Order kurz nach 00:00 UTC; Kursdifferenz über Slippage abgedeckt) – wirksam ab Rendite t+1.

## Test 1 – Trendfilter BTC+ETH (Long/Cash)
- Portfolio: 50 % BTC-Sleeve, 50 % ETH-Sleeve; jedes Sleeve ist entweder investiert (Anteil = Signal-Exposure) oder USDT.
- Signal-Varianten (6): SMA50, SMA100, SMA200 (long wenn Close > SMA), EMA10/20 und EMA20/50 (long wenn kurz > lang; EMA10/20 ≈ Bitwise BITC), Ensemble = Mittel der Binärsignale Close > SMA(n), n ∈ {20, 50, 100, 150, 200} (Exposure 0, 0,2 … 1,0).
- Prüffrequenz (2): täglich, wöchentlich (Sonntagsschluss). → Gitter 12 Konfigurationen.
- Rebalancing: bei Signaländerung sofort, sonst nur wenn Ist- vom Zielgewicht um > 20 % (relativ) abweicht.
- **Primärvariante: Ensemble, täglich, 50/50 BTC/ETH.**
- Vergleich: BTC B&H, ETH B&H, 50/50 B&H (monatlich rebalanciert), A-Spot (bt2, Primärvariante).
- Statistik: Sharpe (√365), Deflated Sharpe (N=12), PBO (CSCV, 16 Blöcke), Walk-Forward jährlich expandierend (Auswahl nach Sharpe) 2022–2026, Block-Bootstrap 12 Monate (10.000 Pfade, Blocklänge 20). Kapital 100/500/1000 USDT mit Mindestorder.

## Test 2 – Smart-DCA BTC/ETH
- Sparrate R = 100 USDT/Monat (Sensitivität 50 USDT); wöchentlich: R·12/52 je Sonntag. Monatlich: 1. Kalendertag.
- Aufteilung 50/50 BTC/ETH (zusätzlich BTC-only und ETH-only als Robustheit).
- **Gleiche Gesamteinzahlung**: Jede Periode wird R eingezahlt. Plain-DCA kauft sofort R. Smart-DCA kauft m·R (m = Multiplikator), begrenzt durch verfügbares USDT; Rest bleibt als USDT-Reserve im Depot.
- Signal: Multiple M = Close / SMA(L) des jeweiligen Assets am Vortagesschluss.
- Multiplikator-Schemata:
  - moderat: M<0,8 → 2,0; 0,8–1,0 → 1,5; 1,0–1,5 → 1,0; 1,5–2,4 → 0,5; >2,4 → 0
  - linear: m = clip(2 − M, 0, 2)
  - aggressiv: M<1,0 → 3,0; 1,0–1,5 → 1,0; >1,5 → 0
- L ∈ {100, 200, 365} → Gitter 9 Konfigurationen.
- **Primärvariante: Mayer Multiple (L=200), moderat, monatlich, 50/50, 100 USDT.**
- Vergleich: Plain-DCA gleicher Einzahlung und Frequenz; Lump-Sum (Gesamtsumme aller Einzahlungen am Starttag investiert, 50/50).
- Kennzahlen: IRR (money-weighted, XIRR), Endvermögen je eingezahltem USDT, durchschnittlicher Einstandspreis BTC/ETH, max. Drawdown des Depotwerts, max. Drawdown des zeitgewichteten Anteilswerts, Ø Cash-Quote, Cash am Ende.
- Robustheit: rollierende Startmonate mit 36-Monats-Horizont (alle Starts 09/2018 …), Anteil der Fenster, in denen Smart > Plain (IRR); PBO via CSCV über die rollierenden Fenster (Metrik IRR-Vorsprung ggü. Plain); Walk-Forward: jährliche 12-Monats-Sparpläne, Schema nach bestem Ø-Vorsprung der Vorjahre; Monte-Carlo: Block-Bootstrap synthetischer BTC/ETH-Pfade (365 Tage Vorlauf + 365 Tage Sparplan, 5.000 Pfade).
- DSR ist für Sparpläne (Cashflow-Strategie ohne einzelne Renditereihe) nicht sinnvoll definiert; stattdessen werden PBO, Rollfenster und Bootstrap berichtet.
