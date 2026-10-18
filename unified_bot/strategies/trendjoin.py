"""V4 TrendJoin.

bitget_bot_v4 ist leer. Die Risikoregeln sind ausführbar, das Momentum-Signal nicht.
TODO: detect_breakout ersetzen, sobald der Quell-Repo Code hat.
"""

from __future__ import annotations

from unified_bot.market import CycleContext
from unified_bot.models import CyclePlan, OrderIntent, Position, StopUpdate
from unified_bot.sizing import floor_size
from unified_bot.strategies.reversal import _market_close

LEVERAGE = 5
RISK_PCT = 0.01
MAX_POSITIONS = 3
MAX_TRADES_PER_DAY = 5
REENTRY_COOLDOWN_MS = 24 * 3_600_000
TIME_STOP_MS = 24 * 3_600_000
BREAKEVEN_MS = 12 * 3_600_000
PARTIAL_R = 0.75
PARTIAL_FRACTION = 1.0 / 3.0
LONG_ONLY = True


class BreakoutSignal:
    """Platzhalter. Wird erst befüllt, wenn V4 Code da ist."""

    def __init__(self, symbol: str, entry: float, stop: float, take_profit: float):
        self.symbol = symbol
        self.entry = entry
        self.stop = stop
        self.take_profit = take_profit


class TrendJoinStrategy:
    id = "trendjoin"

    def __init__(self, settings):
        self.settings = settings.strategy(self.id)

    def plan(self, ctx: CycleContext) -> CyclePlan:
        plan = CyclePlan()
        for pos in list(ctx.positions):
            self._manage_position(ctx, plan, pos)
        if not self.settings.enabled or self.settings.entries_paused or not ctx.entries_allowed:
            plan.notes.append("trendjoin aus")
            return plan
        signal = self.detect_breakout(ctx)
        if signal is None:
            plan.notes.append(
                "TODO: Momentum-Breakout aus bitget_bot_v4 — Repo leer, kein Entry"
            )
            return plan
        allowed, why = entry_allowed(
            signal_side="long",
            open_positions=len(ctx.positions),
            max_positions=min(self.settings.max_positions, MAX_POSITIONS),
            entries_today=ctx.entries_today,
            max_trades=min(self.settings.max_trades_per_day, MAX_TRADES_PER_DAY) or MAX_TRADES_PER_DAY,
            last_stop_ms=ctx.last_stop_ms.get(signal.symbol, 0),
            now_ms=ctx.now_ms,
        )
        if not allowed:
            plan.notes.append(f"trendjoin: {why}")
            return plan
        view = ctx.views.get(signal.symbol)
        if view is None or view.spec is None:
            return plan
        risk_pct = self.settings.risk_pct or RISK_PCT
        dist = abs(signal.entry - signal.stop)
        if dist <= 0 or ctx.sleeve_equity <= 0:
            return plan
        raw = (ctx.sleeve_equity * risk_pct * LEVERAGE) / dist
        size = floor_size(raw, view.spec.qty_step)
        plan.orders.append(
            OrderIntent(
                strategy_id=self.id,
                symbol=signal.symbol,
                market="perp",
                book_side="buy",
                position_side="long",
                purpose="open",
                order_type="limit",
                size=size,
                price=signal.entry,
                leverage=LEVERAGE,
                post_only=True,
                stop=signal.stop,
                take_profit=signal.take_profit,
                exit_is_maker=True,
                reason="trendjoin_breakout",
            )
        )
        return plan

    def detect_breakout(self, ctx: CycleContext) -> BreakoutSignal | None:
        """TODO: Port, sobald https://github.com/HonklerOfColor/bitget_bot_v4 Code enthält.

        Vorgesehen ist ein Long-only Momentum-Breakout. Bis dahin kein Signal.
        """
        return None

    def consume_fill(self, fill, book) -> None:
        return None

    def on_reject(self, intent, reason: str) -> None:
        return None

    def export_state(self) -> dict:
        return {"todo": "signal_source_missing"}

    def load_state(self, raw: dict) -> None:
        return None

    def _manage_position(self, ctx: CycleContext, plan: CyclePlan, pos: Position) -> None:
        view = ctx.views.get(pos.symbol)
        mark = view.last if view and view.last > 0 else 0.0
        if mark <= 0:
            return
        age = ctx.now_ms - pos.opened_ms
        pnl = (mark - pos.entry) * pos.qty if pos.side == "long" else (pos.entry - mark) * pos.qty
        if age >= TIME_STOP_MS and pnl <= 0:
            plan.orders.append(_market_close(pos, "time_stop"))
            return
        if pos.stop and pos.side == "long" and mark <= pos.stop:
            plan.orders.append(_market_close(pos, "sl"))
            return
        if (
            age >= BREAKEVEN_MS
            and pnl > 0
            and not pos.breakeven_armed
            and (pos.stop is None or pos.stop < pos.entry)
        ):
            plan.stops.append(StopUpdate(self.id, pos.symbol, pos.side, pos.entry, "breakeven_12h"))
        if pos.partial_done or pos.stop is None or pos.side != "long":
            return
        risk = pos.entry - pos.stop
        if risk <= 0:
            return
        if (mark - pos.entry) >= PARTIAL_R * risk:
            qty = pos.qty * PARTIAL_FRACTION
            if view and view.spec is not None:
                qty = floor_size(qty, view.spec.qty_step)
            if qty <= 0 or qty >= pos.qty:
                return
            plan.orders.append(
                OrderIntent(
                    strategy_id=self.id,
                    symbol=pos.symbol,
                    market="perp",
                    book_side="sell",
                    position_side="long",
                    purpose="reduce",
                    order_type="limit",
                    size=qty,
                    price=view.ask if view and view.ask > view.bid else mark,
                    leverage=pos.leverage,
                    post_only=True,
                    reason="partial_0.75R",
                )
            )


def entry_allowed(
    *,
    signal_side: str,
    open_positions: int,
    max_positions: int,
    entries_today: int,
    max_trades: int,
    last_stop_ms: int,
    now_ms: int,
) -> tuple[bool, str]:
    if signal_side != "long":
        return False, "long_only"
    if open_positions >= max_positions:
        return False, "max_positions"
    if entries_today >= max_trades:
        return False, "max_trades_per_day"
    if last_stop_ms and now_ms - last_stop_ms < REENTRY_COOLDOWN_MS:
        return False, "reentry_cooldown"
    return True, "ok"
