"""Eine Order-Tür. Hedge-Felder, Post-only, clientOid, und die Risiko-Entscheidung davor."""

from __future__ import annotations

from unified_bot.book import Book
from unified_bot.gridcore.specs import ContractSpec, format_number, snap_price
from unified_bot.ids import make_client_oid, owner_of
from unified_bot.models import Fill, OrderIntent, SubmitResult, WorkingOrder
from unified_bot.risk import RiskManager
from unified_bot.settings import Settings


def build_perp_payload(
    intent: OrderIntent,
    spec: ContractSpec,
    pos_mode: str,
    product_type: str,
    margin_mode: str,
    margin_coin: str,
) -> dict:
    """Hedge: `side` ist die Positionsrichtung. Close-Long ist side=buy, tradeSide=close."""
    if pos_mode != "hedge":
        raise ValueError("nur hedge wird gebaut")
    size = format_number(intent.size, spec.qty_place)
    if intent.reduce_only:
        side = "buy" if intent.book_side == "sell" else "sell"
        fields = {"side": side, "tradeSide": "close"}
    else:
        fields = {"side": intent.book_side, "tradeSide": "open"}
    payload: dict = {
        "symbol": intent.symbol,
        "productType": product_type,
        "marginMode": margin_mode,
        "marginCoin": margin_coin,
        "size": size,
        "orderType": intent.order_type,
        "clientOid": intent.client_oid,
    }
    payload.update(fields)
    if intent.order_type == "limit":
        if intent.price is None:
            raise ValueError("Limit-Order ohne Preis")
        payload["price"] = format_number(intent.price, spec.price_place)
        payload["force"] = "post_only" if intent.wants_post_only else "gtc"
    elif intent.order_type == "market":
        payload["force"] = "ioc"
    else:
        raise ValueError(f"unbekannter orderType: {intent.order_type}")
    return payload


def build_spot_payload(intent: OrderIntent, spec: ContractSpec) -> dict:
    """Spot-Skelett für den Funding-Slot. Der Loop schickt das nicht."""
    if intent.price is None:
        raise ValueError("Spot-Limit ohne Preis")
    return {
        "symbol": intent.symbol,
        "side": intent.book_side,
        "orderType": intent.order_type,
        "force": "post_only" if intent.wants_post_only else "gtc",
        "price": format_number(intent.price, spec.price_place),
        "size": format_number(intent.size, spec.qty_place),
        "clientOid": intent.client_oid,
    }


