# Architektur

Ein Prozess, ein API-Key, mehrere Strategien. Die Börse sieht ein Hedge-Konto. Die Strategien sehen nur ihr Sleeve.

```text
Marktdaten (öffentlich)
        │
        ▼
   Strategie.plan(ctx)  ──►  OrderIntent / Cancel / Stop
        │
        ▼
   RiskManager          Globale Limits, Fee-Abstand, Mindestgröße, Pause, Kill
        │
        ▼
   Symbol-Sperre        Ein Symbol gehört höchstens einer Strategie
        │
        ▼
   OrderManager         Hedge-Payload, Post-only, clientOid
        │
        ├── PaperBroker  (Default)
        └── LiveBroker   (nur --live)
        │
        ▼
   Book / Ledger        PnL, Fees, Funding je Strategie
        │
        ▼
   state/unified_state.json
   GET /api/agent/status
   GET /api/agent/closed
```

## Strategie-Schnittstelle

Jede Strategie implementiert:

- `plan(ctx) -> CyclePlan` mit Orders, Stornos und Stop-Nachzügen
- `consume_fill(fill, book)` für strategieeigenen Zustand (das Grid führt seine Lots)
- `on_reject(intent, reason)`
- `export_state` / `load_state`

Ein Intent beschreibt Seite, Zweck (`open`, `close`, `reduce`, `emergency`), Größe, Preis, Hebel und das Gewinnziel. Die Strategie signiert nichts und kennt den API-Key nicht.

`CycleContext` enthält nur das Sleeve der Strategie, ihre Positionen und ihre Orders, plus die Marktsicht der erlaubten Symbole.

Neue Strategie: Modul unter `unified_bot/strategies/`, Eintrag in `registry.py`, Vorsilbe in `ids.py`, Block in `STRATEGIES`. Die Registry sortiert nach `priority`. Wer zuerst eine Sperre setzt, behält das Symbol.

## Order-Manager

USDT-M, Isolated, Hedge.

- Entry-Limit ist Post-only (`force=post_only`), außer die Strategie setzt `post_only=False`.
- Market nur für Stop, Time-Stop, Notausstieg und Kill-Switch (`force=ioc`), mit Slippage im Paper.
- Close-Long ist `side=buy` und `tradeSide=close`. Das ist der Reduce-only-Exit im Hedge. `reduceOnly=YES` wäre One-Way und wird nicht gebaut.
- Ein Limit, das den Ask (Buy) oder den Bid (Sell) erreichen würde, wird lokal als `would_cross` verworfen.
- `clientOid` beginnt mit der Strategie-Vorsilbe.

| Strategie | Vorsilbe |
| --- | --- |
| reversal | `rv1` |
| sniper | `sn3` |
| grid | `grd` |
| trendjoin | `tj4` |
| funding_arb | `fra` |
| daily_trend | `dtr` |

Spot-Payloads kann `build_spot_payload` bauen. Der Manager lehnt Spot von jeder Strategie außer dem Funding-Slot ab, und der Slot schickt nichts, solange er Recherche ist.

## Symbol-Sperre (keine Netting-Vermischung)

Bitget führt im One-Way-Modus je Symbol nur eine Nettoposition. Im Hedge-Modus gibt es je Symbol eine Long- und eine Short-Lage — aber immer noch nur **eine** Long-Lage für das ganze Konto, nicht eine je Strategie. Zwei Strategien, die beide DOGE long wollen, wären nach dem Fill nicht mehr trennbar. Funding, Liquidation und der Börsen-Stop hängen an dieser einen Lage.

Deshalb **keine** virtuelle Aufrechnung gegeneinander.

Regel:

1. Ein Symbol ist frei oder gehört genau einer Strategie.
2. Die Sperre entsteht mit der ersten akzeptierten Entry-Order (auch wenn sie nur liegt).
3. Dieselbe Strategie darf beide Seiten halten. Das Grid macht das: Long unter dem Preis, Short darüber.
4. Eine andere Strategie, die dasselbe Symbol long **oder** short öffnen will, bekommt `symbol_locked`.
5. Schließen darf nur der Eigentümer. Ist die Strategie flat (keine Lage, keine Entry-Order), fällt die Sperre.
6. Eine Börsenlage ohne unsere Vorsilbe und ohne lokalen Zustand wird nicht angefasst. Das Symbol wird eingefroren.
7. Priorität bei zwei Intents im selben Zyklus: kleinere `priority` zuerst. Default: Grid 10, Reversal 20, Sniper 30, TrendJoin 40, Funding 50, Daily 60.

