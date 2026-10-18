"""Start-Abgleich über die clientOid-Vorsilbe. Fremde Orders bleiben liegen."""

from __future__ import annotations

from unified_bot.book import Book
from unified_bot.ids import owner_of
from unified_bot.models import Fill


def reconcile(book: Book, broker, specs: dict, maker_fee: float, ts_ms: int) -> list[str]:
    notes: list[str] = []
    remote = broker.list_open_orders()
    remote_ids = {str(row.get("clientOid") or "") for row in remote}
    for row in remote:
        oid = str(row.get("clientOid") or "")
        owner = owner_of(oid)
        if owner is None:
            notes.append(f"fremd {row.get('symbol')} {oid or row.get('orderId')} nicht angefasst")
            continue
        if oid not in book.orders:
            broker.cancel(str(row.get("symbol") or ""), oid, row.get("orderId"))
            notes.append(f"verwaist {oid} storniert ({owner})")
            continue
        if row.get("orderId"):
            book.orders[oid].order_id = str(row["orderId"])

    for oid, order in list(book.orders.items()):
        if oid in remote_ids:
            continue
        detail = broker.get_order(order.symbol, oid) or {}
        state = str(detail.get("state") or "").lower()
        filled = float(detail.get("filled") or 0)
        avg = float(detail.get("avg") or order.price or 0)
        delta = filled - order.filled
        if delta > 1e-12 and avg > 0 and state in ("filled", "partially_filled", "full_fill"):
            fee = avg * delta * maker_fee
            book.apply_fill(
                Fill(
                    strategy_id=order.strategy_id,
                    client_oid=oid,
                    symbol=order.symbol,
                    book_side=order.book_side,
                    position_side=order.position_side,
                    purpose=order.purpose,
                    price=avg,
                    qty=delta,
                    fee=fee,
                    fee_rate=maker_fee,
                    liquidity="maker",
                    ts_ms=ts_ms,
                    leverage=order.leverage,
                    reason=order.reason or "reconcile_fill",
                    market=order.market,
                )
            )
            notes.append(f"fill übernommen {oid}")
            continue
        if state in ("canceled", "cancelled", "expired") or not detail:
            book.drop_order(oid)
            notes.append(f"lokal verworfen {oid} ({state or 'weg'})")

    local_qty: dict[tuple[str, str], float] = {}
    for pos in book.positions:
        if pos.qty <= 0:
            continue
        key = (pos.symbol, pos.side)
        local_qty[key] = local_qty.get(key, 0.0) + pos.qty

    exchange_qty: dict[tuple[str, str], float] = {}
    for row in broker.list_positions():
        symbol = str(row.get("symbol") or "")
        side = str(row.get("side") or "")
        qty = float(row.get("qty") or 0)
        if not symbol or qty <= 0:
            continue
        exchange_qty[(symbol, side)] = exchange_qty.get((symbol, side), 0.0) + qty

    symbols = {symbol for symbol, _side in local_qty} | {symbol for symbol, _side in exchange_qty}
    for symbol in symbols:
        spec = specs.get(symbol)
        step = spec.qty_step if spec is not None else 1e-8
        tol = max(step * 0.5, 1e-8)
        for side in ("long", "short"):
            local = local_qty.get((symbol, side), 0.0)
            remote_qty = exchange_qty.get((symbol, side), 0.0)
            if abs(local - remote_qty) <= tol:
                continue
            owner = book.symbol_owner(symbol)
            if local <= tol and owner is None:
                notes.append(f"{symbol} {side}: fremde Lage {remote_qty}, eingefroren, nicht angefasst")
            else:
                notes.append(
                    f"{symbol} {side}: Lage weicht ab, lokal {local}, Börse {remote_qty}. Symbol eingefroren."
                )
            book.locks[symbol] = owner or "__exchange__"
    return notes
