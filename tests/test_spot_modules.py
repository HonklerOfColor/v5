"""Spot-Module (Paper): laufende Kerze, Rebalance-Schwelle, Mindestorder, Universum, Delisting,
Idempotenz, Live-Modus ohne Orders, Alarme, Schattenrechnung, Status, CSV, Konto-Check."""

from __future__ import annotations

import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from unified_bot.runner import Bot
from unified_bot.settings import base_settings, load_settings, namespace_from
from unified_bot.spot import client as spot_client
from unified_bot.spot.account_check import check_spot_account
from unified_bot.spot.broker import PaperSpotBroker
from unified_bot.spot.candles import DailyCandle, closed_only, day_from_iso, day_iso
from unified_bot.spot.client import SpotApiError
from unified_bot.spot.engine import TradeDecision, decide_trades
from unified_bot.spot.export import trades_to_csv
from unified_bot.spot.ledger import SpotLedger, SpotTrade
from unified_bot.spot.modules import TrendEnsembleModule, TrendFilterModule
from unified_bot.spot.params import DAY_MS, TREND_B, TREND_UNIVERSE_MIN_MEDIAN_USDT
from unified_bot.spot.runner import SpotRunner
from unified_bot.spot.specs import SpotSpec, floor_quantity, load_fallback_specs
from unified_bot.status_server import start_status_server
from unified_bot.spot.universe import excluded_by_name
from tests.fake_spot_client import FakeSpotClient, candles_from_closes, random_walk

TODAY = day_from_iso("2026-10-18")
RUN_MS = TODAY * DAY_MS + 6 * 60_000      # 00:06 UTC


def _rising(n: int, start: float = 10.0) -> list[float]:
    """Steigt jeden Tag, abwechselnd +3 % / +1 %: Breakout in jedem Fenster, σ90 > 0."""
    out = [start]
    for index in range(1, n):
        out.append(out[-1] * (1.03 if index % 2 else 1.01))
    return out


def _spec(symbol: str, min_usdt: float = 1.0, qprec: int = 6, status: str = "online") -> SpotSpec:
    base = symbol[:-4]
    return SpotSpec(symbol, base, "USDT", min_usdt, qprec, 2, status, open_time_ms=1_500_000_000_000)


def _client(symbols: list[str], n: int = 420, running_candle: bool = True, rising: tuple[str, ...] = ()) -> FakeSpotClient:
    first = TODAY - n
    candles, tickers, specs = {}, {}, {}
    for index, symbol in enumerate(symbols):
        closes = _rising(n + 1, 10.0 * (index + 1)) if symbol in rising else random_walk(n + 1, 50.0 * (index + 1), seed=index + 7)
        rows = candles_from_closes(first, closes, (len(symbols) - index) * 4e6)
        candles[symbol] = rows if running_candle else rows[:-1]
        tickers[symbol] = {"last": closes[-2], "usdt_volume": (len(symbols) - index) * 4e6}
        specs[symbol] = _spec(symbol)
    return FakeSpotClient(specs=specs, candles=candles, tickers=tickers)


def _module(cls, client, folder: str, mode: str = "paper", notify=None, capital: float = 500.0):
    cfg = base_settings()
    cfg.mode = mode
    return cls(cfg, client, Path(folder) / f"{cls.id}.json", notify=notify, capital=capital, enabled=True)


class RunningCandleTests(unittest.TestCase):
    def test_closed_only_drops_todays_candle(self):
        rows = [DailyCandle((TODAY - 1) * DAY_MS, 1, 1, 1, 1.0, 1), DailyCandle(TODAY * DAY_MS, 1, 1, 1, 99.0, 1)]
        kept = closed_only(rows, RUN_MS)
        self.assertEqual([candle.day for candle in kept], [TODAY - 1])
        kept_tomorrow = closed_only(rows, (TODAY + 1) * DAY_MS)
        self.assertEqual([candle.day for candle in kept_tomorrow], [TODAY - 1, TODAY])

    def test_module_never_uses_todays_candle(self):
        symbols = ["BTCUSDT", "ETHUSDT"]
        client = _client(symbols)
        for symbol in symbols:   # heutige Kerze extrem, damit sie auffallen würde
            rows = client.candles[symbol]
            last = rows[-1]
            client.candles[symbol] = rows[:-1] + [DailyCandle(last.ts, 1e6, 1e6, 1e6, 1e6, 1e9)]
        with tempfile.TemporaryDirectory() as folder:
            module = _module(TrendFilterModule, client, folder)
            report = module.run(RUN_MS)
            self.assertTrue(report["ok"], report)
            self.assertEqual(report["day"], day_iso(TODAY - 1))
            for symbol in symbols:
                yesterday = client.candles[symbol][-2].close
                self.assertEqual(module.last_meta["coins"][symbol]["close"], yesterday)
            for call in client.calls:
                if call[0] == "history":
                    self.assertEqual(call[3], RUN_MS)


