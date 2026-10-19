"""Paper-Spot-Broker: long-only, kein Hebel, Gebühr und Slippage je Seite, Mindestorder und Rundung aus den Specs.

Es gibt keinen Live-Spot-Broker. Live-Spot ist nicht Teil dieses Standes; der Client kann keine Orders senden.
"""

from __future__ import annotations

from dataclasses import dataclass

from unified_bot.spot.engine import TradeDecision
from unified_bot.spot.ledger import SpotLedger, SpotTrade
from unified_bot.spot.params import FEE_RATE, SLIPPAGE_RATE
from unified_bot.spot.specs import SpotSpec, floor_quantity


@dataclass
class Execution:
    trade: SpotTrade | None
    note: str          # leer bei Erfolg, sonst Grund für das Überspringen


class PaperSpotBroker:
    mode = "paper"

    def __init__(self, fee_rate: float = FEE_RATE, slippage_rate: float = SLIPPAGE_RATE):
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate

    def execute(
        self,
        ledger: SpotLedger,
        decision: TradeDecision,
        price: float | None,
        spec: SpotSpec | None,
        ts_ms: int,
        default_min_usdt: float,
    ) -> Execution:
        symbol = decision.symbol
        minimum = spec.min_trade_usdt if spec and spec.min_trade_usdt > 0 else default_min_usdt
        precision = spec.quantity_precision if spec else 8
        if decision.delta > 0:
            if price is None or price <= 0:
                return Execution(None, f"{symbol}: kein Preis, Kauf übersprungen")
            fill_price = price * (1.0 + self.slippage_rate)
            qty = floor_quantity(decision.delta / fill_price, precision)
            value = qty * fill_price
            if qty <= 0 or value + 1e-9 < minimum:
                return Execution(
                    None,
                    f"{symbol}: Kauf {decision.delta:.2f} USDT unter Mindestorder {minimum:g} USDT nach Rundung, übersprungen",
                )
            fee = value * self.fee_rate
            if value + fee > ledger.cash + 1e-9:
                qty = floor_quantity(ledger.cash / (fill_price * (1.0 + self.fee_rate)), precision)
                value = qty * fill_price
                fee = value * self.fee_rate
                if qty <= 0 or value + 1e-9 < minimum:
                    return Execution(None, f"{symbol}: nicht genug USDT für die Mindestorder, übersprungen")
            trade = SpotTrade(ts_ms, symbol, "buy", qty, fill_price, fee, value, decision.reason)
            ledger.record(trade)
            return Execution(trade, "")
        # Verkauf
        held = ledger.qty(symbol)
        if held <= 0:
            return Execution(None, f"{symbol}: kein Bestand, Verkauf übersprungen")
        close_all = decision.target == 0.0
        if price is None or price <= 0:
            price = ledger.price_for(symbol, None)
            if price is None:
                return Execution(None, f"{symbol}: kein Kurs für die Glattstellung")
            close_all = True
        fill_price = price * (1.0 - self.slippage_rate)
        if close_all:
            qty = held
        else:
            qty = min(held, floor_quantity(abs(decision.delta) / fill_price, precision))
        value = qty * fill_price
        if not close_all and (qty <= 0 or value + 1e-9 < minimum):
            return Execution(
                None,
                f"{symbol}: Verkauf {abs(decision.delta):.2f} USDT unter Mindestorder {minimum:g} USDT nach Rundung, übersprungen",
            )
        fee = value * self.fee_rate
        trade = SpotTrade(ts_ms, symbol, "sell", qty, fill_price, fee, value, decision.reason)
        ledger.record(trade)
        return Execution(trade, "")
