# Ein Bitget-Konto, alle Strategien

Ein Python-Bot für **ein** Bitget-Konto (ein API-Key). USDT-M Perpetuals laufen im Hedge-Modus, Spot ist nur als Schnittstelle für eine spätere Funding-Arbitrage vorbereitet. Die alten Bots (je Subaccount einer) werden als Strategie-Module geführt. Orders gehen durch einen Order-Manager und einen Risiko-Manager. PnL, Fees und Funding hängen am virtuellen Unterkonto der Strategie.

**Paper ist der Default.** Ohne `DRY_RUN = False`, `LIVE_TRADING = True` und den Start mit `--live` verlässt keine Order die Maschine.

## Paper starten

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.py config.py    # Platzhalter reichen
python3 -m unified_bot --once     # ein Zyklus
python3 -m unified_bot            # Loop, Standard 20 Sekunden
```

Status:

- [http://127.0.0.1:8767](http://127.0.0.1:8767)
- [http://127.0.0.1:8767/api/agent/status](http://127.0.0.1:8767/api/agent/status)
- [http://127.0.0.1:8767/api/agent/closed](http://127.0.0.1:8767/api/agent/closed)

`/api/agent/closed` liefert geschlossene Trades mit dem Feld `strategy`. Paper schreibt `state/unified_state.json`. Ein Wechsel Paper/Live ignoriert die Datei des anderen Modus.

Mit echten Keys liest Paper höchstens die Equity (für die Sleeve-Größe) und sendet keine Orders. `config.py` wird nicht committed.

```bash
python3 -m unittest discover -s tests -t .
python3 backtest.py grid --equity 50
python3 backtest.py reversal
```

## Was standardmäßig handelt

| Strategie | Entries | Anteil | Symbole |
| --- | --- | ---: | --- |
| Grid | an (Paper) | 50 % | DOGE, SUI, SNDK, INTC, ANTHROPIC |
| V1 Reversal | aus | 0 | BTC, ETH, BNB |
| V3 Sniper | aus, `entries_paused` | 0 | BTC, ETH, SOL, BNB, HYPE |
| V4 TrendJoin | aus, Signal TODO | 0 | — |
| Funding-Arbitrage | Slot, Recherche | 0 | Spot + Perp, noch keine Orders |
| Daily Trend | Slot, Recherche | 0 | — |

V1 und V3 sind portiert, aber aus, weil die ausgewerteten Live-Trades nach Fees keinen Edge zeigen. Einschalten heißt in `config.py` unter `STRATEGIES` `enabled` und `entries_paused` setzen **und** eine Allokation > 0 geben, die zusammen mit den anderen nicht über 100 % liegt.

## Live

Erst Paper, dann [TRADING_RULES.md](TRADING_RULES.md) und [MIGRATION.md](MIGRATION.md). In `config.py`:

```python
DRY_RUN = False
LIVE_TRADING = True
```

```bash
python3 -m unified_bot --live
```

Fehlt einer der beiden Schalter, bleibt es Paper — auch mit `--live` bricht der Prozess ab, statt still Orders zu schicken. Platzhalter-Keys werden im Live-Modus abgelehnt. `POS_MODE` muss `hedge` sein.

Kill-Switch: Datei `KILL_SWITCH` im Arbeitsverzeichnis anlegen oder `KILL_SWITCH = True`. Der Bot storniert eigene Orders (erkennbar an der clientOid-Vorsilbe) und schließt die eigenen Lagen. Fremde Orders ohne Vorsilbe bleiben liegen.

## Dateien

| Datei | Rolle |
| --- | --- |
| `unified_bot/` | Loop, Order-Manager, Risiko, Ledger, Status |
| `unified_bot/strategies/` | Reversal, Sniper, Grid, TrendJoin, zwei leere Slots |
| `unified_bot/gridcore/` | Portierte Grid-Engine (Regime, Levels, Backtest) |
| `config.example.py` | Vorlage, keine Secrets |
| `ARCHITECTURE.md` | Aufbau, Symbol-Sperre, clientOid |
| `TRADING_RULES.md` | Was der Bot durchsetzt |
| `MIGRATION.md` | Weg von den Subaccounts |

Futures können das Konto aufbrauchen. Der Grid-Backtest der Alt-Symbole war nach Fees nicht der Beweis für einen Vorteil. Details in den verlinkten Dateien.
