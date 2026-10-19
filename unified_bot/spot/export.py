"""CSV-Export der Paper-Trades je Modul (für die Steuer: Datum UTC, Symbol, Seite, Menge, Preis, Gebühr, Wert)."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from unified_bot.spot.ledger import SpotTrade

COLUMNS = ["datum_utc", "symbol", "seite", "menge", "preis", "gebuehr_usdt", "wert_usdt", "grund", "modul"]


def trades_to_csv(trades: list[SpotTrade], module_id: str) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(COLUMNS)
    for trade in trades:
        stamp = datetime.fromtimestamp(trade.ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow(
            [
                stamp,
                trade.symbol,
                "Kauf" if trade.side == "buy" else "Verkauf",
                f"{trade.qty:.10g}",
                f"{trade.price:.10g}",
                f"{trade.fee:.8f}",
                f"{trade.value_usdt:.8f}",
                trade.reason,
                module_id,
            ]
        )
    return buffer.getvalue()
