# Mikrostruktur auf Bitget: drei Ineffizienzen mit 1-Minuten-Kerzen (18.10.2026)

Drei Messungen, die nicht auf Kursprognose, sondern auf Marktmechanik zielen: Liquidations-Dochte, Aktien-Perps am Wochenende, Kursverlauf um den Funding-Zeitpunkt. Alle Schwellen und Regeln standen vor dem Lauf fest (siehe `research/wicks.py`, `research/weekend.py`, `research/funding_window.py`), keine Parametersuche. Kostenmodell wie überall im Projekt: Maker 0,02 %, Taker 0,06 % + 2 bp Slippage, echtes Bitget-Funding. Erzeugt mit `python3 -m research.microstructure_report`.

## Datenbasis

1-Minuten-Kerzen von Bitget (`research.fetch_1m`, Endpunkt history-candles, 200 Kerzen je Aufruf). Bitget liefert für 1m mindestens 180 Tage; geladen sind 90 Tage. Funding-Sätze von Bitget (90 Tage, drei je Tag). Fehlende Minuten sind Minuten ohne Kerze an der Börse.

| Symbol | Kerzen | von | bis | Tage | fehlende Minuten |
| --- | ---: | --- | --- | ---: | ---: |
| BTCUSDT | 129650 | 2026-07-20 15:10 | 2026-10-18 15:59 | 90,0 | 0 |
| ETHUSDT | 129650 | 2026-07-20 15:10 | 2026-10-18 15:59 | 90,0 | 0 |
| SOLUSDT | 129650 | 2026-07-20 15:10 | 2026-10-18 15:59 | 90,0 | 0 |
| XRPUSDT | 129600 | 2026-07-20 16:00 | 2026-10-18 15:59 | 90,0 | 0 |
| DOGEUSDT | 129600 | 2026-07-20 16:00 | 2026-10-18 15:59 | 90,0 | 0 |
| SUIUSDT | 129600 | 2026-07-20 16:00 | 2026-10-18 15:59 | 90,0 | 0 |
| TSLAUSDT | 129600 | 2026-07-20 16:00 | 2026-10-18 15:59 | 90,0 | 0 |
| NVDAUSDT | 129600 | 2026-07-20 16:00 | 2026-10-18 15:59 | 90,0 | 0 |
| MSTRUSDT | 129600 | 2026-07-20 16:00 | 2026-10-18 15:59 | 90,0 | 0 |
| INTCUSDT | 129600 | 2026-07-20 16:00 | 2026-10-18 15:59 | 90,0 | 0 |
| SNDKUSDT | 129600 | 2026-07-20 16:00 | 2026-10-18 15:59 | 90,0 | 0 |

## 1. Liquidations-Dochte

Ereignis: Minutentief mehr als 3 × ATR(14, 1h) unter dem Schluss der Vorminute (spiegelbildlich Hochs). Rückholung: Schluss der Ereigniskerze oder späteres Hoch über der Hälfte des Dochts innerhalb von 15 bzw. 60 Minuten. Simulation: Maker-Limit jede Minute bei Vorschluss ∓ 2 × ATR, Fill nur bei Tief/Hoch jenseits des Limits und Eröffnung diesseits; Ziel ∓ 0,5 × ATR (Maker), Stop ∓ 4 × ATR (Taker), Zeitstopp 60 Minuten (Taker); 50 USDT Notional, eine Position je Symbol.

| Symbol | Ereignisse | je Tag | Tiefs: 50 % zurück in 15 min | in 60 min | Hochs: 15 min | 60 min | Long-Trades | Long netto | Fees | Short-Trades | Short netto |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BTCUSDT | 4 | 0,04 | 50 % | 50 % | 100 % | 100 % | 6 | −0,61 | 0,18 | 3 | −0,90 |
| ETHUSDT | 3 | 0,03 | 50 % | 50 % | 100 % | 100 % | 10 | +1,31 | 0,28 | 6 | −1,67 |
| SOLUSDT | 3 | 0,03 | 67 % | 67 % | – | – | 5 | −2,50 | 0,18 | 1 | +0,52 |
| XRPUSDT | 2 | 0,02 | 100 % | 100 % | – | – | 10 | +2,20 | 0,26 | 2 | −0,20 |
| DOGEUSDT | 11 | 0,12 | 89 % | 89 % | 100 % | 100 % | 19 | +2,28 | 0,52 | 4 | +3,32 |
| SUIUSDT | 5 | 0,06 | 100 % | 100 % | 100 % | 100 % | 6 | −3,74 | 0,22 | 3 | −0,39 |
| TSLAUSDT | 14 | 0,16 | 75 % | 75 % | 100 % | 100 % | 31 | +0,71 | 0,86 | 27 | −4,13 |
| NVDAUSDT | 3 | 0,03 | 100 % | 100 % | 50 % | 50 % | 11 | −1,68 | 0,36 | 11 | −1,59 |
| MSTRUSDT | 1 | 0,01 | – | – | 100 % | 100 % | 6 | −0,20 | 0,18 | 2 | −0,00 |
| INTCUSDT | 5 | 0,06 | 67 % | 67 % | 100 % | 100 % | 11 | +1,27 | 0,34 | 10 | −0,07 |
| SNDKUSDT | 7 | 0,08 | 50 % | 50 % | 100 % | 100 % | 11 | +1,81 | 0,32 | 10 | +2,24 |

