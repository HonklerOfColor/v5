# Strategie

Grid nur dann, wenn der Markt seitwärts läuft. Jede Order, die das Grid aufmacht oder ein Los mit Gewinn schließt, ist Post-only. Der Notausstieg darf Taker sein, weil eine hängende Lage im Ausbruch teurer ist als die Taker-Fee.

## Warum nicht V2

Subaccount `at-HNKHNK`, 792 geschlossene Trades vom 05.07.2026 bis 20.09.2026, durchweg Isolated:

| | USDT |
| --- | ---: |
| Brutto-PnL | −31,00 |
| Fees | −32,89 |
| Funding | +0,78 |
| Netto | −63,11 |

739 Shorts, 53 Longs. Symbole vor allem ETH, BTC, SOL, etwas XRP. Die Fee je Round-Trip, geteilt durch Entry- plus Exit-Notional, lag im Median bei etwa 0,04 % **pro Seite** — zwischen Maker 0,02 % und Taker 0,06 %, näher am Taker. Bei rund 800 Round-Trips haben die Fees mehr gekostet als der Markt hergegeben hat.

Dieser Bot handelt deshalb selten, nur in einer erkannten Range, und kassiert auf dem normalen Weg die Maker-Fee. Der Mindestabstand zweier Levels ist das Dreifache der Maker-Round-Trip-Fee: 2 × 0,02 % × 3 = **0,12 %**. Ein voller Umlauf (Kauf und Verkauf als Maker) kostet 0,04 % und lässt bei genau 0,12 % Abstand rechnerisch 0,08 % vor Funding und vor dem Notausstieg übrig. Enger wird nicht gehandelt.

## Regime

Kein Grid, solange eine Bedingung fehlt. Geschlossene Kerzen, kein Blick in die Zukunft.

| Filter | Default | Bedeutung |
| --- | --- | --- |
| ADX(14) 1h | unter 22 | kein gerichteter 1h-Trend |
| ADX(14) 4h | unter 25 | der höhere Zeitrahmen ist nicht trendig |
| Efficiency Ratio, 24×1h | unter 0,35 | der Pfad ist verschlungen, nicht eine Gerade |
| Bollinger-Breite(20, 2) **oder** ATR(14)/Preis | unter 6 % bzw. unter 1,5 % | Volatilität ist komprimiert, eine der beiden reicht |
| Mittelkreuzungen im 48h-Fenster | mindestens 3 | beide Seiten der Range wurden gehandelt |

Eine glatte Sinuswelle kann den ADX hochziehen, obwohl sie optisch „seitwärts“ aussieht. Der Filter will Gehacker, nicht die erste Hälfte eines Schwungs. Im Backtest blockiert vor allem der ADX.

Ein laufendes Grid wird geschlossen, sobald ein Filter fehlt. Die meisten Ausstiege sind deshalb Regime-Ausstiege, und jeder zahlt Taker auf das Inventar. Eine Hysterese ist als Option eingebaut, Default aus: `ADX_EXIT_MARGIN`, `ER_EXIT_MARGIN`, `EXIT_TREND_ONLY`. Getestet mit +6 ADX, +0,15 ER und nur ADX/ER beim Halten. Sie tauschte Regime-Ausstiege gegen Breakouts und war nicht robust besser. Zahlen in [backtest/exit_variants.md](backtest/exit_variants.md).

## Grid

Die Grenzen sind das Tief und das Hoch der letzten 48 Stundenkerzen. Der letzte Schluss muss im mittleren 70 % dieser Spanne liegen (`EDGE_INSET` 0,15). Die Spanne selbst muss zwischen 0,8 % und 8 % des Mittelpreises liegen.

Daraus werden bis zu 6 Levels. Die Zahl sinkt, bis jedes Intervall mindestens 0,12 % weit ist. Unter 3 Levels wird abgelehnt.

Die Stückzahl je Level zielt auf 20 % des Kapitals als Notional, wird aber auf die Börsenmindestgröße angehoben und auf den Step abgerundet. Budget ist 50 % des Kapitals als Margin bei dem Symbol-Hebel. Zwei Orders (eine unter dem Preis, eine darüber) müssen in dieses Budget passen, sonst gibt es kein Grid.

