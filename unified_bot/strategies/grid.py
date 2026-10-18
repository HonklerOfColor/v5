"""Grid auf dem gemeinsamen Konto. Dieselbe Engine wie der alte Grid-Bot."""

from __future__ import annotations

from unified_bot.gridcore.engine import ActiveGrid, RestingOrder, build_plan
from unified_bot.gridcore.params import GridParams
from unified_bot.gridcore.regime import assess
from unified_bot.market import CycleContext
from unified_bot.models import CancelIntent, CyclePlan, Fill, OrderIntent

HOUR_MS = 3_600_000


class GridStrategy:
    id = "grid"

    def __init__(self, settings):
        self.settings = settings.strategy(self.id)
        self.account = settings
        self.params = _params(settings)
        self.grids: dict[str, ActiveGrid] = {}
        self.cooldown_until_ms: dict[str, int] = {}

    def plan(self, ctx: CycleContext) -> CyclePlan:
        plan = CyclePlan()
        allow_open = self.settings.enabled and not self.settings.entries_paused and ctx.entries_allowed
        for symbol in list(self.grids):
            self._manage_grid(ctx, plan, symbol, allow_open)
        if self.grids or not allow_open:
            if not allow_open and not self.grids:
                plan.notes.append("grid: keine neuen Grids")
            return plan
        if len(self.grids) >= int(self.params.max_active_grids):
            return plan
        for symbol in self.settings.symbols:
            if self._try_open(ctx, plan, symbol):
                break
        return plan

    def consume_fill(self, fill: Fill, book) -> None:
        grid = self.grids.get(fill.symbol)
        if grid is None:
            return
        if fill.purpose == "open":
            order = grid.orders.get(fill.client_oid)
            if order is None:
                order = RestingOrder(
                    client_oid=fill.client_oid,
                    order_id=None,
                    level=int(fill.reason.split(":")[-1]) if ":" in (fill.reason or "") else 0,
                    book_side=fill.book_side,
                    position_side=fill.position_side,
                    purpose="open",
                    price=fill.price,
                    size=fill.qty,
                )
                grid.orders[order.client_oid] = order
            grid.apply_fill(order, fill.price, fill.qty, fill.fee_rate)
        else:
            order = grid.orders.get(fill.client_oid)
            if order is not None and fill.purpose == "close":
                # Regulärer TP: die Engine schließt genau die Lots dieser Stufe.
                grid.apply_fill(order, fill.price, fill.qty, fill.fee_rate)
            else:
                grid.close_qty(fill.position_side, fill.price, fill.qty, fill.fee_rate)
                grid.orders.pop(fill.client_oid, None)
        self._retire_if_flat(grid, fill.symbol, fill.ts_ms, fill.purpose)

    def _retire_if_flat(self, grid: ActiveGrid, symbol: str, ts_ms: int, purpose: str) -> None:
        if purpose == "open":
            return
        if grid.long_qty > 1e-8 or grid.short_qty > 1e-8 or grid.orders:
            return
        self.cooldown_until_ms[symbol] = ts_ms + self.params.cooldown_bars * HOUR_MS
        self.grids.pop(symbol, None)

    def on_reject(self, intent: OrderIntent, reason: str) -> None:
        grid = self.grids.get(intent.symbol)
        if grid is not None and intent.client_oid:
            grid.orders.pop(intent.client_oid, None)

    def on_funding(self, book, symbol: str, mark: float, rate: float) -> None:
        grid = self.grids.get(symbol)
        if grid is None or mark <= 0 or rate <= 0:
            return
        before = grid.funding
        grid.charge_funding(mark, rate)
        book.note_funding(self.id, symbol, grid.funding - before)

    def export_state(self) -> dict:
        return {
            "grids": {symbol: grid.to_dict() for symbol, grid in self.grids.items()},
            "cooldown_until_ms": self.cooldown_until_ms,
        }

    def load_state(self, raw: dict) -> None:
        self.grids = {}
        for symbol, body in (raw.get("grids") or {}).items():
            self.grids[symbol] = ActiveGrid.from_dict(body)
        self.cooldown_until_ms = {
            str(k): int(v) for k, v in (raw.get("cooldown_until_ms") or {}).items()
        }

    def _manage_grid(self, ctx: CycleContext, plan: CyclePlan, symbol: str, allow_open: bool) -> None:
        grid = self.grids[symbol]
        view = ctx.views.get(symbol)
        if view is None or view.spec is None or view.last <= 0:
            plan.notes.append(f"{symbol}: keine Marktdaten, Grid bleibt")
            return
        mark = view.last
        reason = ""
        if grid.outside(mark, self.params.breakout_buffer_pct):
            reason = "breakout"
        elif grid.net_pnl(mark) <= -grid.hard_stop_usdt:
            reason = "hard_stop"
        elif view.candles and not assess(view.candles, None, self.params).ranging:
            reason = "regime"
        if reason:
            self._queue_flatten(plan, grid, reason)
            # Ohne Lage gibt es keinen Fill, der das Grid später abräumt.
            self._retire_if_flat(grid, symbol, ctx.now_ms, "emergency")
            return
        cancelled = grid.sync_orders(mark, ctx.sleeve_equity, view.spec, self.params)
        known = ctx.known_order_ids()
        for order in cancelled:
            if order.client_oid in known:
                plan.cancels.append(CancelIntent(self.id, symbol, order.client_oid, order.order_id))
        for order in list(grid.orders.values()):
            if order.client_oid in known:
                continue
            if order.purpose == "open" and not allow_open:
                grid.orders.pop(order.client_oid, None)
                continue
            plan.orders.append(_from_resting(grid, order))

    def _try_open(self, ctx: CycleContext, plan: CyclePlan, symbol: str) -> bool:
        if ctx.now_ms < self.cooldown_until_ms.get(symbol, 0):
            plan.notes.append(f"{symbol}: Cooldown")
            return False
        if symbol in ctx.frozen:
            plan.notes.append(f"{symbol}: eingefroren")
            return False
        view = ctx.views.get(symbol)
        if view is None or view.spec is None or view.error:
            plan.notes.append(f"{symbol}: {view.error if view else 'keine Daten'}")
            return False
        if len(view.candles) < self.params.min_bars_1h:
            plan.notes.append(f"{symbol}: zu wenig Kerzen")
            return False
        regime = assess(view.candles, None, self.params)
        if not regime.ranging:
            plan.notes.append(f"{symbol}: {regime.reason_text()}")
            return False
        built, why = build_plan(
            view.candles,
            view.spec,
            ctx.sleeve_equity,
            self.params,
            min(self.settings.leverage, self.params.max_leverage),
        )
        if built is None:
            plan.notes.append(f"{symbol}: {why}")
            return False
        # Die Engine lässt 2 % Toleranz zu. Der Risiko-Manager prüft strikt das Dreifache der Fee.
        if built.spacing_pct + 1e-12 < self.params.min_spacing_pct:
            plan.notes.append(f"{symbol}: abstand_unter_fee")
            return False
        grid = ActiveGrid.from_plan(built, created_ms=ctx.now_ms)
        self.grids[symbol] = grid
        grid.sync_orders(view.last, ctx.sleeve_equity, view.spec, self.params)
        for order in grid.orders.values():
            plan.orders.append(_from_resting(grid, order))
        plan.notes.append(f"{symbol}: Grid auf ({len(grid.levels)} Levels)")
        return True

    def _queue_flatten(self, plan: CyclePlan, grid: ActiveGrid, reason: str) -> None:
        for order in list(grid.orders.values()):
            plan.cancels.append(CancelIntent(self.id, grid.symbol, order.client_oid, order.order_id))
        grid.orders.clear()
        for intent in grid.emergency_intents():
            plan.orders.append(
                OrderIntent(
                    strategy_id=self.id,
                    symbol=grid.symbol,
                    market="perp",
                    book_side=intent.book_side,
                    position_side=intent.position_side,
                    purpose="emergency",
                    order_type="market",
                    size=intent.size,
                    leverage=grid.leverage,
                    post_only=False,
                    client_oid=intent.client_oid,
                    exit_is_maker=False,
                    reason=reason,
                )
            )


