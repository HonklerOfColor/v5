"""Payloads, Risikolimits, Symbol-Sperre, Zurechnung. Kein Netz."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from unified_bot.book import Book
from unified_bot.gridcore.specs import ContractSpec
from unified_bot.models import OrderIntent
from unified_bot.orders import OrderManager, build_perp_payload, build_spot_payload
from unified_bot.risk import RiskManager, RiskState
from unified_bot.settings import base_settings
from unified_bot.sizing import floor_size
from tests.fake_client import FakeBroker


def spec_alt() -> ContractSpec:
    return ContractSpec("ALTUSDT", 0.01, 5.0, 0.01, 0.01, 2, 2)


def settings():
    cfg = base_settings()
    cfg.strategies["grid"].allocation = 0.50
    cfg.strategies["sniper"].enabled = True
    cfg.strategies["sniper"].entries_paused = False
    cfg.strategies["sniper"].allocation = 0.20
    return cfg


def stack(cfg=None):
    cfg = cfg or settings()
    allocations = {item.strategy_id: item.allocation for item in cfg.strategies.values()}
    book = Book(100.0, allocations)
    risk = RiskManager(cfg, RiskState(day="2026-10-18", day_start_equity=100.0))
    broker = FakeBroker()
    return cfg, book, OrderManager(cfg, risk, book, broker), broker, risk


def open_intent(**kwargs) -> OrderIntent:
    base = dict(
        strategy_id="grid",
        symbol="ALTUSDT",
        market="perp",
        book_side="buy",
        position_side="long",
        purpose="open",
        order_type="limit",
        size=0.2,
        price=100.0,
        leverage=2,
        post_only=True,
        expected_tp_pct=0.01,
        exit_is_maker=True,
        reason="test",
    )
    base.update(kwargs)
    return OrderIntent(**base)


class PayloadTests(unittest.TestCase):
    def test_hedge_open_is_post_only_and_tagged(self):
        cfg, book, manager, broker, _risk = stack()
        result = manager.submit(open_intent(), spec_alt(), mark=100.0, bid=99.9, ask=100.1, ts_ms=1)
        self.assertTrue(result.accepted, result.reason)
        payload = result.payload
        self.assertEqual(payload["side"], "buy")
        self.assertEqual(payload["tradeSide"], "open")
        self.assertEqual(payload["force"], "post_only")
        self.assertTrue(payload["clientOid"].startswith("grd"))
        self.assertNotIn("e", payload["size"].lower())
        self.assertEqual(payload["marginMode"], "isolated")
        self.assertEqual(broker.placed[0]["payload"]["clientOid"], payload["clientOid"])

    def test_hedge_close_long_uses_buy_and_close(self):
        intent = OrderIntent(
            strategy_id="grid",
            symbol="ALTUSDT",
            market="perp",
            book_side="sell",
            position_side="long",
            purpose="close",
            order_type="limit",
            size=0.2,
            price=101.0,
            leverage=2,
            client_oid="grd000000001",
        )
        payload = build_perp_payload(intent, spec_alt(), "hedge", "USDT-FUTURES", "isolated", "USDT")
        self.assertEqual(payload["side"], "buy")
        self.assertEqual(payload["tradeSide"], "close")
        self.assertEqual(payload["force"], "post_only")
        self.assertNotIn("reduceOnly", payload)

    def test_spot_payload_is_built_but_not_sent_for_other_strategies(self):
        intent = open_intent(strategy_id="funding_arb", market="spot", client_oid="fra000000001")
        payload = build_spot_payload(intent, spec_alt())
        self.assertEqual(payload["force"], "post_only")
        _cfg, _book, manager, broker, _risk = stack()
        result = manager.submit(open_intent(market="spot"), spec_alt(), mark=100, bid=99, ask=101)
        self.assertEqual(result.reason, "spot_not_enabled")
        self.assertEqual(broker.placed, [])

    def test_would_cross_is_refused(self):
        _cfg, _book, manager, broker, _risk = stack()
        result = manager.submit(open_intent(price=100.2), spec_alt(), mark=100, bid=99.9, ask=100.1)
        self.assertEqual(result.reason, "would_cross")
        self.assertEqual(broker.placed, [])


class RiskTests(unittest.TestCase):
    def test_floors_size_and_rejects_below_min_notional(self):
        self.assertEqual(floor_size(0.019, 0.01), 0.01)
        self.assertEqual(floor_size(0.009, 0.01), 0.0)
        cfg, _book, manager, _broker, _risk = stack()
        tiny = open_intent(size=0.04, price=100.0)  # notional 4 after floor? 0.04*100=4
        result = manager.submit(tiny, spec_alt(), mark=100, bid=99, ask=101)
        self.assertEqual(result.reason, "below_min_notional")
        below_step = open_intent(size=0.009, price=100)
        result = manager.submit(below_step, spec_alt(), mark=100, bid=99, ask=101)
        self.assertEqual(result.reason, "below_min_size")

    def test_tp_must_clear_three_round_trips(self):
        _cfg, _book, manager, _broker, _risk = stack()
        # Maker+Maker = 0.04 %. 3× = 0.12 %. 0.10 % ist zu eng, 0.20 % reicht.
        tight = open_intent(expected_tp_pct=0.0010)
        self.assertEqual(manager.submit(tight, spec_alt(), mark=100, bid=99, ask=101).reason, "tp_inside_fees")
        wide = open_intent(expected_tp_pct=0.0020)
        self.assertTrue(manager.submit(wide, spec_alt(), mark=100, bid=99, ask=101).accepted)

    def test_taker_exit_needs_a_wider_target(self):
        _cfg, _book, manager, _broker, _risk = stack()
        # Entry Maker + Exit Taker = 0.08 %, 3× = 0.24 %.
        intent = open_intent(expected_tp_pct=0.0020, exit_is_maker=False, strategy_id="sniper", leverage=3)
        result = manager.submit(intent, spec_alt(), mark=100, bid=99, ask=101)
        self.assertEqual(result.reason, "tp_inside_fees")

    def test_entries_paused_and_disabled(self):
        cfg = settings()
        cfg.strategies["sniper"].entries_paused = True
        _cfg, _book, manager, _broker, _risk = stack(cfg)
        intent = open_intent(strategy_id="sniper", leverage=3, exit_is_maker=False, expected_tp_pct=0.01)
        self.assertEqual(manager.submit(intent, spec_alt(), mark=100, bid=99, ask=101).reason, "entries_paused")
        cfg.strategies["reversal"].enabled = False
        cfg.strategies["reversal"].allocation = 0.1
        _cfg, _book, manager, _broker, _risk = stack(cfg)
        intent = open_intent(strategy_id="reversal", leverage=3, expected_tp_pct=0.01)
        self.assertEqual(manager.submit(intent, spec_alt(), mark=100, bid=99, ask=101).reason, "strategy_disabled")

    def test_leverage_exposure_and_margin(self):
        cfg, book, manager, _broker, _risk = stack()
        hot = open_intent(leverage=10)
        self.assertEqual(manager.submit(hot, spec_alt(), mark=100, bid=99, ask=101).reason, "leverage_cap")
        cfg.max_total_exposure = 0.30
        huge = open_intent(size=0.40, price=100, leverage=2)  # Notional 40, Deckel 30
        self.assertEqual(manager.submit(huge, spec_alt(), mark=100, bid=99, ask=101).reason, "exposure_cap")
        book.anchor = 10
        cfg.strategies["grid"].allocation = 0.50
        book.sync_allocations({"grid": 0.50, "sniper": 0.0, "reversal": 0.0, "trendjoin": 0.0, "funding_arb": 0.0, "daily_trend": 0.0})
        # sleeve cash = 5. Margin für 0.2*100/2 = 10 > 5.
        fat = open_intent(size=0.2, price=100, leverage=2)
        self.assertEqual(manager.submit(fat, spec_alt(), mark=100, bid=99, ask=101).reason, "margin_exceeds_sleeve")

    def test_daily_loss_and_kill_block_entries_not_exits(self):
        cfg, book, manager, _broker, risk = stack()
        risk.state.day_start_equity = 100
        risk.state.check_daily(94, cfg.daily_loss_pct)
        self.assertTrue(risk.state.halted)
        self.assertEqual(risk.state.halt_reason, "daily_loss")
        blocked = manager.submit(open_intent(), spec_alt(), mark=100, bid=99, ask=101)
        self.assertEqual(blocked.reason, "daily_loss")
        from unified_bot.models import Position

        book.positions.append(
            Position("grid", "ALTUSDT", "long", 0.2, 100, 2, 1, market="perp")
        )
        book.rebuild_locks()
        close = OrderIntent(
            strategy_id="grid",
            symbol="ALTUSDT",
            market="perp",
            book_side="sell",
            position_side="long",
            purpose="emergency",
            order_type="market",
            size=0.2,
            leverage=2,
            post_only=False,
            reason="daily_loss",
        )
        closed = manager.submit(close, spec_alt(), mark=99, ts_ms=2)
        self.assertTrue(closed.accepted, closed.reason)
        self.assertEqual(closed.reason, "filled")

    def test_kill_file(self):
        from unified_bot.risk import kill_file_active

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "KILL_SWITCH"
            self.assertFalse(kill_file_active(path))
            path.write_text("1", encoding="utf-8")
            self.assertTrue(kill_file_active(path))


class ConflictTests(unittest.TestCase):
    def test_second_strategy_is_locked_out_of_the_symbol(self):
        _cfg, book, manager, broker, _risk = stack()
        first = manager.submit(open_intent(), spec_alt(), mark=100, bid=99.5, ask=100.5)
        self.assertTrue(first.accepted, first.reason)
        self.assertEqual(book.symbol_owner("ALTUSDT"), "grid")
        second = open_intent(
            strategy_id="sniper",
            book_side="sell",
            position_side="short",
            leverage=3,
            exit_is_maker=False,
            expected_tp_pct=0.01,
        )
        locked = manager.submit(second, spec_alt(), mark=100, bid=99.5, ask=100.5)
        self.assertEqual(locked.reason, "symbol_locked")
        self.assertEqual(len(broker.placed), 1)

    def test_same_strategy_may_hold_both_sides(self):
        _cfg, _book, manager, broker, _risk = stack()
        self.assertTrue(
            manager.submit(open_intent(), spec_alt(), mark=100, bid=99.5, ask=100.5).accepted
        )
        other = open_intent(book_side="sell", position_side="short", price=101)
        result = manager.submit(other, spec_alt(), mark=100, bid=99.5, ask=100.4)
        self.assertTrue(result.accepted, result.reason)
        self.assertEqual(len(broker.placed), 2)

    def test_other_symbol_stays_free(self):
        _cfg, _book, manager, _broker, _risk = stack()
        manager.submit(open_intent(), spec_alt(), mark=100, bid=99.5, ask=100.5)
        other = open_intent(
            strategy_id="sniper",
            symbol="BNBUSDT",
            leverage=3,
            price=100,
            exit_is_maker=False,
            expected_tp_pct=0.01,
        )
        spec = ContractSpec("BNBUSDT", 0.01, 5, 0.01, 0.01, 2, 2)
        result = manager.submit(other, spec, mark=100, bid=99.5, ask=100.5)
        self.assertTrue(result.accepted, result.reason)


class AttributionTests(unittest.TestCase):
    def test_fees_and_pnl_stay_on_the_owning_strategy(self):
        cfg, book, manager, _broker, _risk = stack()
        opened = manager.submit(open_intent(size=0.2, price=100), spec_alt(), mark=100, bid=99, ask=101, ts_ms=1_000)
        self.assertEqual(opened.reason, "live")
        # Fill über den Paper-Pfad nachbauen: Limit liegt, wir buchen den Fill direkt.
        from unified_bot.models import Fill

        order = book.orders[opened.client_oid]
        fill = Fill(
            strategy_id="grid",
            client_oid=order.client_oid,
            symbol="ALTUSDT",
            book_side="buy",
            position_side="long",
            purpose="open",
            price=100.0,
            qty=0.2,
            fee=100 * 0.2 * cfg.maker_fee,
            fee_rate=cfg.maker_fee,
            liquidity="maker",
            ts_ms=2_000,
            leverage=2,
            reason="grid",
        )
        book.apply_fill(fill)
        close = OrderIntent(
            strategy_id="grid",
            symbol="ALTUSDT",
            market="perp",
            book_side="sell",
            position_side="long",
            purpose="close",
            order_type="market",
            size=0.2,
            leverage=2,
            post_only=False,
            reason="tp",
        )
        closed = manager.submit(close, spec_alt(), mark=102, ts_ms=3_000)
        self.assertTrue(closed.accepted, closed.reason)
        grid = book.ledger("grid")
        sniper = book.ledger("sniper")
        self.assertGreater(grid.fees, 0)
        self.assertAlmostEqual(grid.realized, 0.4, places=6)
        self.assertEqual(sniper.fees, 0)
        self.assertEqual(sniper.realized, 0)
        self.assertEqual(book.closed[-1].strategy, "grid")
        self.assertAlmostEqual(book.closed[-1].gross_pnl, 0.4, places=6)
        self.assertEqual(book.symbol_owner("ALTUSDT"), None)


if __name__ == "__main__":
    unittest.main()
