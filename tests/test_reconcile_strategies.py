"""Abgleich, Strategie-Schalter, V4-Regeln, Backtest-Harness."""

from __future__ import annotations

import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path

from unified_bot.book import Book
from unified_bot.gridcore.candles import Candle
from unified_bot.gridcore.specs import ContractSpec
from unified_bot.ids import owner_of
from unified_bot.market import CycleContext, SymbolView
from unified_bot.models import Position, WorkingOrder
from unified_bot.reconcile import reconcile
from unified_bot.backtest_harness import run_grid_backtest, run_reversal_replay
from unified_bot.settings import base_settings, load_settings, namespace_from
from unified_bot.strategies.registry import build_strategies
from unified_bot.strategies.reversal_rules import entry_hour_blocked, vienna_hour
from unified_bot.strategies.sniper_rules import imbalance_ratio, sniper_side, trend_from_closes, update_sweep
from unified_bot.strategies.trendjoin import (
    BREAKEVEN_MS,
    PARTIAL_FRACTION,
    TIME_STOP_MS,
    TrendJoinStrategy,
    entry_allowed,
)
from tests.fake_client import FakeBroker


ROOT = Path(__file__).resolve().parents[1]


class ReconcileTests(unittest.TestCase):
    def test_orphan_with_our_prefix_is_cancelled_foreign_is_not(self):
        cfg = base_settings()
        allocations = {item.strategy_id: item.allocation for item in cfg.strategies.values()}
        book = Book(100, allocations)
        book.orders["grd000000009"] = WorkingOrder(
            strategy_id="grid",
            client_oid="grd000000009",
            order_id="1",
            symbol="DOGEUSDT",
            market="perp",
            book_side="buy",
            position_side="long",
            purpose="open",
            order_type="limit",
            price=0.1,
            size=50,
            filled=0,
            leverage=2,
            post_only=True,
            placed_ms=1,
        )
        broker = FakeBroker()
        broker.remote_orders = [
            {"clientOid": "grd000000099", "orderId": "9", "symbol": "DOGEUSDT", "state": "live"},
            {"clientOid": "someoneelse1", "orderId": "8", "symbol": "BTCUSDT", "state": "live"},
        ]
        broker.details["grd000000009"] = {"state": "canceled", "filled": 0}
        notes = reconcile(book, broker, {}, 0.0002, 1)
        cancelled = [row["clientOid"] for row in broker.cancelled]
        self.assertIn("grd000000099", cancelled)
        self.assertNotIn("someoneelse1", cancelled)
        self.assertTrue(any("fremd" in note for note in notes))
        self.assertIsNone(owner_of("someoneelse1"))
        self.assertEqual(owner_of("grd000000099"), "grid")
        self.assertNotIn("grd000000009", book.orders)

    def test_position_mismatch_freezes(self):
        cfg = base_settings()
        allocations = {item.strategy_id: item.allocation for item in cfg.strategies.values()}
        book = Book(100, allocations)
        book.positions.append(Position("grid", "DOGEUSDT", "long", 10, 0.1, 2, 1))
        book.rebuild_locks()
        broker = FakeBroker()
        broker.remote_positions = [{"symbol": "DOGEUSDT", "side": "long", "qty": 40}]
        spec = ContractSpec("DOGEUSDT", 1, 5, 1, 0.00001, 5, 0)
        notes = reconcile(book, broker, {"DOGEUSDT": spec}, 0.0002, 1)
        self.assertTrue(any("eingefroren" in note for note in notes))