def _from_resting(grid: ActiveGrid, order: RestingOrder) -> OrderIntent:
    return OrderIntent(
        strategy_id="grid",
        symbol=grid.symbol,
        market="perp",
        book_side=order.book_side,
        position_side=order.position_side,
        purpose=order.purpose,
        order_type="limit",
        size=order.size,
        price=order.price,
        leverage=grid.leverage,
        post_only=True,
        client_oid=order.client_oid,
        expected_tp_pct=grid.spacing_pct if order.purpose == "open" else None,
        exit_is_maker=True,
        reason=f"grid:{order.level}",
    )


def _params(settings) -> GridParams:
    raw = settings.grid
    grid = settings.strategy("grid")
    base = GridParams()
    return GridParams(
        maker_fee=settings.maker_fee,
        taker_fee=settings.taker_fee,
        fee_spacing_mult=float(raw.get("fee_spacing_mult", base.fee_spacing_mult)),
        funding_rate_8h=settings.funding_rate_8h,
        adx_max_1h=float(raw.get("adx_max_1h", base.adx_max_1h)),
        adx_max_4h=float(raw.get("adx_max_4h", base.adx_max_4h)),
        grid_levels=int(raw.get("grid_levels", base.grid_levels)),
        min_grid_levels=int(raw.get("min_grid_levels", base.min_grid_levels)),
        leverage=grid.leverage,
        max_leverage=grid.max_leverage,
        max_margin_fraction=float(raw.get("max_margin_fraction", base.max_margin_fraction)),
        max_inventory_levels=int(raw.get("max_inventory_levels", base.max_inventory_levels)),
        level_notional_fraction=float(raw.get("level_notional_fraction", base.level_notional_fraction)),
        breakout_buffer_pct=float(raw.get("breakout_buffer_pct", base.breakout_buffer_pct)),
        hard_stop_pct=float(raw.get("hard_stop_pct", base.hard_stop_pct)),
        daily_loss_pct=settings.daily_loss_pct,
        taker_slippage_pct=settings.taker_slippage_pct,
        cooldown_bars=int(raw.get("cooldown_bars", base.cooldown_bars)),
        max_active_grids=int(raw.get("max_active_grids", base.max_active_grids)),
        paper_equity=settings.paper_equity,
        pos_mode=settings.pos_mode,
        product_type=settings.product_type,
        margin_mode=settings.margin_mode,
        margin_coin=settings.margin_coin,
    )