Unter dem Preis liegen Post-only-Buys (Long öffnen), darüber Post-only-Sells (Short öffnen), höchstens 3 offene Lose je Seite inklusive schon liegender Einstiege. Ein Long-Fill bekommt einen Post-only-Sell eine Stufe höher (`tradeSide=close` im Hedge). Ein Short-Fill bekommt den Buy eine Stufe tiefer. Reduce-only im One-Way-Modus ist `reduceOnly=YES` und die Orderbuch-Seite, ohne `tradeSide`.

## Schutz

| Ereignis | Reaktion |
| --- | --- |
| Stunden-Schluss jenseits der Range plus 0,25 % | Alles stornieren, Lage schließen |
| Preis jenseits der Range plus 1 %, auch innerhalb der Stunde | dasselbe, sofort (Notstopp) |
| Regime nicht mehr seitwärts | dasselbe |
| Grid-Netto ≤ −6 % des Kapitals beim Start | dasselbe |
| UTC-Tagesverlust ≥ 5 % vom Tagesstart | schließen, an diesem Tag nichts Neues |
| Datei `KILL_SWITCH` oder Config | schließen, bis der Schalter weg ist |

Nach einem Ausstieg 6 Stunden Pause auf dem Symbol. Im Live-Betrieb wird der Close zuerst als Post-only versucht (20 Sekunden), der Rest geht als Market-IOC. Der Backtest bucht den Notausstieg sofort als Taker (0,06 %) plus 2 bp Slippage. Zusätzlich ein pauschales Funding von 0,01 % je 8 Stunden auf den Betrag der Nettoposition — das sind nicht die historischen Funding-Raten, sondern ein Abschlag.

Live und Backtest entscheiden den Breakout gleich: am Schluss der letzten geschlossenen Stundenkerze. Ein Docht durch den 0,25-%-Puffer stoppt nicht aus. Für den Fall, dass der Preis innerhalb der Stunde wegläuft, gibt es den Notstopp bei 1 % jenseits der Range (`BREAKOUT_HARD_PCT`). Live prüft ihn am Ticker alle 20 Sekunden. Der Backtest bucht ihn, sobald Hoch oder Tief der Kerze ihn erreicht, zum Stopp-Preis oder bei einer Lücke zum Open, plus Taker und Slippage.

Live versucht außerdem einen Börsen-Stop auf der ganzen Long- bzw. Short-Lage am Notstopp. Das ist ein Zusatz, kein Ersatz für einen laufenden Prozess.

## Parameter (Defaults)

Hebel 2, Deckel 3, Isolated, Hedge. Ein Grid zur Zeit. Paper-Kapital, wenn kein Kontostand lesbar ist: 50 USDT. Loop 20 Sekunden. Default-Symbole nach dem Universum-Backtest ohne BTC, ETH und BNB: DOGEUSDT, SUIUSDT, SNDKUSDT, INTCUSDT, ANTHROPICUSDT. Herleitung und die negativen Kontroll-Portfolios stehen in [backtest/universe_report.md](backtest/universe_report.md).

Die vollständige Liste steht in `config.example.py`. Fehlende Felder in einem eingeworfenen V2-`config.py` fallen auf diese Defaults zurück. Der Hebel wird gekappt, auch wenn dort 5 steht.

## Backtest

`python3 backtest.py --days 120 --equity 50` auf öffentlichen Bitget-1h-Kerzen, 20.06.2026 bis 18.10.2026, 2865 Stunden, jedes Symbol mit eigenen 50 USDT und dasselbe noch einmal als Portfolio mit einem Grid zur Zeit. Report: `backtest/latest_report.json`.

Gebühren: Maker 0,02 %, Taker 0,06 % nur auf Notausstiegen, Funding-Abschlag 0,01 % / 8h. Dieselbe Engine wie Paper und Live.

| | Ende | Netto | Realisiert | Fees (Maker/Taker) | Funding | Max. DD | Grids | Round-Trips | Ausstiege |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| BTCUSDT | 49,88 | −0,12 | +0,56 | 0,64 (0,34/0,30) | 0,04 | 1,53 % | 34 | 81 | 24 Regime, 9 Breakouts, 1 Notstopp |
| ETHUSDT | 49,70 | −0,30 | +0,22 | 0,44 (0,22/0,22) | 0,08 | 3,05 % | 24 | 18 | 20 Regime, 2 Breakouts, 2 Notstopps |
| BNBUSDT | 50,41 | +0,41 | +1,10 | 0,65 (0,35/0,31) | 0,04 | 1,40 % | 37 | 94 | 28 Regime, 8 Breakouts, 1 Notstopp |
| Portfolio | 49,64 | −0,36 | +1,04 | 1,32 (0,67/0,65) | 0,07 | 2,26 % | 75 | 143 | 55 Regime, 17 Breakouts, 3 Notstopps |

