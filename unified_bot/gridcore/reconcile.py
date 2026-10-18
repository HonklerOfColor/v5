"""Start-Abgleich: lokale Orders gegen die Börse, ohne fremde Positionen anzufassen."""

from __future__ import annotations

from unified_bot.gridcore.engine import ActiveGrid, RestingOrder


def position_mismatch(grid: ActiveGrid, exchange_long: float, exchange_short: float, step: float) -> bool:
    tol = max(step * 0.5, 1e-12)
    return abs(grid.long_qty - exchange_long) > tol or abs(grid.short_qty - exchange_short) > tol


def absorb_exchange_order(grid: ActiveGrid, order: RestingOrder, detail: dict, maker_fee: float) -> str:
    """Verarbeitet eine lokale Order, die nicht mehr unverändert offen ist.

    detail: state, filled (kumuliert), avg.
    """
    state = str(detail.get("state", "")).lower()
    filled = float(detail.get("filled") or 0)
    avg = float(detail.get("avg") or order.price or 0)
    delta = filled - order.filled_ack
    if delta > 1e-12 and avg > 0:
        order.filled_ack += delta
        grid.apply_fill(order, avg, delta, maker_fee)
    still_open = order.client_oid in grid.orders
    if state in ("live", "new", "partially_filled", "init", "not_filled"):
        if delta > 0 and not still_open:
            return "filled"
        return "partial" if delta > 0 else "resting"
    if not still_open:
        return "filled"
    if state in ("canceled", "cancelled", "expired"):
        grid.orders.pop(order.client_oid, None)
        return "canceled"
    grid.orders.pop(order.client_oid, None)
    return "dropped"