class RebalanceThresholdTests(unittest.TestCase):
    def test_threshold_and_flag(self):
        equity, held = 1000.0, {"BTCUSDT": 100.0}
        prices = {"BTCUSDT": 50_000.0}
        below = decide_trades(equity, held, prices, {"BTCUSDT": 0.119}, {"BTCUSDT": False})[0]
        self.assertFalse(below.trade)                     # Delta 19 < 20 % von 119
        above = decide_trades(equity, held, prices, {"BTCUSDT": 0.13}, {"BTCUSDT": False})[0]
        self.assertTrue(above.trade)                      # Delta 30 > 20 % von 130
        self.assertEqual(above.reason, "threshold")
        flagged = decide_trades(equity, held, prices, {"BTCUSDT": 0.101}, {"BTCUSDT": True})[0]
        self.assertTrue(flagged.trade)                    # Signaländerung: immer
        self.assertEqual(flagged.reason, "flag")
        close_out = decide_trades(equity, held, prices, {"BTCUSDT": 0.0}, {"BTCUSDT": False})[0]
        self.assertTrue(close_out.trade)
        self.assertEqual(close_out.reason, "close_out")

    def test_min_notional_rules_from_capital_py(self):
        equity, held, prices = 500.0, {"XUSDT": 30.0}, {"XUSDT": 1.0}
        tiny_target = decide_trades(equity, held, prices, {"XUSDT": 0.01}, {"XUSDT": True}, min_notional={"XUSDT": 10.0})[0]
        self.assertEqual(tiny_target.target, 0.0)         # Ziel 5 USDT < 10 → Ziel 0, Position wird geschlossen
        self.assertTrue(tiny_target.trade)
        small_delta = decide_trades(equity, held, prices, {"XUSDT": 0.07}, {"XUSDT": True}, min_notional={"XUSDT": 10.0})[0]
        self.assertFalse(small_delta.trade)               # Delta 5 USDT < 10, kein Trade trotz Flag
        self.assertEqual(small_delta.reason, "below_min")


class MinOrderRoundingTests(unittest.TestCase):
    def test_floor_quantity_never_rounds_up(self):
        self.assertEqual(floor_quantity(0.0006249999, 6), 0.000624)
        self.assertEqual(floor_quantity(1.23456789, 4), 1.2345)
        self.assertEqual(floor_quantity(0.0, 6), 0.0)

    def test_broker_rounds_and_skips_below_min(self):
        broker = PaperSpotBroker()
        ledger = SpotLedger.fresh(500.0)
        spec = _spec("BTCUSDT", min_usdt=1.0, qprec=6)
        trade = broker.execute(ledger, TradeDecision("BTCUSDT", 50.0, 0.0, 50.0, True, "flag"), 80_000.0, spec, RUN_MS, 10.0).trade
        self.assertIsNotNone(trade)
        self.assertEqual(trade.side, "buy")
        self.assertEqual(round(trade.qty, 6), trade.qty)
        self.assertAlmostEqual(trade.price, 80_000.0 * 1.0005)
        self.assertAlmostEqual(trade.fee, trade.value_usdt * 0.001)
        self.assertLessEqual(trade.value_usdt, 50.0)
        self.assertAlmostEqual(ledger.cash, 500.0 - trade.value_usdt - trade.fee)
        spec20 = _spec("RNNNNUSDT", min_usdt=20.0, qprec=4)
        skipped = broker.execute(ledger, TradeDecision("RNNNNUSDT", 19.5, 0.0, 19.5, True, "flag"), 2.0, spec20, RUN_MS, 10.0)
        self.assertIsNone(skipped.trade)
        self.assertIn("Mindestorder", skipped.note)
        self.assertNotIn("RNNNNUSDT", ledger.holdings)
        sell_all = broker.execute(ledger, TradeDecision("BTCUSDT", 0.0, 50.0, -50.0, True, "close_out"), 80_000.0, spec, RUN_MS, 10.0).trade
        self.assertEqual(sell_all.qty, trade.qty)
        self.assertNotIn("BTCUSDT", ledger.holdings)
        self.assertAlmostEqual(sell_all.price, 80_000.0 * 0.9995)

    def test_fallback_specs_are_the_offline_reference(self):
        specs = load_fallback_specs()
        self.assertIn("BTCUSDT", specs)
        self.assertEqual(specs["BTCUSDT"].min_trade_usdt, 1.0)
        self.assertEqual(specs["BTCUSDT"].quantity_precision, 6)


