"""Bitget-Orderpayloads.

Hedge-Modus (Konto-Default, wie V2): `side` ist die Positionsrichtung, nicht
die Orderbuch-Seite. Close-Long ist side=buy + tradeSide=close. Das ist der
Reduce-only-Exit. `reduceOnly` schickt Bitget nur im One-Way-Modus (dort YES).

Belegt durch die aktuelle Place-Order-Doku und durch CCXT (hedge + reduceOnly
dreht die Orderbuch-Seite und setzt tradeSide=Close).
"""

from __future__ import annotations

from dataclasses import dataclass

from unified_bot.gridcore.specs import ContractSpec, format_number


@dataclass
class Intent:
    symbol: str
    book_side: str  # buy | sell auf dem Orderbuch
    purpose: str  # open | close | emergency
    position_side: str  # long | short
    level: int
    price: float | None
    size: float
    order_type: str  # limit | market
    client_oid: str

    @property
    def reduce_only(self) -> bool:
        return self.purpose in ("close", "emergency")


def api_fields(intent: Intent, pos_mode: str) -> dict:
    """Liefert side / tradeSide / reduceOnly passend zum Positionsmodus."""
    if pos_mode == "one_way":
        fields = {
            "side": intent.book_side,
            "reduceOnly": "YES" if intent.reduce_only else "NO",
        }
        return fields
    if pos_mode != "hedge":
        raise ValueError(f"unbekannter POS_MODE: {pos_mode}")
    if intent.reduce_only:
        # Orderbuch-Sell schließt ein Long → API-Seite buy (Positionsrichtung).
        side = "buy" if intent.book_side == "sell" else "sell"
        return {"side": side, "tradeSide": "close"}
    return {"side": intent.book_side, "tradeSide": "open"}


def build_payload(
    intent: Intent,
    spec: ContractSpec,
    pos_mode: str,
    product_type: str,
    margin_mode: str,
    margin_coin: str,
) -> dict:
    size = format_number(intent.size, spec.qty_place)
    payload: dict = {
        "symbol": intent.symbol,
        "productType": product_type,
        "marginMode": margin_mode,
        "marginCoin": margin_coin,
        "size": size,
        "orderType": intent.order_type,
        "clientOid": intent.client_oid,
    }
    payload.update(api_fields(intent, pos_mode))
    if intent.order_type == "limit":
        if intent.price is None:
            raise ValueError("Limit-Order ohne Preis")
        payload["price"] = format_number(intent.price, spec.price_place)
        payload["force"] = "post_only"
    elif intent.order_type == "market":
        payload["force"] = "ioc"
    else:
        raise ValueError(f"unbekannter orderType: {intent.order_type}")
    return payload
