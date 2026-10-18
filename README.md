# Bitget USDT-M Grid-Bot

Grid-Trading auf Bitget USDT-M Perpetuals, nur in seitwärts laufenden Märkten, nur mit Post-only-Maker-Orders. Ersatz für den abgeschalteten V2-Bot. Paper ist der Default: ohne ausdrückliche Live-Schalter geht keine Order an die Börse.

Die API-Felder heißen wie in V2, damit die Keys des Subaccounts `at-HNKHNK` in `config.py` eingesetzt werden können: `API_KEY`, `SECRET_KEY`, `PASSPHRASE`, `DEMO_MODE`, `DRY_RUN`, `PRODUCT_TYPE`, `MARGIN_MODE`, `MARGIN_COIN`, `SYMBOLS`.

## Schnellstart (Paper)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.py config.py    # Platzhalter reichen für Paper
python3 grid_bot.py --once        # ein Durchlauf
python3 grid_bot.py               # Loop, Standard 20 Sekunden
```

Paper simuliert Fills an 1-Minuten-Kerzen und schreibt `state/grid_state.json`. Es wird nichts signiert, solange keine echten Keys hinterlegt sind. Mit echten Keys liest Paper höchstens den Kontostand, sendet aber keine Orders.

```bash
python3 backtest.py --days 120 --equity 50
python3 -m unittest discover -s tests -t .
```

## Live

Erst nach Paper-Lauf und nach dem Lesen von [STRATEGY.md](STRATEGY.md) und [TRADING_RULES.md](TRADING_RULES.md). In `config.py` müssen **beide** Schalter gesetzt sein:

```python
DRY_RUN = False
LIVE_TRADING = True
```

Ein altes V2-`config.py` mit `DRY_RUN = False` und ohne `LIVE_TRADING` bleibt im Paper-Modus. `DEMO_MODE = True` setzt den Header `paptrading: 1` (Demo-Konto). Für das echte Subaccount `DEMO_MODE = False`.

Kill-Switch: Datei `KILL_SWITCH` im Arbeitsverzeichnis anlegen oder `KILL_SWITCH = True` in der Config. Der Bot storniert das Grid und schließt die Lage. Datei löschen hebt den Schalter wieder auf.

## Dateien

| Datei | Rolle |
| --- | --- |
| `grid_bot.py` | Loop: Regime, Grid, Fills, Ausstieg, Zustand |
| `bitget_client.py` | REST, Signatur wie V2, öffentliche Kerzen ohne Key |
| `gridbot/` | Indikatoren, Regime, Order-Payloads, Risiko, Backtest |
| `backtest.py` | Historische 1h-Kerzen, Fee- und Funding-Modell |
| `research/` | Strategie-Vergleich: Grid-Varianten, 4h-Trendfolge, Mean-Reversion, gleiche Kosten. `python3 -m research.compare`, `python3 -m research.trend_report`, `python3 -m research.alternatives_report` (Carry, Momentum, Pullback, echtes Funding), `python3 -m research.pairs_report` (Pairs-Trading); Kerzen und Funding aus `data/research/` |
| `config.example.py` | Vorlage, keine Secrets |
| `telegram_notify.py` | Optional, still wenn Token leer ist |

`config.py` steht in `.gitignore` und wird nicht committed.

## Hinweis

Futures-Handel kann das Konto aufbrauchen. Der Backtest auf 120 Tagen mit 50 USDT Startkapital ist nach Fees leicht negativ, über ein Jahr und 28 Coins klar negativ. Von den geprüften Alternativen hat nur die 4h-Trendfolge eine gesunde Kostenstruktur, und auch sie trägt mit 50 USDT nicht. Details in [STRATEGY.md](STRATEGY.md).
