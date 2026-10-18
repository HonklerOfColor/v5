# Handelsregeln

Diese Regeln setzt der gemeinsame Bot durch. Eine Strategie kann enger sein. Weiter als der globale Deckel kommt sie nicht.

## Modus

1. Default ist Paper. Es gibt keine echten Orders.
2. Live nur wenn `DRY_RUN = False` und `LIVE_TRADING = True` und der Prozess mit `--live` startet.
3. Platzhalter-Keys (`your_bitget_…`) werden im Live-Modus abgelehnt.
4. `config.py` wird nicht ins Repo gelegt. Tokens nicht in den Code und nicht in Logs.

## Konto

5. Ein API-Key, ein Konto. USDT-M Perpetuals, Isolated, **Hedge**. One-Way wird beim Laden abgelehnt.
6. Im Hedge ist `side` die Positionsrichtung. Close-Long ist `side=buy`, `tradeSide=close`.
7. Kapital je Strategie ist ein Anteil an der Equity (`allocation`). Die Summe darf 1,0 nicht überschreiten. Allokation 0 blockiert Entries (`no_allocation`).
8. Ein Symbol gehört höchstens einer Strategie (siehe [ARCHITECTURE.md](ARCHITECTURE.md)). Dieselbe Strategie darf Long und Short gleichzeitig halten. Gegenläufige oder überlappende Entries einer zweiten Strategie auf demselben Symbol werden mit `symbol_locked` abgelehnt. Es wird nicht nettogerechnet.
9. Globale Hebelobergrenze `GLOBAL_MAX_LEVERAGE` (Default 5, damit TrendJoin später 5× darf). Zusätzlich der Deckel der Strategie. Grid-Default 2, Deckel 3. Reversal 3. Sniper 3. TrendJoin 5.
10. Brutto-Exposure (offene Lagen plus liegende Entries, Notionalsumme) höchstens `MAX_TOTAL_EXPOSURE` × Equity (Default 1,5).
11. Tagesverlust: Equity fällt gegenüber dem UTC-Tagesstart um mindestens `DAILY_LOSS_PCT` (Default 5 %). Dann keine neuen Entries, offene Lagen werden per Market geschlossen. Am nächsten UTC-Tag ist das Tageslimit zurückgesetzt. Der Kill-Switch nicht.
12. Kill-Switch: Datei `KILL_SWITCH` oder `KILL_SWITCH = True`. Eigene Orders weg, eigene Lagen zu, bis die Datei weg ist und der Config-Schalter aus ist.
13. `enabled = False` ist aus. `entries_paused = True` ist die ENTRIES_PAUSED-Semantik: keine neuen Entries, Verwaltung offener Lagen läuft weiter. Beides zusammen ist der Default von V1, V3 und V4.

## Größe und Fees

14. Größe wird auf `sizeMultiplier` **abgerundet**, nie aufgerundet. Liegt sie danach unter `minTradeNum`, heißt der Grund `below_min_size`.
15. Notional unter `max(minTradeUSDT, 5 USDT)` wird abgelehnt (`below_min_notional`).
16. Ein Entry ohne erkennbares Gewinnziel (`take_profit` oder `expected_tp_pct`) wird abgelehnt.
17. Der Abstand zum Ziel muss mindestens `FEE_TP_MULT` (Default 3) mal die Round-Trip-Fee sein.
    - Beides Maker: 2 × 0,02 % × 3 = **0,12 %**.
    - Maker-Entry und Taker-Exit: (0,02 % + 0,06 %) × 3 = **0,24 %**.
18. Initial-Margin des Entries muss ins freie Sleeve passen (Allokation plus realisiert minus Fees minus Funding minus schon gebundene Margin). Unrealisiertes wird nicht als Kaufkraft gezählt.
19. Entry-Limits sind Post-only. Ein Buy auf oder über dem Ask und ein Sell auf oder unter dem Bid werden lokal verworfen. Market ist Stop, Zeit-Stop, Notausstieg, Kill.
20. Grid-Stückzahlen, die nicht schon auf dem Step liegen, werden nicht still gekürzt (`size_step`), damit die Lots nicht von der Börsenorder abweichen.

