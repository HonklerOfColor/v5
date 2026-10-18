# Ein Bitget-Konto, alle Strategien

Ein Python-Bot für **ein** Bitget-Konto: UID **9711026741**, Name **at-HNK**, ein API-Key. USDT-M Perpetuals laufen im Hedge-Modus, Spot ist nur als Schnittstelle für eine spätere Funding-Arbitrage vorbereitet. Die alten Bots (je Subaccount einer) werden als Strategie-Module geführt. Orders gehen durch einen Order-Manager und einen Risiko-Manager. PnL, Fees und Funding hängen am virtuellen Unterkonto der Strategie.

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
python3 -m pytest -q
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

## Spot-Module (Paper)

Zwei Tagesstrategien auf **Bitget Spot**, nur als Paper. Sie haben je ein eigenes virtuelles Ledger (USDT plus Coin-Bestände), getrennt vom Perp-Buch, und laufen **einmal täglich kurz nach 00:05 UTC** auf der abgeschlossenen Tageskerze (`1Dutc`; Bitgets `1day` schließt um 16:00 UTC und wird deshalb nicht benutzt). Die laufende Kerze wird in `closed_only()` verworfen. Pro UTC-Tag gibt es genau einen Lauf, auch nach Neustart (`state/spot_<modul>.json`). Bauauftrag und verbindliche Regeln: [docs/spot_modules/SPEC.md](docs/spot_modules/SPEC.md), [PREREG_trend_ensemble.md](docs/spot_modules/PREREG_trend_ensemble.md), [PREREG_trendfilter_dca.md](docs/spot_modules/PREREG_trendfilter_dca.md). Alle Parameter stehen in `unified_bot/spot/params.py` und werden nicht nachoptimiert.

**Es gibt keinen Live-Spot.** `unified_bot/spot/client.py` kann keine Orders senden, und es gibt nur einen Paper-Broker. Läuft der Bot mit `--live`, laufen die Spot-Module trotzdem als Paper und loggen das bei jedem Tageslauf.

| Modul | Regel | Kapital (Default) | Alarm |
| --- | --- | ---: | --- |
| `spot_trend_ensemble` | Top-10 Spot-Coins (monatlich nach 30-Tage-Median-Quote-Volumen, Ausschlüsse wie PREREG, mind. 60 Tage Historie), je Coin 1/10 Kapital, 9 Donchian-Fenster 5…360 Tage auf Schlusskursen: Einstieg über Fenster-Hoch, Trailing-Stop = Mittelband nur aufwärts, Ausstieg bei Schluss unter Stop. Gewicht je Fenster min(0,25/σ90, 1,0), Coin-Gewicht = Mittel der 9 Fenster. Rebalance bei Signaländerung oder > 20 % relativer Abweichung. Delisting = Schließen zum letzten Kurs. | 500 USDT | Drawdown > 15 % oder Paper vs. Schatten > 3 pp über 3 Monate |
| `spot_trendfilter_btceth` | 50 % BTC-, 50 % ETH-Sleeve. Exposure je Sleeve = Mittel der Binärsignale Close > SMA(n), n ∈ {20, 50, 100, 150, 200}, Rest USDT. Rebalance sofort bei Signaländerung, sonst nur bei > 20 % relativer Abweichung. | 500 USDT | Drawdown > 50 %, Paper vs. Schatten > 5 pp über 3 Monate, oder > 25 Trades im Monat |

Kosten im Paper: 0,10 % Gebühr + 0,05 % Slippage je Seite. Mindestorder und Mengenrundung (`minTradeUSDT`, `quantityPrecision`) kommen live von `/api/v2/spot/public/symbols`; `docs/spot_modules/code/bitget_spot.json` ist nur der Offline-Stand für Tests. Eine Umschichtung unter der Mindestorder wird übersprungen und geloggt (Logik wie `capital.py`: Ziel unter Mindestorder wird 0). Ausführung im Paper zum Ticker-Kurs kurz nach 00:00 UTC; die **Schattenrechnung** führt dieselben Regeln täglich idealisiert (zum Schlusskurs, ohne Mindestorder, gleiche Kosten) mit und speichert die Abweichung.

Erwartung laut Backtest (SPEC): Trend-Ensemble OOS Sharpe 0,81, 6,2 % p.a., MaxDD −15 %, seit 03/2025 nur Sharpe 0,42, realistisch 3–8 % p.a. Trendfilter OOS Sharpe 0,92, CAGR 28,5 %, MaxDD −29 % (gesamt −47 %), ~17 Umschichtungen/Jahr; der ähnliche Bitwise-ETF BITC liegt live weit unter seinem Backtest. Paper-Laufzeit mindestens 6 Monate, dann Entscheidung. Alarme gehen über Telegram (wenn konfiguriert) und ins Log und setzen das Flag `alarm` im Status; es gibt keinen automatischen Abbruch.

