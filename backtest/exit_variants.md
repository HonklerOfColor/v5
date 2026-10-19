# Ausstiegs-Varianten: Hysterese und Notstopp

Erstellt 2026-10-18. Alle Varianten laufen auf denselben eingefrorenen Kerzen: 1h, 20.06.2026 bis 18.10.2026 (2865 Stunden), 50 USDT, Hebel 2, Maker 0,02 %, Taker 0,06 %, 2 bp Slippage, Funding-Abschlag 0,01 % / 8h. Universum: dieselben 60 Coins aus einem Screening, 58 mit genug Historie. Fenster und Coin-Liste sind gegenüber [universe_report.md](universe_report.md) (bis 16.10.) zwei Tage verschoben.

## Varianten

Vor dem Lauf festgelegt: Hysterese ADX +6 und ER +0,15, beim Halten nur ADX und ER (ohne Kompression und Kreuzungen). Notstopp bei 1 % jenseits der Range, innerhalb der Stunde. Die Varianten bilden ein 2×2-Raster. D ist eine Zerlegung, kein vorab festgelegter Kandidat.

| | Regime-Ausstieg | Notstopp in der Stunde |
| --- | --- | --- |
| A | wie Einstieg (alter Code) | nein |
| E | wie Einstieg | ja, 1 % — **neuer Default** |
| C | Hysterese 6 / 0,15, nur ADX+ER | nein |
| B | Hysterese 6 / 0,15, nur ADX+ER | ja, 1 % |
| D | Einstiegsschwellen, aber nur ADX+ER | ja, 1 % |

## Ohne Auswahl: alle 58 Coins, Default-Parameter, 120 Tage

Jeder Coin hat eigene 50 USDT. Das ist der Vergleich ohne Selektions-Bias.

| | Summe Netto | Median | positiv | Grids | Regime-Ausstiege | Breakouts | Fees |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | −15,88 | −0,167 | 25/58 | 1312 | 870 | 441 | 29,39 |
| E | −13,63 | −0,180 | 24/58 | 1320 | 839 | 480 | 29,40 |
| C | −3,88 | −0,380 | 25/58 | 900 | 260 | 638 | 29,32 |
| B | −13,06 | −0,244 | 22/58 | 915 | 241 | 672 | 29,12 |
| D | −9,78 | −0,109 | 27/58 | 1239 | 729 | 509 | 29,44 |

## BTC, ETH, BNB als Portfolio (ein Grid zur Zeit)

| | BTC | ETH | BNB | Portfolio | Ausstiege Portfolio |
| --- | ---: | ---: | ---: | ---: | --- |
| A | −0,09 | −0,35 | +0,43 | −0,37 | 55 Regime, 20 Breakout |
| E | −0,12 | −0,30 | +0,41 | −0,36 | 55 Regime, 17 Breakout, 3 Notstopp |
| C | −0,87 | +2,36 | −0,44 | −1,05 | 20 Regime, 25 Breakout |
| B | −0,85 | +1,23 | −0,66 | −0,93 | 20 Regime, 19 Breakout, 6 Notstopp |
| D | −0,10 | +0,51 | −0,16 | −0,95 | 50 Regime, 15 Breakout, 3 Notstopp |

## Ehrliches Universum-Portfolio (8 beste In-Sample-Coins, nur Out-of-Sample, Verlierer bleiben drin)

Jede Variante wählt ihre Coins selbst. Die Zeilen enthalten also verschiedene Coins.

| | Netto OOS | PF | Grids | Max. DD |
| --- | ---: | ---: | ---: | ---: |
| A | +2,03 | 1,96 | 22 | 3,0 % |
| E | −0,59 | 0,79 | 24 | 5,2 % |
| C | +0,71 | 1,27 | 12 | 5,2 % |
| B | +1,54 | 1,67 | 17 | 3,0 % |
| D | −0,09 | 0,88 | 14 | 3,8 % |

## Lesart

- **Hysterese ist nicht robust besser.** Sie tauscht Regime-Ausstiege gegen Breakouts: 870 → 260 Regime, 441 → 638 Breakouts. Ohne Notstopp steigt die Summe (A → C), aber der Median fällt von −0,17 auf −0,38. Mit Notstopp ist die Summe gleich (E −13,6, B −13,1), Median und Zahl positiver Coins werden schlechter. Auf BTC/ETH/BNB ist sie in beiden Fällen schlechter. Sie bleibt als Option (`ADX_EXIT_MARGIN`, `ER_EXIT_MARGIN`, `EXIT_TREND_ONLY`), der Default ist aus.
- **Der Notstopp ist eine Korrektur, keine Optimierung.** Vorher stoppte Live am Ticker schon bei 0,25 % jenseits der Range aus, dazu kam ein Börsen-Stop an derselben Stelle. Der Backtest sah nur den Stunden-Schluss. Er rechnete also mit Dochten, die zurückkommen und die Live nie überlebt hätte. Jetzt rechnen beide gleich: normaler Breakout am Stunden-Schluss, Notstopp und Börsen-Stop bei 1 %. Über alle Coins kostet das nichts (A −15,9, E −13,6). Das ehrliche Portfolio fällt dagegen von +2,03 auf −0,59. Dessen Plus hing an wenigen Grids, die erst nach einem Docht über 1 % zurückkamen.
- **Ohne Auswahl ist das Grid in diesem Fenster negativ.** In jeder Variante sind Summe und Median über 58 Coins negativ. Nur 22 bis 27 Coins sind positiv. Die Fees (rund 29 USDT) fressen den Roh-Edge.
- **Die Coin-Auswahl ist instabil.** Zwei Tage später im Fenster hat die alte Config-Liste kein In-Sample-Plus mehr: DOGE IS −0,55 / OOS −0,01, SUI IS −0,20 / OOS +1,40, SNDK IS −0,01 / OOS +0,38 (alles E). INTC und ANTHROPIC fallen nicht einmal mehr ins Screening. Die „empfohlene“ Liste wechselt je nach Variante fast komplett. `SYMBOLS` in `config.example.py` bleibt trotzdem unverändert: Eine Liste nach OOS-Ergebnissen umzubauen wäre genau der Bias, vor dem der Universum-Report warnt.

Reproduktion: Die Varianten liefen über ein Harness, das `universe_backtest.main()` und `backtest.main()` auf eingefrorene Kerzen und ein festes Screening umleitet. Dieselben Daten, nur Code bzw. Parameter verschieden. Die Default-Zahlen in [latest_report.json](latest_report.json) stammen aus Lauf E.