**Long (Kauf in den Docht), gesamt:** 126 Trades, netto +0,83 USDT, brutto +4,55, Fees 3,69 (Maker 1,94, Taker 1,75), Funding +0,03, Ausstiege {'ziel': 67, 'stop': 42, 'zeit': 17}, Treffer 73/126, Mittel je Trade 1,3 bp ± 15,5 bp (t = 0,09).

**Short (Verkauf in die Spitze), gesamt:** 79 Trades, netto −2,87 USDT, brutto −0,41, Fees 2,47 (Maker 1,14, Taker 1,33), Funding −0,00, Ausstiege {'ziel': 35, 'stop': 35, 'zeit': 9}, Treffer 40/79, Mittel je Trade −7,3 bp ± 13,5 bp (t = −0,54).

3-ATR-Dochte sind selten: 58 Ereignisse in 11 Symbolen, im Mittel 0,06 je Symbol und Tag. Wo sie auftreten, holt der Kurs im Mittel über die Symbole in 75 % der Fälle binnen 15 Minuten die Hälfte des Dochts zurück, das ist die bekannte Mechanik. Der Maker-Fade long (126 Trades) endet netto bei +0,83 USDT auf 50 USDT Notional, +1 ± 15 bp je Trade, innerhalb des Rauschens; Fees 3,69 USDT, Ausstiege {'ziel': 67, 'stop': 42, 'zeit': 17}. Short (79 Trades) endet netto bei −2,87 USDT auf 50 USDT Notional, −7 ± 14 bp je Trade, innerhalb des Rauschens; Fees 2,47 USDT, Ausstiege {'ziel': 35, 'stop': 35, 'zeit': 9}. Ein positives Vorzeichen liegt nur auf einer Seite und innerhalb des Standardfehlers; das ist kein Nachweis, nur kein Gegenbeweis.

## 2. Aktien-Perps am Wochenende

Für jede Woche: Bewegung des Perps Freitag 20:00 UTC → Montag 13:30 UTC (Kasse-Eröffnung) gegen Montag 13:30 → 14:30 (erste Handelsstunde) und 13:30 → 20:00 UTC. Simulation: Montag 13:25 UTC als Taker gegen die bis dahin gelaufene Wochenend-Bewegung, nur wenn sie über 1,5 % liegt, Ausstieg 14:30 oder 20:00 als Taker, 50 USDT Notional, Funding 16:00 UTC eingerechnet. US-Feiertage: 2026-09-07 ausgelassen.

| Symbol | Wochen | Korrelation WE → 1. Stunde | WE → Tag | gleiches Vorzeichen 1. Std. | Tag | ⌀ |WE| bp | ⌀ |1. Std.| bp | Wochen > 1,5 % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TSLAUSDT | 11 | +0,24 | +0,17 | 64 % | 64 % | 62 | 172 | 2 |
| NVDAUSDT | 11 | −0,16 | −0,20 | 73 % | 55 % | 94 | 148 | 2 |
| MSTRUSDT | 11 | −0,12 | +0,14 | 55 % | 73 % | 176 | 186 | 4 |
| INTCUSDT | 11 | +0,24 | +0,34 | 55 % | 45 % | 276 | 188 | 7 |
| SNDKUSDT | 11 | −0,15 | −0,26 | 45 % | 45 % | 285 | 408 | 8 |
| **alle** | 55 | +0,05 | +0,00 | 58 % | 56 % | 178 | 221 | 23 |

