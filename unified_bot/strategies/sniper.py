"""V3 Sniper. Signal ist portiert, Entries sind standardmäßig pausiert."""

from __future__ import annotations

from unified_bot.gridcore.indicators import atr
from unified_bot.market import CycleContext
from unified_bot.models import CyclePlan, OrderIntent
from unified_bot.sizing import floor_size
from unified_bot.strategies.reversal import _market_close
from unified_bot.strategies.sniper_rules import (
    LEVERAGE,
    MAX_POSITIONS,
    SL_ATR_MULT,
    TP_ATR_MULT,
    entry_hour_blocked,
    sniper_side,
    trend_from_closes,
    update_sweep,
)


class SniperStrategy:
    id = "sniper"

    def __init__(self, settings):
        self.settings = settings.strategy(self.id)
        self.sweep_state: dict[str, dict] = {}

    def plan(self, ctx: CycleContext) -> CyclePlan:
        plan = CyclePlan()
        self._manage(ctx, plan)
        if not self.settings.enabled or self.settings.entries_paused or not ctx.entries_allowed:
            plan.notes.append("sniper: ENTRIES_PAUSED (kein Edge nach Fees)")
            return plan
        if len(ctx.positions) >= min(self.settings.max_positions, MAX_POSITIONS):
            plan.notes.append("sniper: max Positionen")
            return plan
        for symbol in self.settings.symbols:
            self._maybe_entry(ctx, plan, symbol)
        return plan

    def consume_fill(self, fill, book) -> None:
        return None

    def on_reject(self, intent: OrderIntent, reason: str) -> None:
        return None

    def export_state(self) -> dict:
        return {"sweep_state": self.sweep_state}

    def load_state(self, raw: dict) -> None:
        self.sweep_state = dict(raw.get("sweep_state") or {})

    def _manage(self, ctx: CycleContext, plan: CyclePlan) -> None:
        for pos in ctx.positions:
            view = ctx.views.get(pos.symbol)
            if view is None or view.last <= 0 or pos.stop is None:
                continue
            hit = (pos.side == "long" and view.last <= pos.stop) or (
                pos.side == "short" and view.last >= pos.stop
            )
            if hit:
                plan.orders.append(_market_close(pos, "sl"))
                continue
            if pos.take_profit is None:
                continue
            reached = (pos.side == "long" and view.last >= pos.take_profit) or (
                pos.side == "short" and view.last <= pos.take_profit
            )
            if reached:
                plan.orders.append(_market_close(pos, "tp"))

    def _maybe_entry(self, ctx: CycleContext, plan: CyclePlan, symbol: str) -> None:
        if any(pos.symbol == symbol for pos in ctx.positions):
            return
        if any(order.symbol == symbol for order in ctx.orders):
            return
        view = ctx.views.get(symbol)
        if view is None or view.spec is None or not view.candles:
            return
        bids = view.bids or []
        asks = view.asks or []
        if not bids or not asks:
            plan.notes.append(f"{symbol}: kein Orderbuch")
            return
        from unified_bot.strategies.sniper_rules import imbalance_ratio

        ratio = imbalance_ratio(bids, asks, 10)
        closes = [candle.close for candle in view.candles]
        trend = trend_from_closes(closes)
        state, sweep = update_sweep(
            self.sweep_state.get(symbol, {}),
            float(bids[0][0]),
            float(asks[0][0]),
            view.last,
            ctx.now_ms / 1000,
        )
        self.sweep_state[symbol] = state
        side = sniper_side(ratio, trend, sweep, entry_hour_blocked(ctx.now_ms / 1000))
        if side is None:
            return
        atr_value = atr(view.candles, 14)
        if not atr_value:
            return
        price = float(bids[0][0]) if side == "long" else float(asks[0][0])
        if side == "long":
            sl = price - SL_ATR_MULT * atr_value
            tp = price + TP_ATR_MULT * atr_value
            book_side = "buy"
        else:
            sl = price + SL_ATR_MULT * atr_value
            tp = price - TP_ATR_MULT * atr_value
            book_side = "sell"
        risk_pct = self.settings.risk_pct or 0.003
        risk_dist = abs(price - sl)
        if risk_dist <= 0 or ctx.sleeve_equity <= 0:
            return
        raw = (ctx.sleeve_equity * risk_pct * self.settings.leverage) / risk_dist
        size = floor_size(raw, view.spec.qty_step)
        plan.orders.append(
            OrderIntent(
                strategy_id=self.id,
                symbol=symbol,
                market="perp",
                book_side=book_side,
                position_side=side,
                purpose="open",
                order_type="limit",
                size=size,
                price=price,
                leverage=min(self.settings.leverage, LEVERAGE),
                post_only=True,
                stop=sl,
                take_profit=tp,
                exit_is_maker=False,
                reason="sniper_long" if side == "long" else "sniper_short",
            )
        )
