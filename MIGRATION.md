# Umzug von den Subaccounts

Die alten Bots hatten je einen API-Key auf einem eigenen Subaccount. Dieser Bot ersetzt sie durch **ein** Konto und **einen** Key. Nicht alle drei Keys in eine Config kleben: ein Key handelt nur das Konto, für das er ausgestellt wurde.

## Was wohin gehörte

| Alter Bot | Subaccount in den Auswertungen | Hier |
| --- | --- | --- |
| V1 Reversal (`bitget_bot_v1`, Branch `cursor/enforce-trading-rules-ba7c`) | `at-HNKHNKHNK` | Strategie `reversal`, **aus** |
| V3 Sniper (`bitget_bot_v3`, Branch `cursor/pause-sniper-no-edge-b4fe`) | `at-HNKHNKHNKHNK` | Strategie `sniper`, **aus** (`entries_paused`) |
| Grid (`bitget_bot_grid-`, Branch `cursor/import-grid-bot-a947`), davor V2 | `at-HNKHNK` | Strategie `grid`, in Paper **an** |
| V4 TrendJoin | Repo leer, kein Subaccount | Strategie `trendjoin`, Signal TODO |

Die Namen stammen aus den STRATEGY-/TRADING_RULES-Dateien der alten Repos (Stand der genannten Branches). Wenn ein Subaccount inzwischen anders heißt, zählt das, was in Bitget unter dem jeweiligen Key hängt, nicht dieser Text.

## Reihenfolge

1. **Alte Prozesse stoppen.** Nicht parallel laufen lassen. Zwei Bots auf demselben Geld doppelkaufen; zwei Bots auf verschiedenen Subaccounts sind genau der Zustand, der hier enden soll.
2. **Flach ziehen.** Je Subaccount: keine offene USDT-M-Lage, keine offenen Orders, keine Trigger-Stops, die später noch feuern. Erst dann Geld bewegen.
3. **USDT verschieben.** In Bitget: Transfer vom Subaccount auf das eine Zielkonto, Wallet USDT-M Futures (und, falls der Funding-Slot später Spot braucht, einen Teil Spot-USDT — jetzt nicht nötig). Interne Umbuchung, kein Withdraw auf eine externe Adresse. Etwas Staub für eine letzte Funding-Abrechnung auf dem alten Konto lassen, bis die Position wirklich 0 ist.
4. **Alte Keys entmachten.** Trade-Recht der drei Subaccount-Keys entziehen oder die Keys löschen, sobald die Konten leer und die Prozesse tot sind. Withdraw-Recht hatten sie hoffentlich nie; der neue Key bekommt es nicht.
5. **Einen neuen Key** auf dem Zielkonto: Lesen und Trade, kein Withdraw, IP-Whitelist auf den Host. Passphrase setzen.
6. **`config.py` nur lokal.** `cp config.example.py config.py`, die drei Felder `API_KEY`, `SECRET_KEY`, `PASSPHRASE` füllen. `DEMO_MODE = False` für das echte Konto, `True` nur für ein Bitget-Demo-Konto (`paptrading`). `DRY_RUN` und `LIVE_TRADING` auf den Paper-Defaults lassen.
7. **Positionsmodus Hedge, Margin Isolated, USDT-M.** Der Live-Start setzt das selbst. Steht das Konto auf One-Way und es liegen noch Lagen, zuerst flach machen — der Moduswechsel scheitert sonst an der Börse. Dieser Bot lädt `POS_MODE != hedge` gar nicht.
8. **Paper gegen das echte Konto.** `python3 -m unified_bot`. Mit gültigen Keys liest der erste Start die Equity und nimmt sie als Anker, sendet aber keine Orders. Im Status muss der Modus `paper` sein, Grid an, die anderen aus. Die Fallback-Kontraktwerte für SNDK, INTC und ANTHROPIC werden durch die öffentliche Contract-Abfrage ersetzt, sobald sie klappt. Stimmen Mindestgröße oder Step nicht, lehnt das Grid ab statt unter 5 USDT zu handeln.
9. **Erst dann Live**, und nur mit Geld, dessen Totalverlust verkraftbar ist. Siehe den Abschnitt „Vor Live“ unten. `DRY_RUN = False`, `LIVE_TRADING = True`, Start mit `python3 -m unified_bot --live`.

Der Zustand aus Paper (`state/unified_state.json` mit `"mode": "paper"`) wird im Live-Prozess ignoriert, und umgekehrt. Nach dem Umschalten ist das lokale Buch leer, bis der Abgleich läuft. Vor dem ersten Live-Start sollte das Börsenkonto flach sein, sonst friert der Abgleich Symbole mit fremder Lage ein und fasst sie nicht an.

## Was nicht mitwandert

- Getrennte Subaccount-Equity. Es gibt nur noch Sleeves auf einem Anker. Grid-Default sind 50 % von `PAPER_EQUITY` 100, also 50 USDT — dieselbe Größenordnung wie das alte Paper-Kapital. Auf einem echten Konto ist der Anker die gelesene Equity, das Grid-Sleeve bleibt 50 % davon, bis du `allocation` änderst.
- Telegram-Tokens aus den alten Dateien. Hier sind Token und Chat leer. Nichts aus `sniper_bot.py` übernehmen: dort lag ein Token im Quelltext. Hier nicht.
- `bot_state.json`, `spread_learnings.json`, `grid_state.json` der alten Repos. Das neue Format ist `state/unified_state.json`. Nicht umbenennen und hoffen.
- One-Way-Netting. Bewusst nicht. Siehe Architektur.

## Vor Live noch offen

- V4 hat kein Signal. Funding-Arbitrage und Daily Trend sind leere Slots. Spot-Orders werden nicht live geschickt.
- V1 und V3 sind aus, weil die ausgewerteten Samples nach Fees negativ waren. Sie anschalten ist eine bewusste Config-Änderung, kein Bugfix.
- Der Grid-Backtest auf den großen Paaren war nach Fees leicht negativ. DOGE, SUI, SNDK, INTC, ANTHROPIC sind die Universum-Auswahl aus dem alten Report, kein neuer Live-Nachweis.
- Kontrakt-Specs der Aktien-Perps vor dem ersten echten Grid gegen die Börse prüfen (`minTradeNum`, `sizeMultiplier`, `minTradeUSDT`). Der Bot lehnt zu kleine Orders ab, er rät die Spec nicht zuverlässig, wenn die API nichts liefert.
- Hedge-Modus muss auf dem Konto wirklich stehen. Ein verbleibender One-Way-Rest friert das Symbol ein.
- Kill-Switch einmal in Paper gesehen haben (Datei `KILL_SWITCH` anlegen, Orders weg, Datei löschen).
- Fee-Stufe prüfen. Gerechnet wird VIP0, Maker 0,02 %, Taker 0,06 %.
- Kein zweiter Bot, kein alter Subaccount-Prozess, kein Withdraw auf dem Key.
- Der Status ist im Geiste von `/api/agent/closed` (Trade-Liste mit Strategie). Er ist kein bytegenaues Abbild eines Monitors, dessen Schema nicht in diesen Repos lag.