Universumswahl in der Umsetzung: Bitget hat über 3400 Online-USDT-Paare, davon ~2900 Tokenized Stocks (`rSPY`, `rNVDA`, …, ohne Kerzen über die API) und Pre-Market-Token (`preXXX`); die fallen über die Namensregel raus, wie PREREG es für Tokenized Stocks verlangt. Kandidaten sind dann die Top-100 nach 24h-USDT-Volumen aus dem Ticker (plus aktuelles Universum und Bestände); darauf laufen die exakten PREREG-Regeln (30-Tage-Median ≥ 2 Mio USDT wie in `lib.universe`, 60 Tage Historie, Namens- und Rendite-Ausschlüsse). Die Wahl gilt für den Monat und wird am Tag nach dem Monatsende getroffen. Der Donchian-Zustand wird täglich aus bis zu 1000 Tageskerzen je Coin neu gerechnet.

```python
# config.py
SPOT_MODULES_ENABLED = True
SPOT_TREND_ENABLED = True
SPOT_TF_ENABLED = True
SPOT_TREND_CAPITAL_USDT = 500.0
SPOT_TF_CAPITAL_USDT = 500.0
```

Status je Modul (Equity, Positionen, Exposure, Trades, Drawdown, Abweichung zur Schattenrechnung, letzter Lauf, Alarm-Flags, Universum):

- [http://127.0.0.1:8767/api/v5/spot](http://127.0.0.1:8767/api/v5/spot)
- [http://127.0.0.1:8767/api/v5/spot/spot_trend_ensemble](http://127.0.0.1:8767/api/v5/spot/spot_trend_ensemble)
- [http://127.0.0.1:8767/api/v5/spot/spot_trendfilter_btceth](http://127.0.0.1:8767/api/v5/spot/spot_trendfilter_btceth)
- `/api/v5/spot/<modul>/trades.csv` — alle Paper-Trades (Datum UTC, Symbol, Seite, Menge, Preis, Gebühr, Wert in USDT) für die Steuer

Werkzeuge ohne Netz-Orders:

```bash
python3 -m unified_bot.spot export-trades --module spot_trend_ensemble --out trades_trend.csv
python3 -m unified_bot.spot status --module spot_trendfilter_btceth
```

**Spot-Fähigkeit at-HNK prüfen** (nur lesend, mit dem Key aus `config.py`; wird nie automatisch ausgeführt):

```bash
python3 -m unified_bot.spot check-account
```

Liest `/api/v2/spot/account/info` (UID, Rechte des Keys) und `/api/v2/spot/account/assets` (USDT im Spot-Wallet) und meldet, ob Spot-Konto und Handelsrecht für UID 9711026741 sichtbar sind. Sendet keine Order, gibt keinen Key aus. Erst wenn das bejaht ist, kann über Live-Spot überhaupt nachgedacht werden; dieser Stand enthält es nicht.

Tests (offline, feste Daten): `tests/test_spot_reference.py` prüft Signale, Universum und Equity-Pfad gegen Referenzwerte, die mit `docs/spot_modules/code/lib.py` und `tf.py` erzeugt wurden (`tests/fixtures/spot/make_fixtures.py`, Toleranz 1e-9). `tests/test_spot_modules.py` prüft laufende Kerze, Rebalance-Schwelle, Mindestorder, Delisting, Idempotenz, Live-Modus ohne Orders, Alarme, Schattenrechnung, Status und CSV.

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
| `unified_bot/spot/` | Spot-Module (Paper): Client (nur lesend), Paper-Broker, Ledger, Signale, Schattenrechnung |
| `docs/spot_modules/` | Bauauftrag, PREREG, Referenz-Backtest-Code, Spot-Specs (Offline-Stand) |
| `unified_bot/gridcore/` | Portierte Grid-Engine (Regime, Levels, Backtest) |
| `config.example.py` | Vorlage, keine Secrets |
| `ARCHITECTURE.md` | Aufbau, Symbol-Sperre, clientOid |
| `TRADING_RULES.md` | Was der Bot durchsetzt |
| `MIGRATION.md` | Weg von den Subaccounts |

Futures können das Konto aufbrauchen. Der Grid-Backtest der Alt-Symbole war nach Fees nicht der Beweis für einen Vorteil. Details in den verlinkten Dateien.
