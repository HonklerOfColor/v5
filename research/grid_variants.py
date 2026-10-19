"""Grid-Varianten: der Default aus gridbot.backtest_engine und eine Abwicklung statt Taker-Ausstieg.

Abwicklung (winddown): Fällt das Regime, wird nicht sofort per Taker geschlossen.
Die Einstiegs-Orders werden storniert, die Take-Profits bleiben liegen. Das Grid
endet, sobald kein Los mehr offen ist — ohne Taker-Fee. Breakout, Notstopp und
harter Stop gelten weiter. Kommt das Regime zurück, läuft das Grid normal weiter.
Nach max_winddown_bars Stunden ohne Abschluss wird doch per Taker geschlossen.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace

from gridbot.backtest_engine import _day, _hard_breakout_price, run_backtest
from gridbot.candles import Candle
from gridbot.engine import ActiveGrid, build_plan
from gridbot.params import GridParams
from gridbot.regime import assess
from gridbot.risk import RiskGuard
from gridbot.specs import ContractSpec
from research.metrics import normalize_grid_result


@dataclass(frozen=True)
class GridVariant:
    name: str
    params: GridParams
    winddown: bool = False
    max_winddown_bars: int = 48


def default_variant() -> GridVariant:
    return GridVariant("grid_default", GridParams())


def winddown_variant(max_bars: int = 48) -> GridVariant:
    return GridVariant(f"grid_winddown_{max_bars}h", GridParams(), winddown=True, max_winddown_bars=max_bars)


def winddown_hysteresis_variant(max_bars: int = 48) -> GridVariant:
    params = replace(GridParams(), adx_exit_margin=6.0, er_exit_margin=0.15, exit_trend_only=True)
    return GridVariant(f"grid_winddown_{max_bars}h_hyst", params, winddown=True, max_winddown_bars=max_bars)


def run_grid_variant(
    candles: list[Candle],
    spec: ContractSpec,
    variant: GridVariant,
    equity0: float,
    leverage: int = 2,
    start_index: int = 0,
) -> dict:
    if not variant.winddown:
        raw = run_backtest(candles, spec, variant.params, equity0, leverage, start_index)
    else:
        raw = _run_winddown(candles, spec, variant, equity0, leverage, start_index)
    out = normalize_grid_result(raw)
    out["strategy"] = variant.name
    return out


def _run_winddown(
    candles: list[Candle],
    spec: ContractSpec,
    variant: GridVariant,
    equity0: float,
    leverage: int,
    start_index: int,
) -> dict:
    params = variant.params
    symbol = spec.symbol
    length = len(candles)
    grid: ActiveGrid | None = None
    winddown_since: int | None = None
    banked = 0.0
    banked_realized = 0.0
    banked_fees = 0.0
    banked_funding = 0.0
    taker_fees = 0.0
    trips = 0
    trip_wins = 0
    peak = equity0
    max_dd = 0.0
    risk = RiskGuard()
    cooldown_until = 0
    counts: Counter[str] = Counter()
    grids_started = 0
    exit_reasons: Counter[str] = Counter()
    maker_fills = 0
    profit_sum = 0.0
    loss_sum = 0.0
    closed_wins = 0
    closed_losses = 0
    start_index = max(0, min(start_index, max(length - 1, 0)))

    def equity_at(mark: float) -> float:
        if grid is None:
            return equity0 + banked
        return equity0 + banked + grid.net_pnl(mark)

    def bank(reason: str, mark: float) -> None:
        nonlocal grid, banked, banked_realized, banked_fees, banked_funding, taker_fees
        nonlocal profit_sum, loss_sum, closed_wins, closed_losses, cooldown_until, winddown_since
        assert grid is not None
        before_fees = grid.fees
        grid.flatten(mark, params.taker_slippage_pct, params.taker_fee)
        taker_fees += grid.fees - before_fees
        episode = grid.net_pnl(mark)
        if episode > 0:
            profit_sum += episode
            closed_wins += 1
        elif episode < 0:
            loss_sum += episode
            closed_losses += 1
        banked += episode
        banked_realized += grid.realized
        banked_fees += grid.fees
        banked_funding += grid.funding
        exit_reasons[reason] += 1
        cooldown_until = i + params.cooldown_bars
        grid = None
        winddown_since = None

    def has_inventory() -> bool:
        assert grid is not None
        return grid.long_qty > 0 or grid.short_qty > 0

    for i in range(start_index, length):
        candle = candles[i]
        mark = candle.close
        risk.on_day(_day(candle.ts), equity_at(mark))
        stopped = False

        if grid is not None:
            if candle.ts % (8 * 3_600_000) == 0:
                grid.charge_funding(candle.close, params.funding_rate_8h)
            hard = _hard_breakout_price(grid, candle, params.breakout_hard_pct)
            breakout = hard is not None or grid.outside(candle.close, params.breakout_buffer_pct)
            for order in list(grid.orders.values()):
                if not (candle.low <= order.price <= candle.high):
                    continue
                if breakout and order.purpose != "open":
                    continue
                before = grid.realized
                grid.apply_fill(order, order.price, order.size, params.maker_fee)
                maker_fills += 1
                if order.purpose != "open" and grid.realized != before:
                    trips += 1
                    if grid.realized > before:
                        trip_wins += 1
            if hard is not None:
                bank("breakout_hard", hard)
                stopped = True
            elif breakout:
                bank("breakout", candle.close)
                stopped = True
            elif grid.net_pnl(candle.close) <= -grid.hard_stop_usdt:
                bank("hard_stop", candle.close)
                stopped = True
            else:
                window = candles[max(0, i - 249): i + 1]
                ranging = assess(window, None, params, holding=True).ranging
                if not ranging and winddown_since is None:
                    if not has_inventory():
                        bank("regime_flat", candle.close)  # nichts offen: kostenlos
                        stopped = True
                    else:
                        winddown_since = i
                elif ranging and winddown_since is not None:
                    winddown_since = None  # Range ist zurück
                if grid is not None and winddown_since is not None:
                    if not has_inventory():
                        bank("winddown_done", candle.close)
                        stopped = True
                    elif i - winddown_since >= variant.max_winddown_bars:
                        bank("winddown_timeout", candle.close)
                        stopped = True
                if grid is not None:
                    eq = equity_at(mark)
                    grid.sync_orders(candle.close, eq, spec, params)
                    if winddown_since is not None:
                        for oid, order in list(grid.orders.items()):
                            if order.purpose == "open":
                                grid.orders.pop(oid)

        equity = equity_at(mark)
        if risk.check_daily(equity, params.daily_loss_pct) and grid is not None:
            bank("daily_loss", candle.close)
            stopped = True
            equity = equity_at(mark)

        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)

        if grid is None and not stopped and not risk.halted:
            if i < cooldown_until:
                counts["cooldown"] += 1
                continue
            window = candles[max(0, i - 249): i + 1]
            regime = assess(window, None, params)
            if not regime.ranging:
                for reason in regime.reasons:
                    counts[reason] += 1
                continue
            counts["ranging"] += 1
            plan, why = build_plan(window, spec, equity, params, leverage)
            if plan is None:
                counts[why] += 1
                continue
            grid = ActiveGrid.from_plan(plan, created_ms=candle.ts)
            grid.sync_orders(candle.close, equity, spec, params)
            grids_started += 1
            counts["started"] += 1

    last_mark = candles[length - 1].close if length else 0.0
    final = equity_at(last_mark) if length else equity0
    open_unreal = grid.unrealized(last_mark) if grid is not None else 0.0
    open_realized = grid.realized if grid is not None else 0.0
    open_fees = grid.fees if grid is not None else 0.0
    open_funding = grid.funding if grid is not None else 0.0
    realized = banked_realized + open_realized
    fees = banked_fees + open_fees
    funding = banked_funding + open_funding
    return {
        "bars": length - start_index,
        "start_equity": equity0,
        "end_equity": final,
        "net": final - equity0,
        "realized": realized,
        "unrealized": open_unreal,
        "fees": fees,
        "maker_fees": fees - taker_fees,
        "taker_fees": taker_fees,
        "funding": funding,
        "net_without_funding": final - equity0 + funding,
        "max_drawdown_pct": max_dd * 100.0,
        "grids_started": grids_started,
        "maker_fills": maker_fills,
        "round_trips": trips,
        "round_trip_wins": trip_wins,
        "exits": dict(exit_reasons),
        "counts": dict(counts),
        "open_symbol": symbol if grid is not None else "",
        "from_ts": candles[start_index].ts if length else 0,
        "to_ts": candles[length - 1].ts if length else 0,
        "breakout_exits": int(exit_reasons.get("breakout", 0) + exit_reasons.get("breakout_hard", 0)),
        "hard_breakout_exits": int(exit_reasons.get("breakout_hard", 0)),
        "profit_factor": (profit_sum / abs(loss_sum)) if loss_sum < 0 else None,
        "closed_grid_wins": closed_wins,
        "closed_grid_losses": closed_losses,
    }
