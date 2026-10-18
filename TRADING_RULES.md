# Handelsregeln

Diese Regeln setzt der Bot durch. Wer sie in der Config aufweicht, umgeht die Schutzlogik nicht an jeder Stelle — Mindestabstand, Mindestgröße, Hebel-Deckel und der Live-Schalter bleiben im Code.

## Modus

1. Default ist Paper. Es gibt keine echten Orders.
2. Live nur wenn `DRY_RUN = False` **und** `LIVE_TRADING = True`.
3. Platzhalter-Keys (`your_bitget_…`) werden im Live-Modus abgelehnt.
4. `config.py` wird nicht ins Repo gelegt. Tokens nicht in den Code und nicht in Logs schreiben.

## Markt und Konto

5. Nur USDT-M Perpetuals (`USDT-FUTURES`), Standard Isolated.
6. Positionsmodus Hedge, wie V2. `side` ist im Hedge die Positionsrichtung: Close-Long ist `side=buy` und `tradeSide=close`. Das ist der Reduce-only-Exit. `reduceOnly=YES` geht nur im One-Way-Modus (`POS_MODE = "one_way"`), ohne `tradeSide`.
7. Symbole nur aus `SYMBOLS`. Default nach dem Universum-Backtest: DOGEUSDT, SUIUSDT, SNDKUSDT, INTCUSDT, ANTHROPICUSDT. BTC, ETH und BNB sind dort bewusst nicht enthalten.
8. Hebel pro Symbol höchstens `MAX_LEVERAGE` (Default 3), Default 2. Ein V2-Wert von 5× wird auf 3× gekürzt.
9. Höchstens `MAX_ACTIVE_GRIDS` Grids gleichzeitig (Default 1).

## Wann ein Grid überhaupt aufgemacht wird

10. 1h- und 4h-Regime müssen seitwärts sein: ADX unter der Schwelle, Efficiency Ratio niedrig, Bollinger-Breite oder ATR komprimiert, genug Mittelkreuzungen im Swing-Fenster.
11. Die Range kommt aus dem Swing-Hoch und Swing-Tief der letzten 48 geschlossenen Stunden. Live verwirft die laufende Kerze, die Bitget als letzte mitliefert, genau wie der Backtest. Der Schluss muss im mittleren Bereich liegen, nicht am Rand.
12. Die Range darf nicht enger als `MIN_RANGE_PCT` und nicht weiter als `MAX_RANGE_PCT` sein.
13. Der Abstand zweier Levels muss mindestens dem Dreifachen der Maker-Round-Trip-Fee entsprechen. Bei 0,02 % Maker sind das 0,12 % vom Preis. Passt die gewünschte Levelzahl nicht, wird sie reduziert. Passt auch die Mindestzahl nicht, gibt es kein Grid.
14. Jede Order muss `minTradeNum` und `minTradeUSDT` (bei diesen Kontrakten 5 USDT) erfüllen, nach Step gerundet, ohne wissenschaftliche Notation. Reicht die Margin für mindestens eine Buy- und eine Sell-Order nicht, wird das Grid abgelehnt. Es wird nicht unter der Börsenmindestgröße „aufgefüllt“.

## Orders

15. Grid-Einstiege und Take-Profits sind Limit und `force=post_only`. Ein Buy, der den Ask erreichen würde, und ein Sell, der den Bid erreichen würde, werden verworfen.
16. Take-Profit schließt die Lage (Hedge: `tradeSide=close`). Es wird nicht an derselben Stufe neu eröffnet, solange das Los offen ist.
17. Inventory je Seite höchstens `MAX_INVENTORY_LEVELS` (Default 3). Margin für Lage plus öffnende Orders höchstens `MAX_MARGIN_FRACTION` des Kapitals (Default 50 %), abzüglich eines kleinen Puffers. Kapital ist live das Konto-Equity, nicht `available`. Ist der Kontostand nicht lesbar, bleiben die liegenden Orders unverändert und es startet kein neues Grid.
18. Notausstieg ist die einzige Taker-Strecke: erst Post-only-Close, `FLATTEN_MAKER_TIMEOUT_S` warten, Rest per Market-IOC. Im Backtest wird der Notausstieg sofort als Taker plus Slippage gerechnet, ohne einen optimistischen Maker-Fill.

## Ausstieg und Limits

19. Schluss außerhalb der Range plus `BREAKOUT_BUFFER_PCT`: Grid aus, Orders weg, Lage zu.
20. Regime dreht auf Trend: dasselbe.
21. Harter Stop je Grid: Netto aus realisiert, offen, Fees und Funding kleiner oder gleich `-GRID_HARD_STOP_PCT` des Kapitals beim Aufmachen.
22. Tagesverlust: vom Equity zum UTC-Tagesstart mehr als `DAILY_LOSS_PCT` weg. Dann zu, und an diesem UTC-Tag kein neues Grid. Am nächsten Tag ist das Tageslimit zurückgesetzt, der Kill-Switch nicht.
23. Kill-Switch (`KILL_SWITCH`-Datei oder Config) schließt alles und bleibt, bis die Datei weg ist und der Config-Schalter aus ist.
24. Nach einem Ausstieg Cooldown von `COOLDOWN_BARS` Stunden auf diesem Symbol.

## Neustart

25. Zustand liegt in `state/grid_state.json`. Schreiben ist atomar.
26. Paper- und Live-Zustand werden nicht vermischt. Ein Wechsel des Modus ignoriert das alte File.
27. Live beim Start: bekannte Orders mit der Börse abgleichen (Fill übernehmen, lebende Order behalten, Storno verwerfen). Weicht die Börsenposition von den lokalen Lots um mehr als einen Step ab, wird das Symbol eingefroren und nicht weiter bekauft. Fremde Positionen ohne Grid-Zustand werden nicht angefasst. Verwaiste Orders mit der Id-Vorsilbe `grd` werden storniert. Im laufenden Betrieb wird die Börsenlage jede Runde gegen die Lots geprüft; steht eine Abweichung zwei Runden hintereinander, wird das Symbol ebenso eingefroren. Ein Storno fragt danach den Order-Stand ab und verbucht Fills, die vorher noch durchkamen.
28. Ein Börsen-Stop auf der gesamten Long- bzw. Short-Lage an der Range-Grenze ist versucht (`EXCHANGE_STOP`), ersetzt aber keinen laufenden Prozess. Die lokale Notfall-PnL nach einem Taker-Exit ist eine Schätzung; maßgeblich ist der Fill an der Börse.

## Telegram

29. `TG_TOKEN` und `TG_CHAT_ID` leer lassen, wenn nichts gesendet werden soll. Alternativ die Umgebungsvariablen `TELEGRAM_BOT_TOKEN` und `TELEGRAM_CHAT_ID`. Der Token wird nicht geloggt.