Fees im Modell: Maker 0,02 %, Taker 0,06 % (VIP0). Live überschreibt den Kontrakt aus `/api/v2/mix/market/contracts`, wenn die Abfrage klappt. Fallback-Specs für DOGE, SUI, SNDK, INTC, ANTHROPIC sind Platzhalter und müssen vor Live von der Börse kommen.

## Grid (an)

Port aus `bitget_bot_grid`, Branch `cursor/import-grid-bot-a947`.

21. Symbole: DOGEUSDT, SUIUSDT, SNDKUSDT, INTCUSDT, ANTHROPICUSDT. BTC, ETH und BNB sind bewusst nicht dabei.
22. Höchstens ein Grid gleichzeitig. Hebel 2, Deckel 3.
23. 1h- und 4h-Regime seitwärts: ADX, Efficiency Ratio, Bollinger-Breite oder ATR-Kompression, genug Mittelkreuzungen. Range aus 48 Stunden, Schluss nicht am Rand, Spanne 0,8 % bis 8 %.
24. Level-Abstand mindestens das Dreifache der Maker-Round-Trip-Fee (0,12 %). Darunter kein Grid.
25. Entries und Take-Profits Post-only. Inventory je Seite höchstens 3. Margin für Lage plus öffnende Orders höchstens 50 % des **Sleeves**.
26. Schluss außerhalb der Range plus 0,25 %, Regime dreht, oder Grid-Netto ≤ −6 % des Sleeves beim Aufmachen: Orders weg, Lage per Market zu (erst wäre im alten Bot ein Post-only-Versuch; hier ist der Notausstieg Market, weil der Kill-Pfad derselbe Taker-Ausgang ist).
27. Nach dem Ausstieg 6 Stunden Cooldown auf dem Symbol.
28. Backtest-Engine ist dieselbe wie im alten Repo. Der dortige 120-Tage-Lauf auf BTC/ETH/BNB war nach Fees leicht negativ. Die neuen Symbole sind die Auswahl aus `universe_report`, kein Live-Beweis.

## V1 Reversal (aus)

Port der Entscheidungen aus `bitget_bot_v1`, Branch `cursor/enforce-trading-rules-ba7c`. `enabled = False`, `entries_paused = True`.

29. Nur Long. Signal: vorletzte 1h-Kerze rot, letzte grün.
30. Keine Entries in Europe/Vienna um 0, 1, 2, 3, 4, 14, 17, 20, 22 Uhr. Die Stunde kommt aus `zoneinfo`, nicht aus der Prozess-Zeitzone.
31. Hebel 3. Post-only am Bid. Spread über 1 % oder fehlendes Funding: kein Entry. Funding unter −0,05 %: kein Long.
32. Take-Profit 2,5 × ATR(14, 1h). Stop aus dem Tief der letzten 20 Stunden abzüglich 0,1 %, nie enger als 0,8 × ATR am Entry; ohne Chart 1,5 × ATR. Der Exit über den Stop ist Taker, deshalb gilt der weitere Fee-Abstand (0,24 %).
33. Liegt der Entry nach 60 Sekunden noch, wird er storniert.
34. Alter ≥ 24 h und ROE ≤ 0: Market-Close. Ein fehlender Mark-Preis schließt keinen Gewinner.
35. Alter ≥ 12 h, ROE ≥ 0,3 %, Peak-ROE noch unter 3 %, und der Entry liegt mindestens etwa 0,15 % vom Mark: Stop auf den Entry, nur enger.

Die 587 Live-Trades des alten Subaccounts waren nach Fees negativ. Deshalb ist das Modul aus, nicht weil die Regeln fehlen.

## V3 Sniper (aus)

Port aus `bitget_bot_v3`, Branch `cursor/pause-sniper-no-edge-b4fe`. `ENTRIES_PAUSED` ist hier `entries_paused = True` und zusätzlich `enabled = False`.