Der Lauf enthält den Notstopp innerhalb der Stunde (1 %), den Live schon immer hatte. Vor dem 18.10. war das Fenster 18.06.–16.10. ohne Notstopp im Backtest, Portfolio −0,55 USDT.

Alle 143 Portfolio-Round-Trips sind positiv. Das ist keine Trefferquote, sondern die Konstruktion: ein abgeschlossener Umlauf verkauft eine Stufe über dem Kauf (oder kauft eine Stufe unter dem Short). Der Verlust sitzt in den Notausstiegen. Im Portfolio ist das realisierte Handelsergebnis +1,04 USDT, die Fees sind 1,32 USDT. Die Kosten sind größer als der Roh-Edge. Ohne den Funding-Abschlag bleibt das Portfolio bei etwa −0,29 USDT.

BNB ist im Fenster das einzige positive Symbol (+0,41 USDT, rund +0,8 % in vier Monaten). Das ist eine Stichprobe, kein Grund, die anderen Symbole aus der Liste zu streichen. BTC ist nach Fees negativ, obwohl jeder Umlauf gewonnen hat: 0,64 USDT Fees bei 0,56 USDT realisiertem Preis-PnL.

ETH wird oft gar nicht erst aufgemacht. Mindestgröße 0,01 ETH. Am Ende des Fensters lag ETH bei etwa 2410 USDT, also rund 24,1 USDT Notional und 12,0 USDT Margin bei 2×. Zwei solche Orders brauchen ~24,1 USDT Margin, das Budget bei 50 USDT Kapital und 50 % Einsatz sind 25 USDT. Knapp, und in teureren Stunden abgelehnt (172 Stunden `unter_mindestgroesse`). Der Bot geht dann nicht auf eine kleinere Stückzahl herunter.

Der Filter ist eng. Von den Stunden scheitern die meisten am ADX. Gestartet wurde im Portfolio 75-mal.

Über alle 58 Alts des Universums, ohne Auswahl und mit Default-Parametern, ist die Summe in diesem Fenster −13,6 USDT bei 58 × 50 USDT. Nur 24 Coins sind positiv. Die Default-Symbole aus dem Universum-Report vom 16.10. halten zwei Tage später nicht mehr: DOGE ist in beiden Abschnitten negativ, INTC und ANTHROPIC fallen aus dem Screening. Details in [backtest/exit_variants.md](backtest/exit_variants.md).

### Was der Backtest nicht ist

- Fill, sobald der Docht das Limit berührt. Das ist für Post-only leicht optimistisch.
- Innerhalb einer Breakout-Kerze werden keine Take-Profits gutgeschrieben, wohl aber berührte Einstiege. Das ist absichtlich streng.
- Kein Orderbuch, keine Teilausführung, keine API-Fehler, keine Warteschlange.
- Notausstieg zum Schlusskurs (Breakout, Regime) bzw. zum Stopp-Preis oder Open (Notstopp) plus 2 bp, nicht zum echten Slippage-Pfad.
- Funding ist eine Pauschale, kein historischer Satz.
- Ein Fenster, drei große Symbole, 50 USDT. Kein Beweis für die nächsten vier Monate.
- Der Drawdown bleibt klein, weil die Stückzahl klein ist und der Stop greift. Klein heißt hier nicht „ohne Verlust“.

Gegen die V2-Historie ist das ein anderes Profil: wenige Grids statt hunderter Taker-Scalps, und ein Verlust in der Größenordnung von einem USDT statt rund 63 USDT. Es ist trotzdem kein nachgewiesener Vorteil nach Fees.

## Alternativen geprüft (18.10.2026)

Ein Jahr 1h-Kerzen (18.10.2025 bis 18.10.2026), 28 liquide Krypto-Perps, jedes Symbol mit eigenen 50 USDT, Hebel 2, dieselben Kosten wie oben. Out-of-Sample sind die letzten 120 Tage. Alle Kandidaten und Parameter standen vor dem Lauf fest. Code in `research/`, Tabellen in [backtest/strategy_comparison.md](backtest/strategy_comparison.md) und [backtest/trend_followup.md](backtest/trend_followup.md).