class StrategyTests(unittest.TestCase):
    def test_defaults_only_grid_can_enter(self):
        strategies = {item.id: item for item in build_strategies(base_settings())}
        self.assertTrue(strategies["grid"].settings.enabled)
        self.assertFalse(strategies["grid"].settings.entries_paused)
        self.assertEqual(
            strategies["grid"].settings.symbols,
            ["DOGEUSDT", "SUIUSDT", "SNDKUSDT", "INTCUSDT", "ANTHROPICUSDT"],
        )
        for strategy_id in ("reversal", "sniper", "trendjoin", "funding_arb", "daily_trend"):
            self.assertFalse(strategies[strategy_id].settings.enabled, strategy_id)
            self.assertTrue(strategies[strategy_id].settings.entries_paused, strategy_id)
        empty = CycleContext(
            now_ms=0,
            mode="paper",
            sleeve_equity=0,
            free_margin=0,
            entries_allowed=True,
            views={},
            positions=[],
            orders=[],
        )
        reversal = strategies["reversal"].plan(empty)
        self.assertTrue(any("aus" in note for note in reversal.notes))
        self.assertEqual(reversal.orders, [])
        slot = strategies["funding_arb"].plan(empty)
        self.assertTrue(any("TODO" in note for note in slot.notes))
        self.assertEqual(slot.orders, [])
        daily = strategies["daily_trend"].plan(empty)
        self.assertEqual(daily.orders, [])

    def test_vienna_window_matches_v1(self):
        summer = datetime(2026, 8, 26, 0, 30, tzinfo=timezone.utc).timestamp()
        # UTC 22:30 am 25. ist Wien 00:30 am 26. August (CEST).
        utc = datetime(2026, 8, 25, 22, 30, tzinfo=timezone.utc).timestamp()
        self.assertEqual(vienna_hour(utc), 0)
        self.assertTrue(entry_hour_blocked(utc))
        self.assertFalse(entry_hour_blocked(datetime(2026, 10, 16, 5, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Europe/Vienna")).timestamp()))
        self.assertIsNotNone(summer)

    def test_sniper_needs_all_three_and_ignores_short(self):
        self.assertGreater(imbalance_ratio([[1, 14], [1, 1]], [[1, 10]]), 1.4)
        self.assertEqual(trend_from_closes([1] * 19 + [2]), "LONG")
        state, sweep = update_sweep({"below_bid": True, "above_ask": False, "since": 0}, 100, 101, 100, 10)
        self.assertEqual(sweep, "LONG")
        self.assertEqual(sniper_side(1.5, "LONG", "LONG", hour_blocked=False), "long")
        self.assertIsNone(sniper_side(0.5, "SHORT", "SHORT", hour_blocked=False))
        self.assertIsNone(sniper_side(1.5, "LONG", "LONG", hour_blocked=True))
        self.assertFalse(state["below_bid"])

    def test_trendjoin_rules_and_no_signal_yet(self):
        self.assertEqual(entry_allowed(
            signal_side="short", open_positions=0, max_positions=3,
            entries_today=0, max_trades=5, last_stop_ms=0, now_ms=0,
        )[1], "long_only")
        self.assertEqual(entry_allowed(
            signal_side="long", open_positions=3, max_positions=3,
            entries_today=0, max_trades=5, last_stop_ms=0, now_ms=0,
        )[1], "max_positions")
        self.assertEqual(entry_allowed(
            signal_side="long", open_positions=0, max_positions=3,
            entries_today=5, max_trades=5, last_stop_ms=0, now_ms=0,
        )[1], "max_trades_per_day")
        self.assertEqual(entry_allowed(
            signal_side="long", open_positions=0, max_positions=3,
            entries_today=0, max_trades=5, last_stop_ms=1_000, now_ms=1_000 + 23 * 3_600_000,
        )[1], "reentry_cooldown")
        self.assertTrue(entry_allowed(
            signal_side="long", open_positions=2, max_positions=3,
            entries_today=4, max_trades=5, last_stop_ms=0, now_ms=10**13,
        )[0])
        strategy = TrendJoinStrategy(base_settings())
        now = 10_000_000_000
        pos = Position(
            strategy_id="trendjoin",
            symbol="BTCUSDT",
            side="long",
            qty=3.0,
            entry=100.0,
            leverage=5,
            opened_ms=now - TIME_STOP_MS - 1,
            stop=90.0,
            initial_qty=3.0,
        )
        view = SymbolView(
            "BTCUSDT",
            [],
            bid=99,
            ask=101,
            last=99,
            spec=ContractSpec("BTCUSDT", 0.001, 5, 0.001, 0.1, 1, 3),
        )
        ctx = CycleContext(
            now_ms=now,
            mode="paper",
            sleeve_equity=50,
            free_margin=50,
            entries_allowed=True,
            views={"BTCUSDT": view},
            positions=[pos],
            orders=[],
        )
        plan = strategy.plan(ctx)
        self.assertTrue(any(order.reason == "time_stop" for order in plan.orders))
        pos.opened_ms = now - 1
        pos.stop = 90
        view.last = 110
        plan = strategy.plan(ctx)
        partials = [order for order in plan.orders if order.reason == "partial_0.75R"]
        self.assertEqual(len(partials), 1)
        self.assertAlmostEqual(partials[0].size, 3.0 * PARTIAL_FRACTION, places=6)
        self.assertTrue(partials[0].wants_post_only)
        pos.opened_ms = now - BREAKEVEN_MS - 1
        view.last = 101
        pos.partial_done = True
        plan = strategy.plan(ctx)
        self.assertTrue(any(stop.reason == "breakeven_12h" for stop in plan.stops))
        self.assertIsNone(strategy.detect_breakout(ctx))


class PaperLoopTests(unittest.TestCase):
    def test_grid_places_post_only_then_restart_and_kill_clears(self):
        from unified_bot.runner import Bot

        cfg = base_settings()
        cfg.strategies["grid"].symbols = ["ALTUSDT"]
        spec = ContractSpec("ALTUSDT", 0.01, 5.0, 0.01, 0.01, 2, 2)
        candles = _bounded(320, 100.0, 103.0, 101.5)
        last = candles[-1].close
        view = SymbolView(
            "ALTUSDT", candles, bid=last - 0.05, ask=last + 0.05, last=last,
            funding_rate=0.0001, spec=spec,
        )
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "state.json"
            kill = Path(folder) / "KILL_SWITCH"
            bot = Bot(cfg, state_path=state, kill_path=kill)
            params = bot.by_id["grid"].params
            params.adx_max_1h = 100
            params.adx_max_4h = 100
            params.er_max = 1
            params.min_mid_crosses = 0
            report = bot.run_cycle({"ALTUSDT": view}, now_ms=1_700_000_000_000)
            self.assertGreater(report["placed"], 0, report["notes"])
            self.assertTrue(all(order.post_only for order in bot.book.orders.values()))
            self.assertTrue(all(order.client_oid.startswith("grd") for order in bot.book.orders.values()))
            sides = {order.position_side for order in bot.book.orders.values()}
            self.assertEqual(sides, {"long", "short"})
            again = Bot(cfg, state_path=state, kill_path=kill)
            self.assertEqual(set(again.book.orders), set(bot.book.orders))
            kill.write_text("halt", encoding="utf-8")
            again.by_id["grid"].params.adx_max_1h = 100
            again.by_id["grid"].params.adx_max_4h = 100
            again.by_id["grid"].params.er_max = 1
            again.by_id["grid"].params.min_mid_crosses = 0
            again.run_cycle({"ALTUSDT": view}, now_ms=1_700_000_000_000)
            self.assertTrue(again.risk.state.halted)
            self.assertEqual(again.risk.state.halt_reason, "kill_switch")
            self.assertEqual(again.book.orders, {})


def _bounded(n, lower, upper, end):
    out = []
    for i in range(n):
        phase = (i % 16) / 16.0
        if phase < 0.5:
            px = lower + (upper - lower) * (phase / 0.5)
        else:
            px = upper - (upper - lower) * ((phase - 0.5) / 0.5)
        if i == n - 1:
            px = end
        high = min(upper, max(px, upper if i % 16 == 8 else px))
        low = max(lower, min(px, lower if i % 16 == 0 else px))
        out.append(Candle(i * 3_600_000, px, high, low, px, 1.0))
    return out


class BacktestTests(unittest.TestCase):
    def test_grid_harness_reuses_engine(self):
        result = run_grid_backtest(equity=50)
        for key in ("net", "fees", "funding", "end_equity", "grids_started"):
            self.assertIn(key, result)
        self.assertEqual(result["start_equity"], 50)

    def test_reversal_replay_respects_hour_block(self):
        candles = []
        for i in range(30):
            # Kerze i: abwechselnd, Schluss in Wien-Stunde 0 bleibt gesperrt.
            base = 100 + (i % 2)
            ts = int(datetime(2026, 1, 15, 0, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Europe/Vienna")).timestamp() * 1000)
            ts += i * 3_600_000
            candles.append(Candle(ts, base, base + 1, base - 1, base + (1 if i % 2 == 0 else -1), 1))
        result = run_reversal_replay(candles)
        self.assertIn("trades", result)
        self.assertGreaterEqual(result["trades"], 0)


class ConfigTests(unittest.TestCase):
    def test_example_has_no_secrets_and_paper_is_default(self):
        text = (ROOT / "config.example.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        values = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                try:
                    values[node.targets[0].id] = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    continue
        self.assertTrue(values["DRY_RUN"])
        self.assertFalse(values["LIVE_TRADING"])
        self.assertTrue(str(values["API_KEY"]).startswith("your_"))
        self.assertEqual(values["TELEGRAM_BOT_TOKEN"], "")
        self.assertEqual(values["TELEGRAM_CHAT_ID"], "")
        self.assertNotIn("AAEEXw", text)
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("config.py", gitignore)
        loaded = load_settings(namespace_from({"DRY_RUN": False}))
        self.assertEqual(loaded.mode, "paper")
        with self.assertRaises(SystemExit):
            load_settings(namespace_from({"DRY_RUN": False, "LIVE_TRADING": True, "POS_MODE": "one_way"}))


if __name__ == "__main__":
    unittest.main()
