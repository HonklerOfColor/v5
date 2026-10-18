"""Spot-Signale und Engine gegen Referenzwerte aus docs/spot_modules/code (lib.py, tf.py).

Die Werte in fixtures/spot/reference.json wurden mit make_fixtures.py erzeugt (pandas + numba),
der Bot rechnet in reinem Python. Toleranz 1e-9.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from unified_bot.spot.candles import DailySeries, day_from_iso
from unified_bot.spot.engine import simulate
from unified_bot.spot.signals import donchian_combo, ensemble_signal, sigma_annualized
from unified_bot.spot.universe import rank_candidates, select_universe

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "spot" / "reference.json"
TOL = 1e-9


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _floats(values: list) -> list[float]:
    return [float("nan") if value is None else float(value) for value in values]


def _close(a: float, b: float, tol: float = TOL) -> bool:
    if (a != a) and (b != b):
        return True
    if (a != a) or (b != b):
        return False
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


class TrendReferenceTests(unittest.TestCase):
    def test_donchian_weights_and_flags_match_lib(self):
        ref = _load()
        windows = tuple(ref["windows"])
        for symbol, closes in ref["closes"].items():
            series = _floats(closes)
            sigma = sigma_annualized(series)
            weights, changed, _ = donchian_combo(series, sigma, windows, ref["VT"], ref["cap"])
            expected_w = _floats(ref["W"][symbol])
            expected_ch = ref["CH"][symbol]
            self.assertEqual(len(weights), len(expected_w))
            for index, (got, want) in enumerate(zip(weights, expected_w)):
                self.assertTrue(_close(got, want), f"{symbol} Tag {index}: {got} != {want}")
            self.assertEqual(changed, expected_ch, f"{symbol}: Flags weichen ab")

    def test_ensemble_signal_matches_tf(self):
        ref = _load()
        for symbol, expected in ref["ens"].items():
            got = ensemble_signal(_floats(ref["closes"][symbol]))
            want = _floats(expected)
            for index, (a, b) in enumerate(zip(got, want)):
                self.assertTrue(_close(a, b), f"{symbol} Tag {index}: {a} != {b}")


class EngineReferenceTests(unittest.TestCase):
    def _panel(self, ref: dict, key_tw: str, key_fl: str, symbols: list[str]):
        closes = {symbol: _floats(ref["closes"][symbol]) for symbol in symbols}
        targets = {symbol: _floats(ref[key_tw][symbol]) for symbol in symbols}
        flags = {symbol: ref[key_fl][symbol] for symbol in symbols}
        return closes, targets, flags

    def _assert_path(self, got: list[float], want: list[float]):
        self.assertEqual(len(got), len(want))
        for index, (a, b) in enumerate(zip(got, want)):
            self.assertTrue(_close(a, b), f"Tag {index}: {a} != {b}")

    def test_ideal_equity_matches_run_engine(self):
        ref = _load()
        closes, targets, flags = self._panel(ref, "TW", "FL", list(ref["closes"]))
        got = simulate(closes, targets, flags, 1.0, cost=ref["cost"], threshold=ref["threshold"])
        self._assert_path(got, ref["equity_ideal"])

    def test_min_order_equity_matches_capital_py_logic(self):
        ref = _load()
        symbols = list(ref["closes"])
        closes, targets, flags = self._panel(ref, "TW", "FL", symbols)
        got = simulate(
            closes, targets, flags, 500.0, cost=ref["cost"], threshold=ref["threshold"],
            min_notional={symbol: 10.0 for symbol in symbols},
        )
        self._assert_path(got, ref["equity_min10_k500"])

    def test_trendfilter_equity_matches_tf_run(self):
        ref = _load()
        symbols = list(ref["tf_TW"])
        closes = {symbol: _floats(ref["closes"][symbol]) for symbol in symbols}
        targets = {symbol: _floats(ref["tf_TW"][symbol]) for symbol in symbols}
        flags = {symbol: ref["tf_FL"][symbol] for symbol in symbols}
        got = simulate(
            closes, targets, flags, 500.0, cost=ref["cost"], threshold=ref["threshold"],
            min_notional={symbol: 1.0 for symbol in symbols},
        )
        self._assert_path(got, ref["tf_equity_min1_k500"])


class UniverseReferenceTests(unittest.TestCase):
    def test_monthly_selection_matches_lib_universe(self):
        ref = _load()
        first_day = day_from_iso(ref["dates"][0])
        series = {
            symbol: DailySeries(symbol, first_day, _floats(ref["closes"][symbol]), _floats(ref["qvol"][symbol]))
            for symbol in ref["closes"]
        }
        for month, expected in ref["universe_by_month"].items():
            month_end = day_from_iso(f"{month}-01") - 1
            ranked = rank_candidates(series, month_end, set(), {})
            got = sorted(select_universe(ranked, ref["B"]))
            self.assertEqual(got, expected, f"Universum {month}")