class OrderManager:
    def __init__(self, settings: Settings, risk: RiskManager, book: Book, broker):
        self.settings = settings
        self.risk = risk
        self.book = book
        self.broker = broker

    def submit(
        self,
        intent: OrderIntent,
        spec: ContractSpec,
        *,
        mark: float,
        bid: float = 0.0,
        ask: float = 0.0,
        ts_ms: int = 0,
    ) -> SubmitResult:
        if intent.market == "spot":
            return SubmitResult(False, "spot_not_enabled")
        if not intent.client_oid:
            intent.client_oid = make_client_oid(intent.strategy_id, self.book.next_seq(intent.strategy_id))
        tagged = owner_of(intent.client_oid)
        if tagged != intent.strategy_id:
            return SubmitResult(False, "client_oid_prefix", client_oid=intent.client_oid)
        if intent.client_oid in self.book.orders:
            return SubmitResult(False, "duplicate_order", client_oid=intent.client_oid)

        if intent.purpose == "open":
            owner = self.book.symbol_owner(intent.symbol)
            if owner is not None and owner != intent.strategy_id:
                return SubmitResult(False, "symbol_locked", client_oid=intent.client_oid)
            strategy = self.settings.strategy(intent.strategy_id)
            decision = self.risk.evaluate_open(
                intent,
                spec,
                strategy,
                sleeve_free_margin=self.book.free_margin(intent.strategy_id, {intent.symbol: mark}),
                account_equity=self.book.account_equity({intent.symbol: mark}),
                open_notional=self.book.open_notional({intent.symbol: mark}),
                mark=mark,
            )
            if not decision.allow:
                return SubmitResult(False, decision.reason, client_oid=intent.client_oid)
            intent.size = decision.size
        else:
            pos = self.book.find_position(intent.strategy_id, intent.symbol, intent.position_side)
            if pos is None or pos.qty <= 0:
                return SubmitResult(False, "nothing_to_close", client_oid=intent.client_oid)
            if intent.size > pos.qty + 1e-9:
                intent.size = pos.qty
            if spec.qty_step > 0:
                from unified_bot.sizing import floor_size

                intent.size = floor_size(intent.size, spec.qty_step)
            if intent.size <= 0:
                return SubmitResult(False, "below_min_size", client_oid=intent.client_oid)

        if intent.order_type == "limit" and intent.price is not None and spec.price_tick > 0:
            intent.price = snap_price(intent.price, spec.price_tick)
        if intent.wants_post_only and intent.price is not None and bid > 0 and ask > 0:
            if intent.book_side == "buy" and intent.price >= ask:
                return SubmitResult(False, "would_cross", client_oid=intent.client_oid)
            if intent.book_side == "sell" and intent.price <= bid:
                return SubmitResult(False, "would_cross", client_oid=intent.client_oid)

        try:
            payload = build_perp_payload(
                intent,
                spec,
                self.settings.pos_mode,
                self.settings.product_type,
                self.settings.margin_mode,
                self.settings.margin_coin,
            )
        except ValueError as exc:
            return SubmitResult(False, str(exc), client_oid=intent.client_oid)

        response = self.broker.place(intent, payload, mark=mark)
        if str(response.get("code")) != "00000":
            return SubmitResult(False, str(response.get("msg") or "rejected"), client_oid=intent.client_oid, payload=payload)
        data = response.get("data") or {}
        order_id = data.get("orderId")
        working = WorkingOrder(
            strategy_id=intent.strategy_id,
            client_oid=intent.client_oid,
            order_id=str(order_id) if order_id else None,
            symbol=intent.symbol,
            market=intent.market,
            book_side=intent.book_side,
            position_side=intent.position_side,
            purpose=intent.purpose,
            order_type=intent.order_type,
            price=intent.price,
            size=intent.size,
            filled=0.0,
            leverage=intent.leverage,
            post_only=intent.wants_post_only,
            placed_ms=ts_ms,
            stop=intent.stop,
            take_profit=intent.take_profit,
            expected_tp_pct=intent.expected_tp_pct,
            reason=intent.reason,
            meta=dict(intent.meta),
        )
        state = str(data.get("state") or "live").lower()
        if state == "filled":
            price = float(data.get("fillPrice") or mark)
            qty = float(data.get("fillQty") or intent.size)
            fee_rate = self.settings.taker_fee if intent.order_type == "market" else self.settings.maker_fee
            fill = Fill(
                strategy_id=intent.strategy_id,
                client_oid=intent.client_oid,
                symbol=intent.symbol,
                book_side=intent.book_side,
                position_side=intent.position_side,
                purpose=intent.purpose,
                price=price,
                qty=qty,
                fee=price * qty * fee_rate,
                fee_rate=fee_rate,
                liquidity="taker" if intent.order_type == "market" else "maker",
                ts_ms=ts_ms,
                leverage=intent.leverage,
                reason=intent.reason or intent.purpose,
                market=intent.market,
            )
            # Schutzlevels müssen vor dem Fill am Order hängen.
            self.book.add_order(working)
            self.book.apply_fill(fill)
            self.book.remember_protection(
                intent.strategy_id, intent.symbol, intent.position_side, intent.stop, intent.take_profit
            )
            return SubmitResult(True, "filled", client_oid=intent.client_oid, payload=payload, fill=fill)
        self.book.add_order(working)
        return SubmitResult(True, "live", client_oid=intent.client_oid, payload=payload)

    def cancel(self, symbol: str, client_oid: str, order_id: str | None = None) -> bool:
        response = self.broker.cancel(symbol, client_oid, order_id)
        self.book.drop_order(client_oid)
        return str(response.get("code", "00000")) in ("00000", "ok")