class UniverseTests(unittest.TestCase):
    def test_name_exclusions(self):
        for base in ("USDC", "PAXG", "WBTC", "TSLA", "USDCB", "BTC3L", "ETH5S", "rSPY", "rNVDA", "rNNNN", "preSPCX"):
            self.assertTrue(excluded_by_name(base), base)
        for base in ("BTC", "ETH", "JUP", "SOL", "DOGE", "RENDER", "RAY", "PRE"):
            self.assertFalse(excluded_by_name(base), base)

    def test_bitget_tokenized_stocks_are_not_candidates(self):
        specs = load_fallback_specs()
        pool = [spec for spec in specs.values() if spec.quote == "USDT" and spec.online and not excluded_by_name(spec.base)]
        self.assertLess(len(pool), 600)                       # 2913 von 3421 sind rXXX-Tokenized-Stocks
        self.assertTrue(all(not spec.base.startswith("r") for spec in pool))
        self.assertIn("BTCUSDT", {spec.symbol for spec in pool})

    def test_candidate_without_candles_is_skipped_not_fatal(self):
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        client = _client(symbols)
        client.specs["ODDUSDT"] = _spec("ODDUSDT")
        client.tickers["ODDUSDT"] = {"last": 1.0, "usdt_volume": 9e9}
        client.candle_errors["ODDUSDT"] = SpotApiError("48001", "Parameter validation failed null", "/candles")
        with tempfile.TemporaryDirectory() as folder:
            module = _module(TrendEnsembleModule, client, folder)
            universe = module.select_universe(TODAY - 1, client.get_symbols(), RUN_MS)
        self.assertEqual(sorted(universe), symbols)

    def test_selection_applies_exclusions_min_history_and_volume(self):
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "USDCUSDT", "NEWUSDT", "THINUSDT"]
        client = _client(symbols)
        month_end = day_from_iso("2026-09-30")
        # NEWUSDT: nur 40 Tage Historie bis zum Monatsende. THINUSDT: Volumen unter 2 Mio.
        client.candles["NEWUSDT"] = [row for row in client.candles["NEWUSDT"] if row.day > month_end - 40]
        client.candles["THINUSDT"] = [
            DailyCandle(row.ts, row.open, row.high, row.low, row.close, TREND_UNIVERSE_MIN_MEDIAN_USDT / 2)
            for row in client.candles["THINUSDT"]
        ]
        with tempfile.TemporaryDirectory() as folder:
            module = _module(TrendEnsembleModule, client, folder)
            universe = module.select_universe(TODAY - 1, client.get_symbols(), RUN_MS)
        self.assertEqual(sorted(universe), ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        self.assertEqual(module.universe_selected_at, "2026-09-30")
        reasons = {row["symbol"]: row["reason"] for row in module.universe_report}
        self.assertNotIn("USDCUSDT", reasons)   # Namensregel greift vor dem Datenabruf
        self.assertTrue(all(call[1] != "USDCUSDT" for call in client.calls if call[0] == "history"))

    def test_top_b_by_median_volume(self):
        symbols = [f"C{index:02d}USDT" for index in range(14)]
        client = _client(symbols)
        with tempfile.TemporaryDirectory() as folder:
            module = _module(TrendEnsembleModule, client, folder)
            universe = module.select_universe(TODAY - 1, client.get_symbols(), RUN_MS)
        self.assertEqual(len(universe), TREND_B)
        self.assertEqual(universe, symbols[:TREND_B])     # Volumen fällt mit dem Index


class DelistingTests(unittest.TestCase):
    def test_delisted_coin_is_closed_at_last_price(self):
        symbols = ["AAAUSDT", "BBBUSDT", "CCCUSDT"]
        client = _client(symbols, rising=("AAAUSDT",))
        with tempfile.TemporaryDirectory() as folder:
            module = _module(TrendEnsembleModule, client, folder)
            report = module.run(RUN_MS)
            self.assertTrue(report["ok"], report)
            self.assertGreater(module.ledger.qty("AAAUSDT"), 0.0)
            last_close = client.candles["AAAUSDT"][-2].close
            # Delisting: Symbol offline, keine Kerzen mehr, kein Ticker
            client.specs["AAAUSDT"] = _spec("AAAUSDT", status="offline")
            del client.candles["AAAUSDT"]
            del client.tickers["AAAUSDT"]
            report2 = module.run(RUN_MS + DAY_MS)
            self.assertTrue(report2["ok"], report2)
            self.assertEqual(module.ledger.qty("AAAUSDT"), 0.0)
            sells = [trade for trade in module.ledger.trades if trade.symbol == "AAAUSDT" and trade.side == "sell"]
            self.assertEqual(len(sells), 1)
            self.assertAlmostEqual(sells[0].price, last_close * 0.9995)
            self.assertNotIn("AAAUSDT", module.shadow.positions)


class IdempotenceTests(unittest.TestCase):
    def test_one_run_per_day_survives_restart(self):
        client = _client(["BTCUSDT", "ETHUSDT"])
        with tempfile.TemporaryDirectory() as folder:
            module = _module(TrendFilterModule, client, folder)
            self.assertFalse(module.due(TODAY * DAY_MS + 2 * 60_000))     # 00:02: vor dem Puffer
            self.assertTrue(module.due(RUN_MS))
            self.assertTrue(module.run(RUN_MS)["ok"])
            trades = len(module.ledger.trades)
            self.assertIsNone(module.tick(RUN_MS + 3_600_000))
            restarted = _module(TrendFilterModule, client, folder)             # neuer Prozess, gleiche Datei
            self.assertEqual(restarted.last_run_day, TODAY)
            self.assertFalse(restarted.due(RUN_MS + 5 * 3_600_000))
            self.assertIsNone(restarted.tick(RUN_MS + 5 * 3_600_000))
            self.assertEqual(len(restarted.ledger.trades), trades)
            self.assertTrue(restarted.due(RUN_MS + DAY_MS))

    def test_api_error_retries_later_and_keeps_day_open(self):
        client = _client(["BTCUSDT", "ETHUSDT"])
        client.symbols_error = SpotApiError("transport", "down", "/symbols")
        with tempfile.TemporaryDirectory() as folder:
            module = _module(TrendFilterModule, client, folder)
            report = module.run(RUN_MS)
            self.assertFalse(report["ok"])
            self.assertIsNone(module.last_run_day)
            self.assertFalse(module.due(RUN_MS + 60_000))
            self.assertTrue(module.due(RUN_MS + 11 * 60_000))
            client.symbols_error = None
            self.assertTrue(module.run(RUN_MS + 11 * 60_000)["ok"])


class LiveModeTests(unittest.TestCase):
    def test_spot_modules_stay_paper_when_bot_is_live(self):
        client = _client(["BTCUSDT", "ETHUSDT"])
        with tempfile.TemporaryDirectory() as folder:
            module = _module(TrendFilterModule, client, folder, mode="live")
            report = module.run(RUN_MS)
            self.assertTrue(report["ok"], report)
            self.assertTrue(any("PAPER" in note for note in report["notes"]))
            self.assertEqual(client.signed_calls, [])
            self.assertEqual(module.status()["mode"], "paper")
            self.assertEqual(module.status()["bot_mode"], "live")
            self.assertEqual(module.broker.mode, "paper")

    def test_spot_client_has_no_order_methods(self):
        names = [name for name in dir(spot_client.BitgetSpotClient) if not name.startswith("_")]
        for name in names:
            lowered = name.lower()
            self.assertNotIn("order", lowered)
            self.assertNotIn("place", lowered)
            self.assertNotIn("transfer", lowered)
            self.assertNotIn("withdraw", lowered)
        with self.assertRaises(SystemExit):
            TrendFilterModule(base_settings(), FakeSpotClient(), Path(tempfile.mkdtemp()) / "x.json", broker=object())


class AlarmTests(unittest.TestCase):
    def _module_with_history(self, cls, rows, trades=0, month="2026-10"):
        client = _client(["BTCUSDT", "ETHUSDT"])
        sent = []
        folder = tempfile.mkdtemp()
        module = _module(cls, client, folder, notify=sent.append)
        module.equity_history = rows
        for index in range(trades):
            module.ledger.trades.append(SpotTrade(day_from_iso(f"{month}-05") * DAY_MS + index, "BTCUSDT", "buy", 0.001, 1.0, 0.0, 1.0, "test"))
        return module, sent

    @staticmethod
    def _rows(paper: list[float], shadow: list[float], start_day: int = TODAY - 200):
        return [
            {"day": start_day + index, "date": day_iso(start_day + index), "paper": p, "shadow": s, "exposure": 0.5}
            for index, (p, s) in enumerate(zip(paper, shadow))
        ]

    def test_trend_drawdown_and_deviation(self):
        module, sent = self._module_with_history(TrendEnsembleModule, self._rows([500, 520, 440], [500, 520, 440]))
        reasons = module.alarm_checks(TODAY - 1)
        self.assertEqual(len(reasons), 1)
        self.assertIn("Drawdown", reasons[0])
        module.equity_history = self._rows([500] * 95, [500] * 5 + [500 + 0.2 * index for index in range(90)])
        reasons = module.alarm_checks(TODAY - 1)
        self.assertTrue(any("Abweichung" in reason for reason in reasons), reasons)
        module.equity_history = self._rows([500, 510, 505], [500, 510, 515])   # 2 pp: unter 3
        self.assertEqual(module.alarm_checks(TODAY - 1), [])
        self.assertEqual(sent, [])

    def test_trendfilter_thresholds_and_single_notification(self):
        module, sent = self._module_with_history(TrendFilterModule, self._rows([500, 300, 240], [500, 300, 240]))
        self.assertTrue(any("Drawdown" in r for r in module.alarm_checks(TODAY - 1)))   # 52 % > 50 %
        module.equity_history = self._rows([500, 400], [500, 400])                    # 20 %: unter 50 %
        self.assertEqual(module.alarm_checks(TODAY - 1), [])
        module.equity_history = self._rows([500] * 10, [500] * 9 + [530])              # 6 pp > 5
        self.assertTrue(any("Abweichung" in r for r in module.alarm_checks(TODAY - 1)))
        module, sent = self._module_with_history(TrendFilterModule, self._rows([500], [500]), trades=26)
        module._evaluate_alarms(day_from_iso("2026-10-17"))
        self.assertTrue(module.alarm)
        self.assertEqual(len(sent), 1)
        self.assertIn("26 Trades", sent[0])
        module._evaluate_alarms(day_from_iso("2026-10-18"))   # gleicher Grund: keine zweite Meldung
        self.assertEqual(len(sent), 1)
        module.ledger.trades.clear()
        module._evaluate_alarms(day_from_iso("2026-10-18"))
        self.assertFalse(module.alarm)


class ShadowTests(unittest.TestCase):
    def test_shadow_runs_same_rules_without_min_order_and_records_deviation(self):
        client = _client(["BTCUSDT", "ETHUSDT"])
        with tempfile.TemporaryDirectory() as folder:
            module = _module(TrendFilterModule, client, folder)
            report = module.run(RUN_MS)
            self.assertTrue(report["ok"], report)
            targets = module.last_targets
            turnover = sum(abs(weight) * 500.0 for weight in targets.values())
            self.assertAlmostEqual(module.shadow.equity, 500.0 - 0.0015 * turnover, places=9)
            for symbol, weight in targets.items():
                if weight > 0:
                    self.assertAlmostEqual(module.shadow.positions[symbol], weight * 500.0, places=9)
                    self.assertAlmostEqual(module.shadow.last_prices[symbol], client.candles[symbol][-2].close)
            status = module.status()
            self.assertEqual(status["equity_history"][-1]["shadow"], round(module.shadow.equity, 8))
            self.assertIsInstance(status["deviation_pp"], float)
            self.assertEqual(status["deviation_window_days"], 1)
            # Deviation: Paper kauft 0,1 % über dem Schluss (Ticker) + Slippage, der Schatten zum Schluss.
            paper_return = status["equity"] / 500.0 - 1.0
            shadow_return = module.shadow.equity / 500.0 - 1.0
            self.assertAlmostEqual(status["deviation_pp"], (paper_return - shadow_return) * 100.0, places=3)


class StatusAndExportTests(unittest.TestCase):
    def test_status_endpoints_and_csv(self):
        client = _client(["BTCUSDT", "ETHUSDT"])
        cfg = base_settings()
        with tempfile.TemporaryDirectory() as folder:
            bot = Bot(cfg, state_path=Path(folder) / "state.json", kill_path=Path(folder) / "KILL")
            runner = SpotRunner(cfg, Path(folder), client=client)
            bot.attach_spot(runner)
            runner.by_id[TrendFilterModule.id].run(RUN_MS)
            server = start_status_server(bot, "127.0.0.1", 0)
            port = server.server_address[1]
            import threading

            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v5/spot", timeout=5) as response:
                    index = json.loads(response.read())
                self.assertIn(TrendFilterModule.id, index["modules"])
                self.assertEqual(index["mode"], "paper")
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v5/spot/{TrendFilterModule.id}", timeout=5) as response:
                    body = json.loads(response.read())
                for key in ("equity", "positions", "exposure", "trades", "drawdown", "deviation_pp", "last_run", "alarm", "shadow"):
                    self.assertIn(key, body)
                self.assertEqual(body["last_run"]["signal_day"], day_iso(TODAY - 1))
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v5/spot/{TrendFilterModule.id}/trades.csv", timeout=5) as response:
                    csv_text = response.read().decode("utf-8")
                self.assertTrue(csv_text.startswith("datum_utc;symbol;seite;menge;preis;gebuehr_usdt;wert_usdt"))
                self.assertEqual(len(csv_text.strip().splitlines()), 1 + body["trades"]["count"])
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
                    page = response.read().decode("utf-8")
                self.assertIn("Spot-Module (Paper)", page)
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/agent/status", timeout=5) as response:
                    status = json.loads(response.read())
                self.assertIn("spot", status)
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v5/spot/nope", timeout=5)
                    self.fail("404 erwartet")
                except urllib.error.HTTPError as exc:
                    self.assertEqual(exc.code, 404)
                    exc.close()
            finally:
                server.shutdown()
                server.server_close()

    def test_csv_columns(self):
        trade = SpotTrade(RUN_MS, "BTCUSDT", "buy", 0.001234, 80_000.5, 0.0987, 98.7, "flag")
        text = trades_to_csv([trade], "spot_trendfilter_btceth")
        lines = text.strip().splitlines()
        self.assertEqual(lines[0].split(";")[:7], ["datum_utc", "symbol", "seite", "menge", "preis", "gebuehr_usdt", "wert_usdt"])
        self.assertEqual(lines[1].split(";")[:4], ["2026-10-18 00:06:00", "BTCUSDT", "Kauf", "0.001234"])

    def test_bot_without_spot_still_runs(self):
        cfg = base_settings()
        with tempfile.TemporaryDirectory() as folder:
            bot = Bot(cfg, state_path=Path(folder) / "state.json", kill_path=Path(folder) / "KILL")
            bot.run_cycle({}, now_ms=RUN_MS)
            self.assertIsNone(bot.spot_index_payload())
            self.assertEqual(bot.status_payload()["spot"], {})


class SettingsTests(unittest.TestCase):
    def test_spot_settings_from_config(self):
        cfg = namespace_from({"SPOT_TREND_CAPITAL_USDT": 800, "SPOT_TF_CAPITAL_USDT": 250, "SPOT_TF_ENABLED": False})
        settings = load_settings(cfg)
        self.assertEqual(settings.spot_capital["spot_trend_ensemble"], 800.0)
        self.assertEqual(settings.spot_capital["spot_trendfilter_btceth"], 250.0)
        self.assertFalse(settings.spot_enabled["spot_trendfilter_btceth"])
        self.assertTrue(settings.spot_modules_enabled)
        with self.assertRaises(SystemExit):
            load_settings(namespace_from({"SPOT_TREND_CAPITAL_USDT": 0}))


class AccountCheckTests(unittest.TestCase):
    def test_placeholder_keys_do_not_call_the_exchange(self):
        client = FakeSpotClient()
        result = check_spot_account(base_settings(), client)
        self.assertEqual(result["verdict"], "nicht prüfbar")
        self.assertEqual(client.signed_calls, [])

    def test_readable_account_reports_fields_without_secrets(self):
        cfg = base_settings()
        cfg.api_key, cfg.secret_key, cfg.passphrase = "k" * 20, "s" * 40, "p" * 8
        client = FakeSpotClient()
        client.account_info = {"userId": "9711026741", "authorities": ["readonly", "spot_trade"], "parentId": "1"}
        client.assets = [{"coin": "USDT", "available": "123.45"}]
        result = check_spot_account(cfg, client)
        self.assertTrue(result["uid_matches"])
        self.assertTrue(result["spot_trade_permission"])
        self.assertEqual(result["usdt_available"], 123.45)
        self.assertTrue(result["btcusdt_online"])
        dumped = json.dumps(result)
        self.assertNotIn("k" * 20, dumped)
        self.assertNotIn("s" * 40, dumped)
