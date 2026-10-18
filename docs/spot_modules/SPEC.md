# Bauauftrag: Zwei Spot-Module für den Unified Bot (HonklerOfColor/v5)

Status: Paper-Modus only. Kein Live, kein Merge/Deploy ohne Andreas' ausdrückliche Freigabe. Stufe-1-Regeln (eigener Branch + PR, kein Push auf main, keine Secrets, kein Force-Push).

## Kontext
- Unified Bot: v5 PR #1 (Branch cursor/import-unified-bot), handelt bisher nur USDT-M-Perps auf at-HNK (UID 9711026741).
- Beide Module laufen auf **Bitget SPOT** (nicht Perps): Perps sind laut Backtest wegen Funding und Mindestgrößen schlechter.
- Benötigt: Spot-Broker/Adapter (Bitget Spot API v2: Kerzen, Specs, Orders, Balances), Paper-Simulation für Spot, eigenes virtuelles Ledger je Modul, Kapitalaufteilung im Risk-Manager. Spot ist long-only, kein Hebel.
- Prüfen: Spot-Guthaben/Handel auf dem Subaccount at-HNK möglich? Sonst Konto-Frage an Andreas.

## Modul 1: `spot_trend_ensemble` (A-Spot, niedrigeres Risiko)
Regeln exakt wie PREREG_trend_ensemble.md, Primärvariante, NICHT nachoptimieren:
- Universum: am Monatsende Top-10 Coins nach Median-Quote-Volumen der letzten 30 Tage (Bitget-Spot, USDT-Paare), Ausschluss Stablecoins/Fiat/Gold/Wrapped/Leveraged/Tokenized Stocks, mind. 60 Tage Historie.
- Je Coin 1/10 des Modulkapitals. Je Coin 9 Donchian-Fenster (5,10,20,30,60,90,150,250,360 Tage) auf Tages-Schlusskursen: Einstieg bei Breakout über das Fenster-Hoch, Trailing-Stop = Mittelband (nur aufwärts nachziehen), Ausstieg bei Schluss unter Stop.
- Gewicht je Fenster = min(0,25 / σ90, 1,0) (σ90 = annualisierte 90-Tage-Vola), Coin-Gewicht = Mittel über die 9 Fenster. Kein Hebel (Cap 1,0).
- Rebalancing nur bei Signaländerung oder wenn Vol-Anpassung > 20 % relativ.
- Takt: täglich kurz nach 00:00 UTC auf der abgeschlossenen Tageskerze (laufende Kerze NICHT verwenden!).
- Delisting: zum letzten Kurs schließen.
- Backtest-Erwartung: OOS Sharpe 0,81, 6,2 % p.a., MaxDD −15 %; seit 03/2025 nur Sharpe 0,42. Realistisch 3–8 % p.a.
- Abbruch-/Alarmkriterien: Drawdown > 15 % ODER Paper vs. Backtest-Schattenrechnung > 3 Prozentpunkte Abweichung über 3 Monate.

## Modul 2: `spot_trendfilter_btceth` (höhere Rendite, höheres Risiko)
Regeln exakt wie PREREG_trendfilter_dca.md, Test 1 Primärvariante:
- 50 % BTC-Sleeve, 50 % ETH-Sleeve (BTCUSDT, ETHUSDT Spot).
- Exposure je Sleeve = Mittel der Binärsignale Close > SMA(n) für n ∈ {20,50,100,150,200} → 0; 0,2; …; 1,0. Rest in USDT.
- Täglich auf Tagesschluss 00:00 UTC (abgeschlossene Kerze), Order kurz danach.
- Rebalancing: bei Signaländerung sofort, sonst nur wenn Ist- vom Zielgewicht > 20 % relativ abweicht.
- Backtest-Erwartung: OOS 2024–09/2026 Sharpe 0,92, CAGR 28,5 %, MaxDD −29 %; Gesamt MaxDD −47 %; ~17 Umschichtungen/Jahr.
- Warnung: Bitwise-ETF BITC (ähnliche Regel) live seit 03/2023 nur +28 % vs. Backtest +194 % – Lücke ungeklärt. Paper-Ergebnisse genau gegen Schattenrechnung loggen.
- Abbruch-/Alarmkriterien: Drawdown > 50 %, Paper vs. Backtest > 5 Prozentpunkte über 3 Monate, > 25 Trades/Monat.

## Gemeinsam
- Kosten-Annahmen im Paper: Spot-Gebühr 0,10 % + 0,05 % Slippage je Seite. Mindestorder aus Bitget-Spot-Specs (code/bitget_spot.json als Referenz, live laden).
- Kapital: Paper-Startkapital konfigurierbar (Vorschlag je Modul 500 USDT; technisch ab 100 USDT möglich).
- Schattenrechnung: Modul rechnet täglich parallel die idealisierte Backtest-Equity mit, um Abweichungen zu messen.
- Status-Endpunkt: je Modul Equity, Positionen, Exposure, Trades, Drawdown, Abweichung zur Schattenrechnung, letzter Lauf (für Trader-Überwachung über dev.honkler.at/api/agent hinter Authelia).
- Tests: Unit-Tests für Signale (gegen Referenzwerte aus code/runA.py bzw. code/tf.py auf festen Testdaten), Rebalance-Schwelle, Mindestorder-Rundung, keine Nutzung der laufenden Kerze.
- Steuern: 27,5 % KESt nicht eingerechnet; Trades exportierbar halten (CSV) für Steuer.
- Laufzeit Paper: mindestens 6 Monate, danach Entscheidung durch Andreas.

## Referenzen in diesem Ordner
- PREREG_*.md: verbindliche Regeln
- backtest_*.md: vollständige Berichte; profitable_strategien.md: Recherche (60 Quellen)
- code/: Backtest-Code (lib.py, runA.py = Trend-Ensemble, tf.py = Trendfilter, capital.py = Mindestorder-Sim)
- charts/: Equity- und Drawdown-Kurven