| Simulation (Taker 13:25, nur |WE| > 1,5 %) | Trades | netto USDT | brutto | Fees | Funding | Treffer | Mittel bp | t |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gegen die WE-Bewegung, Ausstieg 14:30 | 24 | −8,39 | −6,96 | 1,44 | +0,00 | 7/24 | −70 ± 84 | −0,83 |
| gegen die WE-Bewegung, Ausstieg 20:00 | 24 | −2,73 | −1,18 | 1,44 | +0,12 | 8/24 | −23 ± 90 | −0,25 |
| mit der WE-Bewegung, Ausstieg 14:30 (Spiegel) | 24 | +4,56 | +6,00 | 1,44 | +0,00 | 15/24 | +38 ± 84 | 0,45 |
| mit der WE-Bewegung, Ausstieg 20:00 (Spiegel) | 24 | −1,11 | +0,21 | 1,44 | −0,12 | 14/24 | −9 ± 90 | −0,10 |

Einzelwochen (Wochenend-Bewegung / erste Stunde / Tag, in %):

| Montag | TSLAUSDT | NVDAUSDT | MSTRUSDT | INTCUSDT | SNDKUSDT |
| --- | --- | --- | --- | --- | --- |
| 2026-07-27 | −0,0 / −1,9 / −1,3 | +0,6 / −4,4 / −5,5 | +3,2 / +2,5 / +4,3 | +0,2 / −4,3 / −0,8 | +1,8 / −12,4 / −12,5 |
| 2026-08-03 | −0,1 / +2,5 / +3,5 | −1,4 / +3,8 / +4,5 | −1,4 / +3,4 / +3,0 | −2,2 / +1,4 / +3,0 | −4,5 / +7,7 / +10,9 |
| 2026-08-10 | −0,5 / +1,5 / +1,2 | −0,1 / −1,3 / −2,6 | −0,4 / −0,1 / −2,2 | −3,3 / −0,9 / −0,8 | −0,6 / +3,2 / +2,7 |
| 2026-08-17 | −0,5 / −0,3 / −0,4 | +0,4 / +0,3 / −0,4 | +0,3 / +2,8 / +4,6 | +1,3 / +0,1 / −0,4 | +3,7 / +4,4 / +5,0 |
| 2026-08-24 | −0,3 / −2,0 / −3,5 | +0,4 / −2,9 / −3,3 | +2,1 / +3,3 / +0,7 | −1,4 / −3,3 / −1,8 | −6,4 / −3,8 / −0,1 |
| 2026-08-31 | −0,3 / +4,6 / +5,9 | +0,6 / +0,5 / +0,8 | +1,1 / −1,5 / +3,3 | +0,5 / −0,1 / −0,5 | +0,2 / +1,8 / +5,3 |
| 2026-09-14 | −1,5 / −0,4 / −0,2 | −3,2 / −0,4 / −0,2 | −0,1 / +3,2 / +4,6 | −6,9 / +1,2 / +1,4 | −6,8 / +2,2 / +1,8 |
| 2026-09-21 | +2,1 / +1,4 / +0,9 | +0,5 / +0,3 / +1,9 | +7,1 / +0,8 / +2,3 | +7,3 / +3,8 / +4,5 | +2,0 / −2,4 / −3,3 |
| 2026-09-28 | −1,0 / −1,9 / −3,0 | +2,2 / +0,6 / −0,4 | −0,4 / −0,8 / −0,5 | −1,8 / −2,8 / −3,9 | −2,4 / −2,6 / −1,2 |
| 2026-10-05 | −0,4 / +1,9 / +2,6 | +0,9 / +0,4 / +1,3 | +2,9 / −0,3 / −0,2 | −3,3 / +1,5 / +0,8 | +0,3 / −0,2 / −1,2 |
| 2026-10-12 | −0,0 / −0,5 / −1,1 | −0,3 / −1,4 / −1,0 | −0,4 / +1,6 / −0,6 | −2,1 / −1,2 / −1,2 | −2,7 / −4,3 / −3,3 |