36. Long nur wenn gleichzeitig: Bid/Ask-Imbalance der Top 10 über 1,4, Sweep zurück über den Bid, Schluss über dem Mittel der letzten 20 Stunden-Schlüsse. Shorts sind aus.
37. Stunden-Sperre Europe/Vienna: 2, 3, 4, 14, 17, 20, 22. (0 und 1 sind die V1-Erweiterung, nicht V3.)
38. Hebel 3, Risiko 0,3 % des Sleeves, Stop 1,3 × ATR, Ziel 2,0 × ATR, höchstens eine Lage je Symbol und zwei insgesamt. Entry Post-only. Stop und erreichtes Ziel sind Market, wie der alte Trigger-Exit.
39. Dieselben Größen-Gates: nicht auf die Mindestorder aufrunden, nicht unter 5 USDT, nicht über die Sleeve-Margin, Ziel muss den dreifachen Round-Trip decken (enger als das alte 1×-Gate).

346 Live-Trades waren brutto kaum positiv und netto negativ. Wieder anschalten nur bewusst, und nur mit Sleeve, der die Mindestorder trägt.

## V4 TrendJoin (TODO)

`bitget_bot_v4` ist leer. `detect_breakout` gibt nichts zurück. Die Regeln, die ein späterer Port einhalten muss, laufen schon für eine vorhandene Lage:

40. Nur Long, Momentum-Breakout (Signal fehlt).
41. Hebel 5. Risiko 1 % des Sleeves je Trade. Größe aus Abstand zum Stop, dann auf den Step abgerundet.
42. Höchstens 3 offene Positionen, höchstens 5 Entries je UTC-Tag.
43. Nach einem Stop 24 Stunden kein Wiedereinstieg in dasselbe Symbol.
44. Zeit-Stop: Alter ≥ 24 h und PnL ≤ 0, dann Market-Close.
45. Ab 12 h im Gewinn: Stop auf den Entry.
46. Teilverkauf: ein Drittel als Post-only-Reduce, sobald der Lauf 0,75 R erreicht hat (R = Entry minus Stop).

Solange das Signal fehlt, entstehen keine Entries, auch wenn jemand `enabled` setzt. Die Notiz im Status bleibt `TODO`.

## Slots

47. `funding_arb`: vorgesehen ist Spot gegen Perp, wenn die Funding-Rate die Round-Trip-Kosten trägt. Kein Signal, keine Orders, Spot wird vom Manager noch nicht live geschickt.
48. `daily_trend`: Tages-Trendfolge. Kein Signal, bis eine vorher festgelegte Regel out-of-sample nach Fees positiv ist.

## Spot-Module (Paper)

50. `spot_trend_ensemble` und `spot_trendfilter_btceth` handeln nur im eigenen Paper-Ledger. Kein Pfad sendet Spot-Orders, auch nicht mit `--live`.
51. Signal nur aus abgeschlossenen Tageskerzen (00:00 UTC, `1Dutc`). Die laufende Kerze wird verworfen. Ein Lauf je UTC-Tag, nach 00:05 UTC, idempotent über Neustarts.
52. Parameter exakt wie `docs/spot_modules/PREREG_*.md` (siehe `unified_bot/spot/params.py`). Kein Nachoptimieren.
53. Kosten 0,10 % + 0,05 % je Seite. Mindestorder und Rundung aus den Spot-Specs; darunter wird übersprungen und geloggt. Glattstellungen (Ziel 0, Delisting) werden immer ausgeführt.
54. Alarm (kein Abbruch): Trend-Ensemble Drawdown > 15 % oder Abweichung zur Schattenrechnung > 3 pp über 3 Monate; Trendfilter Drawdown > 50 %, Abweichung > 5 pp über 3 Monate, oder > 25 Trades im Monat.

## Fremde Orders

49. Ohne die Vorsilbe `rv1` / `sn3` / `grd` / `tj4` / `fra` / `dtr` wird eine Order nicht storniert und eine Lage nicht geschlossen.
