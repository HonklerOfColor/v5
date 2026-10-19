# Vorab-Registrierung (fixiert am 18.10.2026, VOR Ansicht der Ergebnisse)

## Daten
- Binance Vision, alle jemals gelisteten USDT-Paare (Spot) bzw. USDⓈ-M-Perps inkl. delisteter (survivorship-frei), Tages-Klines + Funding.
- Backtest-Fenster 2020-01-01 – 2026-09-30. Signale nutzen nur Daten bis Schlusskurs t, Position ab t+1.
- **In-Sample (IS): 2020-01-01 – 2023-12-31. Out-of-Sample (OOS): 2024-01-01 – 2026-09-30.** Walk-Forward: jährlich expandierend, Auswahl nach IS-Sharpe, Handel im Folgejahr (2022–2026).
- Universum: am Monatsende Top-B nach Median-Quote-Volumen der letzten 30 Tage; Ausschluss von Stablecoins/Fiat, Gold-Token, Wrapped-Token, Index-Perps, Tokenized Stocks, Leveraged Tokens; mind. 60 Handelstage Historie.
- Delisting: Position wird zum letzten verfügbaren Schlusskurs geschlossen.

## Kosten (Bitget)
- Perp Taker 0,06 % + Slippage 0,05 % je Seite (Basisfall); Perp Maker 0,02 % ohne Slippage (optimistisch).
- Spot 0,10 % + Slippage 0,05 % je Seite.
- Funding: tatsächliche Binance-Funding-Sätze (Long zahlt bei positivem Funding).
- Mindestorder: Bitget-Specs vom 18.10.2026 (Perp min 5 USDT + Lot-Größe; Spot min 1–20 USDT); unbekannte/delistete Symbole: Perp 5 USDT, Spot 10 USDT.

## A – Trend-Ensemble (Zarattini et al. 2025 Regeln)
- Donchian-Breakout auf Schlusskursen, Trailing-Stop = Mittelband (nur aufwärts), Gewicht je Fenster min(VT/σ90, Cap); Cap 2,0 (Perp) / 1,0 (Spot); 20 %-Rebalance-Schwelle für reine Vol-Anpassungen; je Coin 1/B des Kapitals; monatliche Universumswahl.
- Konfigurationsgitter (18): Fenster {alle 9: 5…360 | kurz: 5,10,20,30 | lang: 60,90,150,250,360} × B {5,10,20} × VT {25 %, 50 %}.
- **Primärvariante: alle 9 Fenster, B=10, VT=25 %.**
- **Funding-Filter (Perp, fix):** Ist der Mittelwert der Funding-Sätze der letzten 7 Tage > 0,03 % je 8 h (≈ 33 % p.a.), wird das Ziel-Gewicht des Coins auf 0 gesetzt.

## B – Cross-sektionaler Funding-Carry (nach Vine 2026)
- Universum: Top-30 Perps nach 30-Tage-Median-Volumen (point-in-time), mind. 30 Tage Funding-Historie.
- Signal: Mittel der täglichen Funding-Summen über L Tage (um 1 Tag verzögert). Long unteres Quantil q, Short oberes Quantil q, gleichgewichtet, dollar-neutral, Brutto-Exposure 1,0.
- Gitter (36): L {3,7,14,30} × q {20 %, 33 %, 50 %} × Rebalance {3, 7, 14 Tage}.
- **Primärvariante: L=7, q=33 %, Rebalance 7 Tage.**
- **Abbruchkriterium: OOS-Sharpe (Primär bzw. Walk-Forward) < 0,3 ODER PBO > 0,5 → nicht weiter verfolgen.**

## C – Kombination
- 50/50-Kapitalaufteilung zwischen A-Primär (beste Venue gemäß Vorab-Kriterium Sharpe IS) und B-Primär, monatlich rebalanciert. Bewertung: Korrelation, Sharpe, MaxDD, Ergebnisse 2022 und 2025.

## Statistik
- Sharpe annualisiert mit √365, rf = 0.
- Deflated Sharpe (Bailey & López de Prado 2014) mit N = Gittergröße.
- PBO via CSCV (Bailey et al.), S = 16 Blöcke, alle 12.870 Kombinationen, auf dem Gesamtzeitraum.
- Monte-Carlo: stationärer Block-Bootstrap (mittlere Blocklänge 20 Tage), 10.000 Pfade à 365 Tage, gemeinsam mit BTC gezogen.