Die Korrelation zwischen Wochenend-Bewegung und erster Handelsstunde liegt bei +0,05, zum ganzen Montag bei +0,00 (n = 55 Symbol-Wochen; gleiches Vorzeichen in 58 % bzw. 56 % der Wochen). Die Wochenend-Bewegung ist im Mittel 178 bp groß, die erste Stunde 221 bp; 23 Wochen liegen über der 1,5-%-Schwelle. Der Fade (gegen die Bewegung, Taker) macht mit Ausstieg 14:30 netto −8,39 USDT aus 24 Trades (−70 ± 84 bp, t = −0,83), mit Ausstieg 20:00 −2,73 USDT (−23 ± 90 bp, t = −0,25); Fees 1,44 bzw. 1,44 USDT. Mit 11 Wochen und 5 Symbolen trägt kein Vorzeichen; |t| bleibt unter 2, und die Wochen sind über die Symbole hinweg korreliert, also sind es weniger unabhängige Beobachtungen, als die Tabelle zeigt. Das Spiegelbild (mit der Bewegung, Ausstieg 14:30) steht bei +4,56 USDT und t = 0,45: dieselben 24 Trades rückwärts gelesen, kein Befund.

## 3. Funding-Fenster

Kursbewegung in den 30 Minuten vor und nach jedem Bitget-Funding-Zeitpunkt (00:00, 08:00, 16:00 UTC), gruppiert nach Vorzeichen und Größe des Satzes (Klassen vorab: < 1 bp, genau 1 bp, 1 bis 3 bp, > 3 bp). Fade: 30 Minuten vorher gegen das Vorzeichen des Satzes (Short bei positivem Satz), Funding kassieren, 30 Minuten danach schließen. Bounce: zum Funding mit dem Vorzeichen des Satzes, nach 30 Minuten schließen. Netto = brutto minus 16 bp Taker-Round-Trip.

| Gruppe | n | ⌀ Satz bp | vorher bp | nachher bp | Fade brutto bp | Fade netto | Bounce brutto bp | Bounce netto |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 2962 | +0,61 | +0,5 ± 0,8 | +4,6 ± 0,9 | −6,2 ± 1,5 | −22,2 | +5,9 ± 1,1 | −10,1 |
| pos | 1808 | +1,12 | +0,7 ± 1,1 | +6,7 ± 1,1 | −6,2 ± 1,6 | −22,2 | +6,7 ± 1,1 | −9,3 |
| pos/<1bp | 846 | +0,50 | −0,9 ± 1,4 | +2,6 ± 1,2 | −1,2 ± 1,8 | −17,2 | +2,6 ± 1,2 | −13,4 |
| pos/=1bp | 665 | +1,00 | +1,2 ± 1,9 | +10,8 ± 2,4 | −11,0 ± 3,1 | −27,0 | +10,8 ± 2,4 | −5,2 |
| pos/1-3bp | 187 | +1,96 | −1,7 ± 3,9 | +4,3 ± 3,5 | −0,6 ± 5,5 | −16,6 | +4,3 ± 3,5 | −11,7 |
| pos/>3bp | 110 | +5,26 | +13,6 ± 4,7 | +17,8 ± 4,7 | −26,1 ± 6,9 | −42,1 | +17,8 ± 4,7 | +1,8 |
| neg | 239 | −0,98 | −6,9 ± 2,7 | −0,1 ± 3,4 | −6,0 ± 4,2 | −22,0 | +0,1 ± 3,4 | −15,9 |
| neg/<1bp | 183 | −0,30 | −7,9 ± 3,0 | +0,1 ± 3,6 | −7,4 ± 4,6 | −23,4 | −0,1 ± 3,6 | −16,1 |
| neg/=1bp | 1 | −1,00 | +13,2 ± – | −14,1 ± – | +0,1 ± – | −15,9 | +14,1 ± – | −1,9 |
| neg/1-3bp | 32 | −1,55 | −4,5 ± 6,2 | −0,7 ± 11,9 | −3,7 ± 13,4 | −19,7 | +0,7 ± 11,9 | −15,3 |
| neg/>3bp | 23 | −5,57 | −3,4 ± 11,3 | −0,6 ± 12,4 | +1,5 ± 16,9 | −14,5 | +0,6 ± 12,4 | −15,4 |
| null | 915 | +0,00 | +2,1 ± 1,0 | +1,6 ± 1,7 | – ± – | – | – ± – | – |
| null/<1bp | 915 | +0,00 | +2,1 ± 1,0 | +1,6 ± 1,7 | – ± – | – | – ± – | – |
| Kontrolle +4 h (kein Funding) | 2970 | – | −0,5 ± 0,8 | +4,0 ± 0,8 | – | – | – | – |

