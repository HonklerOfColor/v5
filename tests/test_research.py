"""Plausibilität der Forschungs-Engines auf synthetischen Kerzen. Kein Netz."""

from __future__ import annotations

import unittest

from gridbot.candles import Candle
from gridbot.specs import ContractSpec
from research.costs import Costs
from research.meanrev import MeanRevParams, run_meanrev
from research.metrics import Ledger
from research.trend import TrendParams, atr_series, run_trend


def spec() -> ContractSpec:
    return ContractSpec("ALTUSDT", min_qty=0.01, min_notional=5.0, qty_step=0.01, price_tick=0.01, price_place=2, qty_place=2)


def hourly(prices: list[float], wick: float = 0.2) -> list[Candle]:
    out = []
    for i, px in enumerate(prices):
        prev = prices[i - 1] if i else px
        out.append(Candle(i * 3_600_000, prev, max(prev, px) + wick, min(prev, px) - wick, px, 1.0))
    return out


class TrendTests(unittest.TestCase):
    def test_atr_series_aligns_with_candles(self):
        candles = hourly([100 + i * 0.1 for i in range(40)])
        atrs = atr_series(candles, 14)
        self.assertEqual(len(atrs), len(candles))
        self.assertIsNone(atrs[13])
        self.assertIsNotNone(atrs[14])
        self.assertAlmostEqual(atrs[-1], 0.5, places=6)  # Range 0.1 + 2×0.2 Docht

    def test_uptrend_makes_money_long_and_loses_nothing_short(self):
        # 200 Stunden Seitwärts, dann 600 Stunden stetig aufwärts (+60 %)
        flat = [100.0 + (0.3 if i % 2 else -0.3) for i in range(200)]
        up = [100.0 + i * 0.1 for i in range(600)]
        candles = hourly(flat + up)
        result = run_trend(candles, spec(), TrendParams(entry_lookback=20, exit_lookback=10), Costs(), 50.0, 2)
        self.assertGreater(result["net"], 0.5)
        self.assertGreaterEqual(result["trades"], 1)
        self.assertEqual(result["maker_fees"], 0.0)

    def test_ledger_mark_does_not_touch_cash(self):
        ledger = Ledger(50.0)
        ledger.mark(60.0)
        ledger.mark(40.0)
        self.assertEqual(ledger.equity, 50.0)
        self.assertAlmostEqual(ledger.max_dd, 1 / 3)

    def test_too_small_orders_are_skipped(self):
        flat = [100.0 + (0.3 if i % 2 else -0.3) for i in range(200)]
        up = [100.0 + i * 0.1 for i in range(600)]
        candles = hourly(flat + up)
        big = ContractSpec("BIGUSDT", min_qty=10.0, min_notional=5.0, qty_step=1.0, price_tick=0.01, price_place=2, qty_place=0)
        result = run_trend(candles, big, TrendParams(entry_lookback=20, exit_lookback=10), Costs(), 50.0, 2)
        self.assertEqual(result["trades"], 0)
        self.assertEqual(result["net"], 0.0)


class MeanRevTests(unittest.TestCase):
    def test_chop_fills_at_band_and_exits_at_mid(self):
        from tests.test_grid import chop_candles

        # Gezähmter Random Walk: Bandberührungen kehren zurück. Eine glatte Sinuswelle
        # läuft nach der Berührung weiter und wird nur ausgestoppt.
        candles = chop_candles(1200, seed=3)
        result = run_meanrev(candles, spec(), MeanRevParams(max_hold=48), Costs(), 50.0, 2)
        self.assertGreater(result["trades"], 5)
        self.assertGreater(result["exits"].get("ziel", 0), 0)
        self.assertGreater(result["maker_fees"], 0.0)

    def test_entry_candle_opening_through_limit_is_rejected(self):
        # Kerze eröffnet unter dem Buy-Limit: Post-only wäre abgelehnt, kein Fill.
        prices = [100.0 + (0.5 if i % 2 else -0.5) for i in range(60)] + [90.0] * 5 + [100.0] * 40
        candles = hourly(prices, wick=0.0)
        result = run_meanrev(candles, spec(), MeanRevParams(max_hold=48), Costs(), 50.0, 2)
        self.assertEqual(result["taker_fees"] + result["maker_fees"], result["fees"])


if __name__ == "__main__":
    unittest.main()