Die Default-Symbole überlappen sich nicht (Grid: DOGE/SUI/SNDK/INTC/ANTHROPIC, Reversal: BTC/ETH/BNB, Sniper: BTC/ETH/SOL/BNB/HYPE). Die Sperre wird scharf, sobald zwei Strategien dasselbe Symbol handeln dürfen.

## Ledger

`Book` hält je Strategie:

- Allokation × Start-Equity
- realisierter Preis-PnL
- Fees
- Funding
- offene Lage und liegende Orders

Sleeve-Cash = Anteil am Anker + realisiert − Fees − Funding. Unrealisiertes zählt zur Konto-Equity und zum Tagesverlust, nicht als freie Margin für neue Entries.

Der Anker ist `PAPER_EQUITY` (100 USDT), außer es liegen echte Keys und noch kein Zustand: dann wird die USDT-M-Equity gelesen. Paper sendet dabei keine Order.

Funding im Paper und als Abschlag: 0,01 % je 8 Stunden auf den Betrag der Nettoposition, dem Eigentümer des Symbols gutgeschrieben. Das ist keine historische Funding-Rate.

## Risiko

Siehe [TRADING_RULES.md](TRADING_RULES.md). Kurz: Hebel-Deckel, Brutto-Exposure, Tagesverlust, Kill-Switch-Datei, `enabled` / `entries_paused`, Größe auf `sizeMultiplier` **abgerundet**, unter `minTradeNum` oder 5 USDT abgelehnt, Take-Profit unter dem Dreifachen der Round-Trip-Fee abgelehnt.

Exits bleiben erlaubt, wenn Entries gesperrt sind.

## Neustart

`state/unified_state.json` wird atomar geschrieben (tmp + replace). Enthalten sind Ledger, Orders, Positionen, Sperren, Risiko-Tag, Strategie-Zustand (Grid-Lots, Sniper-Sweep).

Beim Start:

- Modus in der Datei muss zum Prozess passen, sonst wird sie ignoriert.
- Live: offene Börsenorders gegen die Vorsilbe. Bekannte Orders bleiben, Fills werden nachgezogen. Verwaiste Orders **mit** unserer Vorsilbe werden storniert. Orders **ohne** Vorsilbe bleiben.
- Weicht die Börsenmenge je Seite um mehr als einen halben Step von der lokalen Menge ab, wird das Symbol eingefroren und nicht weiter eröffnet.
- Paper spiegelt den lokalen Zustand. Es gibt keine Börse, gegen die man falsch abgleichen könnte.

## Status

Der HTTP-Server läuft im Bot-Prozess (Default-Port 8767).

`GET /api/agent/closed` :

```json
{
  "agent": "unified",
  "mode": "paper",
  "count": 1,
  "trades": [
    {
      "strategy": "grid",
      "symbol": "DOGEUSDT",
      "side": "long",
      "qty": 50,
      "entry": 0.12,
      "exit": 0.121,
      "gross_pnl": 0.05,
      "fees": 0.002,
      "funding": 0.0,
      "net_pnl": 0.048,
      "opened_ms": 0,
      "closed_ms": 0,
      "exit_reason": "tp",
      "client_oid": "grd000000001",
      "market": "perp"
    }
  ]
}
```

`GET /api/agent/status` liefert Equity, Sleeves, Sperren, offene Orders, Positionen, Halt-Grund. Die Startseite zeigt dasselbe auf Deutsch.

Telegram (`unified_bot/telegram.py`) tut nichts, solange Token und Chat leer sind. Der Token wird nicht geloggt. Es gibt keinen Default-Token im Code.

## Backtest

`unified_bot/gridcore/backtest_engine.py` ist die Engine aus `bitget_bot_grid`. `python backtest.py grid` füttert sie mit synthetischen Kerzen, damit der Lauf ohne API geht. Historische Börsenkerzen kann man derselben Funktion geben.

`run_reversal_replay` prüft das portierte V1-Muster (Long-Reversal, Wien-Stunden, 24h-Time-Stop, Fee-Abschlag). Die großen Jahres-Skripte aus `bitget_bot_v1` bleiben in dem Repo; sie hängen an lokalen Datenfiles und sind kein sauberer Import.

## Slots

`funding_arb` und `daily_trend` sind in der Registry, haben eine Vorsilbe und eine Allokation von 0. `plan` liefert eine TODO-Notiz und keine Intents. TrendJoin hat die Risikoregeln (siehe TRADING_RULES), `detect_breakout` gibt `None` zurück, bis `bitget_bot_v4` Code enthält.