| Symbol | n | vorher bp | nachher bp | positiv: n | vorher | nachher | Fade netto | negativ: n | vorher | nachher |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BTCUSDT | 270 | −1,0 | +3,8 | 241 | −0,8 | +3,5 | −18,0 | 29 | −2,0 | +7,0 |
| ETHUSDT | 270 | −0,5 | +5,0 | 245 | +0,0 | +6,0 | −21,3 | 25 | −5,7 | −4,8 |
| SOLUSDT | 270 | −0,6 | +4,1 | 210 | +2,0 | +3,9 | −21,2 | 60 | −9,7 | +5,0 |
| XRPUSDT | 269 | −2,7 | +3,2 | 248 | −2,5 | +3,8 | −16,6 | 21 | −5,2 | −4,5 |
| DOGEUSDT | 269 | +0,0 | +6,9 | 255 | +0,2 | +7,2 | −22,6 | 14 | −3,7 | +1,4 |
| SUIUSDT | 269 | +1,5 | +13,8 | 227 | +2,4 | +14,9 | −32,4 | 42 | −3,0 | +7,9 |
| TSLAUSDT | 269 | +2,4 | −1,9 | 63 | +2,3 | +3,6 | −19,6 | 0 | – | – |
| NVDAUSDT | 269 | +1,3 | +2,2 | 58 | +0,1 | +3,4 | −17,7 | 1 | −0,9 | +10,7 |
| MSTRUSDT | 269 | −1,6 | +7,2 | 88 | +2,4 | +6,1 | −21,8 | 10 | −26,6 | −15,9 |
| INTCUSDT | 269 | +1,0 | +1,4 | 99 | +3,3 | +10,0 | −26,6 | 9 | −23,2 | −16,3 |
| SNDKUSDT | 269 | +5,6 | +4,6 | 74 | +4,2 | +12,1 | −29,3 | 28 | −3,5 | −13,5 |

Über 2962 Funding-Zeitpunkte liegt die Bewegung in den 30 Minuten davor bei +0,5 ± 0,8 bp, danach bei +4,6 ± 0,9 bp. Bei positivem Satz (n = 1808, ⌀ 1,12 bp) sind es +0,7 bp vorher und +6,7 bp nachher, bei negativem (n = 239) −6,9 und −0,1 bp. Die größte Fade-Bruttobewegung einer Gruppe mit mindestens 20 Fällen ist 26,1 bp (pos/>3bp), gegen 16 bp Taker-Round-Trip. Netto positiv nach 16 bp bleibt nur pos/>3bp (Fade −42,1, Bounce +1,8 bp); das sind kleine Gruppen mit Standardfehlern in derselben Größenordnung. Die Kontrolle um 4 Stunden versetzt (kein Funding) zeigt vorher −0,5 ± 0,8 und nachher +4,0 ± 0,8 bp: die Bewegung um das Funding unterscheidet sich nicht vom Rest des Tages. Die Funding-Sätze auf Bitget sind im Sommer 2026 klein (meist der Standardsatz 1 bp); was um den Zeitpunkt passiert, ist in der Größe eines einzelnen Spreads und trägt keinen Taker-Trade.

## Datenlücken und Grenzen

- Zeitraum 2026-07-20 15:10 bis 2026-10-18 15:59 UTC, also ein Sommer- und Frühherbstquartal 2026. Das ist eine Marktphase, kein Zyklus.
- Fehlende Minuten je Symbol: keine.
- Minutenkerzen zeigen nicht, in welcher Reihenfolge Tief und Hoch innerhalb der Minute lagen. Die Simulation nimmt den Stop vor dem Ziel und zählt das Ziel in der Einstiegskerze nur über den Schluss. Fills am Limit sind angenommen, wenn der Kurs darunter handelte; in einem Liquidations-Sturz steht man in der Warteschlange, der echte Fill ist seltener.
- Funding-Sätze gibt es von Bitget nur 90 Tage; sie sind in diesem Zeitraum klein und eng um den Standardsatz.
- 5 Aktien-Perps über 11 Wochen sind 55 Symbol-Wochen, die untereinander korreliert sind (gleicher Markt, gleiche Nachrichten). Jede Aussage dazu hat die Trennschärfe von etwa einem Dutzend Beobachtungen.
- Bitgets history-candles liefert mit `endTime` die Kerzen bis zu dieser Schlusszeit einschließlich; wer wie `bitget_client.get_history_candles` mit `endTime = ältester − 1` weiterblättert, verliert je Seite eine Kerze. `research.fetch_1m` blättert mit `endTime = ältester` und füllt Lücken nach.