| Kandidat | In-Sample | Out-of-Sample | Jahr | positiv | Fees (Jahr) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Grid Default (dieser Bot) | −54,7 | −15,3 | −68,5 | 5/28 | 52,9 |
| Grid mit Abwicklung statt Taker-Ausstieg (48h) | −60,3 | −20,3 | −77,0 | 5/28 | 42,4 |
| Grid Abwicklung + Hysterese | −54,1 | −16,8 | −71,1 | 7/28 | 48,5 |
| Donchian 40/20 auf 4h, Stop 3 × ATR, long+short | +2,5 | +29,1 | +25,7 | 14/28 | 8,4 |
| Donchian 40/20 auf 4h, nur long | −8,4 | +50,8 | +36,8 | 18/28 | 4,6 |
| Donchian 20/10 auf 4h | −11,2 | +31,9 | +18,8 | 17/28 | 13,5 |
| Bollinger-Mean-Reversion 1h, Maker-Einstieg | −404 | −294 | −604 | 1/28 | 273 |

Summen in USDT über 28 × 50 USDT. Buy & Hold im Jahr: Median −39 %, In-Sample −54 %, Out-of-Sample +34 %.

Was daraus folgt:

- **Das Grid ist in jedem Quartal negativ**, auch in den beiden Seitwärts-Bärenquartalen, für die es gebaut ist. Realisiert über das Jahr −12 USDT, Fees 53 USDT. Die Abwicklung statt Taker-Ausstieg spart Taker-Fees, hält das Inventar aber länger in den Ausbruch hinein und ist unterm Strich schlechter. Das Leck ist nicht der Ausstieg, sondern die Konstruktion: 48h-Range, Ausstieg bei jedem Regime-Wackler, Gewinn je Umlauf im Bereich der Fees.
- **Mean-Reversion am Band auf 1h ist bei diesen Kosten tot.** 20.000 Trades, 271 USDT Fees.
- **Trendfolge auf 4h ist der einzige Kandidat mit gesunder Kostenstruktur**: 798 Trades im Jahr, Fees 8 USDT bei realisierten +37 USDT. Sie ist in allen vier Quartalen besser als das Grid, in den zwei Bärenquartalen aber auch negativ (−22, −19), und ihr Jahresplus kommt aus den letzten beiden Quartalen (+29, +63). Die Parameter-Nachbarschaft (30/15 bis 50/25, Stop 2,5 bis 3,5 × ATR) ist in-sample uneinheitlich. Das ist eine Regime-Rendite, kein nachgewiesener Vorteil.
- **Mit 50 USDT als ein Konto trägt auch die Trendfolge nicht.** Als Portfolio mit gemeinsamem Kapital und 3 bis 5 Plätzen liegt sie je nach Variante zwischen −11 und +13 USDT im Jahr, bei 9 bis 43 % Drawdown; das einzige zweistellige Plus (+13) stammt aus einer Variante, die vor dem lückenlosen Nachladen der Kerzen bei 0 lag. Die positiven Einzel-Summen entstehen durch 28 parallele Konten, also 1400 USDT Kapital und echte Streuung. Bei 50 USDT fallen viele Signale unter die Mindestorder von 5 USDT (bis zu 585 ausgelassene Signale im Jahr), und drei Plätze streuen nichts.
- Funding ist weiter eine Pauschale von 0,01 % je 8h auf die Nettoposition. Sie trifft die Trendfolge (immer eine Nettoposition, 9,0 USDT im Jahr) stärker als das Grid (gehedgt). Historische Funding-Sätze wären für beide Seiten einer Trendfolge im Mittel eher neutral.

Empfehlung: Kein Kandidat rechtfertigt Echtgeld. Wer den Bot weiterentwickelt, sollte ihn auf die 4h-Trendfolge umbauen (`research/trend.py`, `research/portfolio.py`), nicht das Grid weiter tunen, und erst mit deutlich mehr Kapital oder mit einem Demo-Konto über mehrere Monate prüfen.

### Zweite Runde: strukturelle Quellen, Momentum, Pullback, Kapital

