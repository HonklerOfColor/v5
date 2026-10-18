"""Regressionstests für Fehler aus dem Code-Review."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from unified_bot.book import Book
from unified_bot.gridcore.specs import FALLBACK_SPECS, ContractSpec
from unified_bot.market import CycleContext, SymbolView
from unified_bot.models import Position, WorkingOrder
from unified_bot.reconcile import reconcile
from unified_bot.runner import Bot
from unified_bot.settings import base_settings
from unified_bot.strategies.reversal import ReversalStrategy
from tests.fake_client import FakeBroker
from tests.test_reconcile_strategies import _bounded


def _grid_bot(folder: str):
    cfg = base_settings()
    cfg.strategies["grid"].symbols = ["ALTUSDT"]
    bot = Bot(cfg, state_path=Path(folder) / "state.json", kill_path=Path(folder) / "KILL")
    params = bot.by_id["grid"].params
    params.adx_max_1h = 100
    params.adx_max_4h = 100
    params.er_max = 1
    params.min_mid_crosses = 0
    return bot


def _alt_view(last: float) -> SymbolView:
    spec = ContractSpec("ALTUSDT", 0.01, 5.0, 0.01, 0.01, 2, 2)
    candles = _bounded(320, 100.0, 103.0, 101.5)
    return SymbolView(
        "ALTUSDT", candles, bid=last - 0.05, ask=last + 0.05, last=last, funding_rate=0.0001, spec=spec
    )


class GridRetireTests(unittest.TestCase):
    def test_breakout_without_lots_removes_grid_and_sets_cooldown(self):
        with tempfile.TemporaryDirectory() as folder:
            bot = _grid_bot(folder)
            now = 1_700_000_000_000
            bot.run_cycle({"ALTUSDT": _alt_view(101.5)}, now_ms=now)
            grid_strategy = bot.by_id["grid"]
            self.assertIn("ALTUSDT", grid_strategy.grids)
            self.assertFalse(grid_strategy.grids["ALTUSDT"].lots)
            bot.run_cycle({"ALTUSDT": _alt_view(130.0)}, now_ms=now + 20_000)
            self.assertNotIn("ALTUSDT", grid_strategy.grids)
            self.assertGreater(grid_strategy.cooldown_until_ms.get("ALTUSDT", 0), now)


class ReversalExitTests(unittest.TestCase):
    def _ctx(self, pos: Position, last: float) -> CycleContext:
        view = SymbolView(
            "BTCUSDT", [], bid=last, ask=last, last=last,
            spec=ContractSpec("BTCUSDT", 0.001, 5, 0.001, 0.1, 1, 3),
        )
        return CycleContext(
            now_ms=pos.opened_ms + 60_000,
            mode="paper",
            sleeve_equity=50,
            free_margin=50,
            entries_allowed=False,
            views={"BTCUSDT": view},
            positions=[pos],
            orders=[],
        )

    def test_stop_and_target_close_the_position(self):
        strategy = ReversalStrategy(base_settings())
        pos = Position(
            strategy_id="reversal", symbol="BTCUSDT", side="long", qty=1.0, entry=100.0,
            leverage=2, opened_ms=1_000_000, stop=97.0, take_profit=104.0, initial_qty=1.0,
        )
        sl = strategy.plan(self._ctx(pos, 96.5))
        self.assertEqual([order.reason for order in sl.orders], ["sl"])
        tp = strategy.plan(self._ctx(pos, 104.5))
        self.assertEqual([order.reason for order in tp.orders], ["tp"])
        quiet = strategy.plan(self._ctx(pos, 100.5))
        self.assertEqual(quiet.orders, [])


class ReconcileFillTests(unittest.TestCase):
    def test_reconcile_returns_fills_and_frozen_symbols(self):
        cfg = base_settings()
        allocations = {item.strategy_id: item.allocation for item in cfg.strategies.values()}
        book = Book(100, allocations)
        book.orders["grd000000001"] = WorkingOrder(
            strategy_id="grid", client_oid="grd000000001", order_id="1", symbol="DOGEUSDT",
            market="perp", book_side="buy", position_side="long", purpose="open",
            order_type="limit", price=0.1, size=50, filled=0, leverage=2, post_only=True, placed_ms=1,
        )
        broker = FakeBroker()
        broker.details["grd000000001"] = {"state": "filled", "filled": 50, "avg": 0.1}
        broker.remote_positions = [
            {"symbol": "BTCUSDT", "side": "long", "qty": 1},
            {"symbol": "DOGEUSDT", "side": "long", "qty": 50},
        ]
        fills: list = []
        frozen: set[str] = set()
        reconcile(book, broker, FALLBACK_SPECS, 0.0002, 5, fills=fills, frozen=frozen)
        self.assertEqual([fill.client_oid for fill in fills], ["grd000000001"])
        self.assertIn("BTCUSDT", frozen)
        self.assertNotIn("DOGEUSDT", frozen)


class _PublicStub:
    def __init__(self, spec: ContractSpec):
        self.spec = spec
        self.spec_calls = 0

    def get_candles(self, *_args, **_kwargs):
        return []

    def get_ticker(self, _symbol):
        return {"lastPr": "0.2", "bidPr": "0.2", "askPr": "0.2"}

    def get_orderbook(self, *_args, **_kwargs):
        return {"data": {"bids": [], "asks": []}}

    def get_spec(self, _symbol):
        self.spec_calls += 1
        return self.spec


class SpecAndAccountTests(unittest.TestCase):
    def test_live_spec_replaces_fallback_once(self):
        live = ContractSpec("DOGEUSDT", 7, 5, 7, 0.00001, 5, 0)
        stub = _PublicStub(live)
        with tempfile.TemporaryDirectory() as folder:
            bot = Bot(base_settings(), state_path=Path(folder) / "s.json", public_client=stub)
            bot._fetch_symbol("DOGEUSDT")
            bot._fetch_symbol("DOGEUSDT")
        self.assertEqual(bot.specs["DOGEUSDT"].qty_step, 7)
        self.assertEqual(stub.spec_calls, 1)

    def test_uid_is_checked_on_restart_with_existing_state(self):
        cfg = base_settings()
        cfg.api_key, cfg.secret_key, cfg.passphrase = "bg_realkey0001", "realsecret0001", "realpass0001"

        class WrongAccount:
            def __init__(self, *_args, **_kwargs):
                pass

            def get_user_id(self):
                return "1234567890"

            def get_equity(self):
                raise AssertionError("Equity darf ohne Zustandsdatei-Anker nicht gelesen werden")

        with mock.patch("unified_bot.runner.BitgetClient", WrongAccount):
            with self.assertRaises(SystemExit):
                Bot._try_account_anchor(Book(100, {}), cfg, anchor=False)

    def test_symbols_skip_disabled_strategies(self):
        with tempfile.TemporaryDirectory() as folder:
            bot = Bot(base_settings(), state_path=Path(folder) / "s.json")
            symbols = bot.symbols()
        self.assertIn("DOGEUSDT", symbols)
        self.assertNotIn("BTCUSDT", symbols)


if __name__ == "__main__":
    unittest.main()
