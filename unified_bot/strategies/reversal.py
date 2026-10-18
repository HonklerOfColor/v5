"""V1 Reversal (Spread-Scalper, Long-only). Portiert, standardmäßig aus."""

from __future__ import annotations

from unified_bot.gridcore.indicators import atr
from unified_bot.market import CycleContext
from unified_bot.models import CancelIntent, CyclePlan, OrderIntent, Position, StopUpdate
from unified_bot.sizing import floor_size
from unified_bot.strategies.reversal_rules import (
    LEVERAGE,
    MAX_FUNDING_RATE,
    MAX_SPREAD_PCT,
    SL_ATR_FALLBACK,
    SL_MIN_ATR,
    TP_ATR_MULT,
    entry_hour_blocked,
    reversal_long_signal,
    should_arm_breakeven,
    time_stop_due,
    unrealized_roe_pct,
)


class ReversalStrategy:
    id = "reversal"

    def __init__(self, settings):
        self.settings = settings.strategy(self.id)
        self.pending_since: dict[str, int] = {}

    def plan(self, ctx: CycleContext) -> CyclePlan:
        plan = CyclePlan()
        if not self.settings.enabled and not ctx.positions:
            plan.notes.append("reversal aus (kein Edge im Backtest)")
            return plan
        self._manage(ctx, plan)
        if not self.settings.enabled or self.settings.entries_paused or not ctx.entries_allowed:
            plan.notes.append("reversal: keine neuen Entries")
            return plan
        for symbol in self.settings.symbols:
            self._maybe_entry(ctx, plan, symbol)
        return plan

    def consume_fill(self, fill, book) -> None:
        return None

    def on_reject(self, intent: OrderIntent, reason: str) -> None:
        return None

    def export_state(self) -> dict:
        return {"pending_since": self.pending_since}

    def load_state(self, raw: dict) -> None:
        self.pending_since = {str(k): int(v) for k, v in (raw.get("pending_since") or {}).items()}

    def _manage(self, ctx: CycleContext, plan: CyclePlan) -> None:
        for pos in ctx.positions:
            if pos.side != "long":
                continue
            view = ctx.views.get(pos.symbol)
            mark = view.last if view and view.last > 0 else 0.0
            age_h = (ctx.now_ms - pos.opened_ms) / 3_600_000
            pnl = (mark - pos.entry) * pos.qty if mark > 0 else 0.0
            if mark > 0 and time_stop_due(age_h, pnl, pos.qty, mark, pos.leverage or LEVERAGE):
                plan.orders.append(_market_close(pos, "time_stop"))
                continue
            roe = unrealized_roe_pct(pnl, pos.qty, mark, pos.leverage or LEVERAGE)
            if roe is None:
                continue
            peak = max(pos.peak_roe, roe)
            pos.peak_roe = peak
            if pos.breakeven_armed or not should_arm_breakeven(age_h, roe, peak):
                continue
            if mark <= 0 or (mark - pos.entry) / mark < 0.0015:
                continue
            if pos.stop is not None and pos.stop >= pos.entry:
                continue
            plan.stops.append(
                StopUpdate(self.id, pos.symbol, pos.side, pos.entry, "breakeven_12h")
            )

        resting = {order.symbol: order for order in ctx.orders if order.purpose == "open"}
        for symbol, order in resting.items():
            if ctx.now_ms - order.placed_ms >= 60_000:
                plan.cancels.append(
                    CancelIntent(self.id, symbol, order.client_oid, order.order_id)
                )

    def _maybe_entry(self, ctx: CycleContext, plan: CyclePlan, symbol: str) -> None:
        if any(pos.symbol == symbol for pos in ctx.positions):
            return
        if any(order.symbol == symbol and order.purpose == "open" for order in ctx.orders):
            return
        if symbol in ctx.frozen:
            plan.notes.append(f"{symbol}: eingefroren")
            return
        view = ctx.views.get(symbol)
        if view is None or view.spec is None or view.error:
            plan.notes.append(f"{symbol}: {view.error if view else 'keine Daten'}")
            return
        if entry_hour_blocked(ctx.now_ms / 1000):
            plan.notes.append(f"{symbol}: Verluststunde Europe/Vienna")
            return
        if len(view.candles) < 20:
            plan.notes.append(f"{symbol}: zu wenig Kerzen")
            return
        prev, last = view.candles[-2], view.candles[-1]
        if not reversal_long_signal(prev.open, prev.close, last.open, last.close):
            return
        if view.funding_rate is None:
            plan.notes.append(f"{symbol}: kein Funding")
            return
        if view.funding_rate < -MAX_FUNDING_RATE:
            plan.notes.append(f"{symbol}: Funding zu negativ")
            return
        if view.bid <= 0 or view.ask <= 0 or view.ask <= view.bid:
            plan.notes.append(f"{symbol}: kein Spread")
            return
        spread_pct = (view.ask - view.bid) / view.mid
        if spread_pct > MAX_SPREAD_PCT:
            plan.notes.append(f"{symbol}: Spread zu weit")
            return
        atr_value = atr(view.candles, 14)
        if not atr_value or atr_value <= 0:
            plan.notes.append(f"{symbol}: kein ATR")
            return
        entry = view.bid
        sl = _chart_sl(view.candles, entry, atr_value)
        tp = entry + atr_value * TP_ATR_MULT
        size = _min_order_size(entry, view.spec)
        if size <= 0:
            plan.notes.append(f"{symbol}: unter Mindestgröße, nicht aufgerundet")
            return
        plan.orders.append(
            OrderIntent(
                strategy_id=self.id,
                symbol=symbol,
                market="perp",
                book_side="buy",
                position_side="long",
                purpose="open",
                order_type="limit",
                size=size,
                price=entry,
                leverage=min(self.settings.leverage, LEVERAGE),
                post_only=True,
                stop=sl,
                take_profit=tp,
                exit_is_maker=False,
                reason="reversal_long",
            )
        )


def _chart_sl(candles, entry: float, atr_value: float) -> float:
    window = candles[-20:]
    lowest = min(candle.low for candle in window)
    sl = lowest * 0.999
    if sl > entry - atr_value * SL_MIN_ATR:
        sl = entry - atr_value * SL_MIN_ATR
    if sl >= entry:
        sl = entry - atr_value * SL_ATR_FALLBACK
    return sl


def _min_order_size(price: float, spec) -> float:
    if price <= 0:
        return 0.0
    raw = max(spec.min_qty, spec.min_notional / price)
    size = floor_size(raw, spec.qty_step)
    if size + 1e-12 < spec.min_qty:
        return 0.0
    if size * price + 1e-9 < spec.min_notional:
        return 0.0
    return size


def _market_close(pos: Position, reason: str) -> OrderIntent:
    return OrderIntent(
        strategy_id=pos.strategy_id,
        symbol=pos.symbol,
        market=pos.market,
        book_side="sell" if pos.side == "long" else "buy",
        position_side=pos.side,
        purpose="close",
        order_type="market",
        size=pos.qty,
        leverage=pos.leverage,
        post_only=False,
        reason=reason,
    )