Gleiche Daten, aber mit **echten Funding-Raten** (Bitget liefert nur 90 Tage, deshalb Binance als Jahres-Proxy; in den 90 gemeinsamen Tagen lag Bitget im Mittel bei 6,7 % p.a., Binance bei 4,0 %; über das ganze Jahr liegt der Binance-Mittelwert bei −0,5 % p.a., im Bärenmarkt war Funding oft negativ). Tabellen in [backtest/alternatives.md](backtest/alternatives.md), Code `research/alternatives_report.py`.

| Kandidat | Ergebnis |
| --- | --- |
| Cash-and-Carry (Spot long, Perp short), 50 USDT | Funding-Ertrag 0,5 bis 1,1 USDT im Jahr auf 25 USDT Perp-Notional. Jede Rotation kostet mehr, als der Wechsel bringt (Jahr −0,7 bis −4,7). Ein Coin ein Jahr halten: +0,4 bis +1,0 USDT. Kein Kursrisiko, aber 1 bis 2 % p.a., und es braucht ein Spot-Konto. |
| Querschnitts-Momentum (wöchentlich Top 3 long, Flop 3 short, 28 Coins) | Vorzeichen wechselt mit Lookback und Abschnitt (14 T: IS +11, OOS −4; 28 T: −5; 56 T: −4). Nur long: Drawdown 36 bis 75 %. Rauschen. |
| Pullback im Trend (4h, RSI(2) unter 10 über SMA 200) | −53 USDT über 28 Coins, 2/28 positiv. Nur long −14, 6/28. Tot. |
| Trendfolge mit echtem Funding, je Symbol 50 USDT | +31,4 statt +25,7: Shorts bekommen Funding. 16/28 positiv. |
| Trendfolge, ein Konto, 5 Plätze, Kapital 50 bis 10.000 USDT | **−13 bis −19 % im Jahr bei jeder Kontogröße** (10 liquide: −4 bis −14 %), Drawdown 30 bis 38 %. Mit Plätzen verfallen Signale, und genau die großen Gewinner fehlen. |
| Trendfolge, ein Konto, alle Signale, Risiko 0,25 % je Trade | 28 Coins: −2 bis +1 % im Jahr, Drawdown 25 bis 28 %. 10 liquide: +1,5 bis +3 %, Drawdown 15 bis 17 %. Profit Factor 0,98 bis 1,08. Bei 0,5 % Risiko schon negativ, weil das Margin-Budget bindet und Signale ausfallen. |

Quartale mit 1000 USDT: Die Trendfolge auf 28 Coins ist in drei von vier Quartalen negativ, auf 10 liquiden in zwei. Carry ist in jedem Quartal leicht negativ, sobald rotiert wird.

Fazit der zweiten Runde: Auch mit echten Funding-Raten, mehr Kapital und drei weiteren Strategiefamilien gibt es auf diesen Daten keinen Kandidaten, der In-Sample und Out-of-Sample zugleich trägt. Das Beste, was ehrlich dasteht, sind +1,5 bis +3 % im Jahr bei 15 bis 17 % Drawdown (Trendfolge auf 10 liquiden Coins, alle Signale, kleines Risiko, ab etwa 300 USDT) und ein nahezu risikofreies +1 bis 2 % aus Funding, wenn Spot dazukommt. Beides ist kein Grund für einen Bot mit 50 USDT.

### Dritte Runde: Mikrostruktur mit 1-Minuten-Kerzen (18.10.2026)

Drei Ineffizienzen, die nicht aus einer Kursprognose kommen, sondern aus der Mechanik des Marktes, auf 90 Tagen 1-Minuten-Kerzen (20.07. bis 18.10.2026) für sechs Krypto-Perps und die fünf Aktien-Perps TSLA, NVDA, MSTR, INTC, SNDK. Alle Schwellen standen vor dem Lauf fest. Code `research/wicks.py`, `research/weekend.py`, `research/funding_window.py`, Tabellen in [backtest/microstructure.md](backtest/microstructure.md).

| Ineffizienz | Messung | Nach Kosten |
| --- | --- | --- |
| Liquidations-Dochte (Minutentief > 3 × ATR(14, 1h) unter dem Vorschluss) | 58 Ereignisse in 11 Symbolen, also alle zwei Wochen je Symbol. In 75 % der Fälle ist die Hälfte des Dochts nach 15 Minuten zurückgeholt. | Maker-Kauf bei −2 × ATR, Ziel −0,5 × ATR, Stop −4 × ATR, 60 Minuten: 126 Trades, netto +0,8 USDT auf 50 USDT Notional, +1 ± 15 bp je Trade (t = 0,1), Fees 3,7 USDT. Short-Spiegel −2,9 USDT. Rauschen, und die Fills am Limit sind im Sturz optimistisch. |
| Aktien-Perps am Wochenende (Fr 20:00 → Mo 13:30 UTC gegen Mo 13:30 → 14:30 und → 20:00) | Korrelation +0,05 (erste Stunde) und 0,00 (Tag) über 55 Symbol-Wochen, gleiches Vorzeichen in 58 %. Die Wochenend-Bewegung des Perps sagt über die Kasse-Eröffnung nichts. | Taker um 13:25 gegen Wochenend-Bewegungen über 1,5 %: 24 Trades, netto −8,4 USDT (Ausstieg 14:30) bzw. −2,7 USDT (20:00). Das Spiegelbild wäre +4,6 USDT bei t = 0,45, also dieselben 24 Trades rückwärts gelesen. |
| Funding-Fenster (30 Minuten vor und nach 00:00, 08:00, 16:00 UTC) | 2962 Funding-Zeitpunkte: vorher +0,5 ± 0,8 bp, nachher +4,6 ± 0,9 bp. Dieselben Fenster um 4 Stunden versetzt, ohne Funding: −0,5 und +4,0 bp. Die Bewegung hat mit dem Funding nichts zu tun. | Fade (Short vor positivem Satz, Funding kassieren): −22 bp je Fenster nach 16 bp Taker-Round-Trip. Bounce (Long zum Funding): −10 bp. Nur bei Sätzen über 3 bp (n = 110) bleibt der Bounce bei +1,8 bp, bei ± 4,7 bp Standardfehler. |

Fazit der dritten Runde: Die Mechanik ist sichtbar (Dochte kehren zurück, der Kurs driftet nach den Fixings leicht aufwärts), aber in der Größe eines einzelnen Spreads. Keine der drei Quellen trägt mit 50 USDT einen Taker-Trade, und das Maker-Spiel in den Docht ist nach 126 Trades von Null nicht zu unterscheiden. Auf Bitget sind die Funding-Sätze im Sommer 2026 klein und die Aktien-Perps am Wochenende weitgehend still; das Umfeld, in dem solche Ineffizienzen Geld wert sind, war in diesen 90 Tagen nicht da.

### Dritte Runde: Pairs-Trading

Zehn Sektor-Paare, vorab festgelegt (BTC/ETH, ETH/SOL, OP/ARB, UNI/AAVE, DOGE/PEPE, NEAR/APT, ADA/DOT, LTC/ZEC, SUI/APT, LINK/INJ). Spread = log(A) − log(B) auf 4h, z über 30 Tage, Einstieg |z| ≥ 2, Ausstieg |z| ≤ 0,5, Stop |z| ≥ 4, Zeitstopp 15 Tage, je Bein 40 % von 50 USDT, Taker, echtes Funding. Tabellen in [backtest/pairs.md](backtest/pairs.md), Code `research/pairs.py`.

| | IS | OOS | Jahr | positiv |
| --- | ---: | ---: | ---: | ---: |
| Summe über 10 Paare | +2,5 | −30,2 | −26,7 | 3/10 |

Zwei Paare sind über das Jahr deutlich positiv (UNI/AAVE +14,5, SUI/APT +12,7), drei verlieren 10 bis 17 USDT, weil der Spread nicht zurückkommt (OP/ARB, NEAR/APT, LINK/INJ; Halbwertszeiten von 70 bis über 10.000 Tagen). Die Nachbarschaft aus 15/30/60 Tagen und z 1,5/2/2,5 ist in 26 von 27 Zellen negativ. Quartale: +14,6, +1,7, −10,9, −31,2. Im Bullenquartal laufen Paare auseinander und bleiben auseinander. Zwei Gewinner aus zehn im Nachhinein auszuwählen wäre genau der Fehler, vor dem der Universum-Report warnt.

## Betrieb

Paper ist der Default. Live ist in [README.md](README.md) und [TRADING_RULES.md](TRADING_RULES.md) beschrieben. Wer live geht, tut das mit dem Wissen, dass dieser Backtest nach Kosten negativ ist, und mit einem Konto, das die Mindestgrößen tragen kann.
