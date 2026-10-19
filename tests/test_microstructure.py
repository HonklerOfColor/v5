"""Mikrostruktur-Messungen auf synthetischen Minutenkerzen. Kein Netz."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from gridbot.candles import Candle
from research.costs import Costs
from research.funding_window import funding_windows, size_bucket, summarize
from research.micro import HOUR, MINUTE, hourly_atr_per_minute, price_at, resample_hourly
from research.weekend import THRESHOLD, mondays_between, simulate, weekend_windows
from research.wicks import detect_wicks, recovered, simulate_fade


def utc(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> int:
    return int(datetime(y, m, d, hh, mm, tzinfo=timezone.utc).timestamp() * 1000)


def flat_minutes(start_ts: int, n: int, price: float = 100.0, wick: float = 0.1) -> list[Candle]:
    """Seitwärts: jede Minute Hoch/Tief ±wick um den Preis, Schluss = Preis."""
    return [Candle(start_ts + i * MINUTE, price, price + wick, price - wick, price, 1.0) for i in range(n)]


class AtrTests(unittest.TestCase):
    def test_resample_groups_by_hour(self):
        candles = flat_minutes(0, 150)
        candles[70] = Candle(70 * MINUTE, 100.0, 105.0, 99.0, 101.0, 1.0)
        hourly = resample_hourly(candles)
        self.assertEqual([h.ts for h in hourly], [0, HOUR, 2 * HOUR])
        self.assertEqual(hourly[1].high, 105.0)
        self.assertEqual(hourly[1].low, 99.0)
        self.assertEqual(hourly[1].close, 100.0)  # letzte Minute der Stunde

    def test_minute_atr_uses_only_completed_hours(self):
        # 20 Stunden flach (Range 0,2), Stunde 20 mit großer Kerze: deren ATR darf erst ab Stunde 21 gelten
        candles = flat_minutes(0, 22 * 60)
        candles[20 * 60 + 5] = Candle((20 * 60 + 5) * MINUTE, 100.0, 120.0, 100.0, 100.0, 1.0)
        atrs = hourly_atr_per_minute(candles, 14)
        self.assertIsNone(atrs[13 * 60 + 59])
        self.assertAlmostEqual(atrs[20 * 60 + 30], 0.2, places=6)  # Stunde 20 noch nicht abgeschlossen
        self.assertGreater(atrs[21 * 60], 1.0)  # jetzt zählt die große Stunde


class WickTests(unittest.TestCase):
    def setUp(self):
        self.candles = flat_minutes(0, 20 * 60)  # ATR(14) auf 1h-Basis = 0,2
        self.atrs = hourly_atr_per_minute(self.candles, 14)

    def test_detects_low_wick_and_recovery(self):
        i = 16 * 60
        # Tief 1,0 unter dem Vorschluss (5 × ATR), Schluss zurück bei 99,95: 95 % zurückgeholt
        self.candles[i] = Candle(i * MINUTE, 100.0, 100.1, 99.0, 99.95, 1.0)
        events = detect_wicks(self.candles, self.atrs)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].side, "low")
        self.assertAlmostEqual(events[0].depth_atr, 5.0, places=6)
        self.assertTrue(recovered(self.candles, events[0], 15))

    def test_no_recovery_when_price_stays_down(self):
        i = 16 * 60
        self.candles[i] = Candle(i * MINUTE, 100.0, 100.1, 99.0, 99.0, 1.0)
        for k in range(i + 1, i + 61):
            self.candles[k] = Candle(k * MINUTE, 99.0, 99.3, 98.9, 99.0, 1.0)
        events = [e for e in detect_wicks(self.candles, self.atrs) if e.side == "low"]
        self.assertEqual(len(events), 1)
        self.assertFalse(recovered(self.candles, events[0], 15))
        self.assertFalse(recovered(self.candles, events[0], 60))
        # 61 Minuten später zurück: zählt nicht mehr für 60
        self.candles[i + 61] = Candle((i + 61) * MINUTE, 99.0, 100.0, 99.0, 100.0, 1.0)
        self.assertFalse(recovered(self.candles, events[0], 60))

    def test_high_wick_is_mirrored(self):
        i = 16 * 60
        self.candles[i] = Candle(i * MINUTE, 100.0, 101.0, 99.9, 100.0, 1.0)
        events = detect_wicks(self.candles, self.atrs)
        self.assertEqual([e.side for e in events], ["high"])
        self.assertTrue(recovered(self.candles, events[0], 15))

    def test_small_moves_and_gaps_are_not_events(self):
        i = 16 * 60
        self.candles[i] = Candle(i * MINUTE, 100.0, 100.1, 99.5, 100.0, 1.0)  # 2,5 × ATR: kein Ereignis
        self.assertEqual(detect_wicks(self.candles, self.atrs), [])
        # Sprung nach 10 Minuten Lücke: kein Docht
        j = 17 * 60
        self.candles[j] = Candle(j * MINUTE + 10 * MINUTE, 100.0, 100.1, 98.0, 100.0, 1.0)
        self.candles[j + 1] = Candle(j * MINUTE + 11 * MINUTE, 100.0, 100.1, 99.9, 100.0, 1.0)
        self.assertEqual(detect_wicks(self.candles, self.atrs), [])

    def test_fade_fills_at_limit_and_exits_at_target_as_maker(self):
        i = 16 * 60
        # Limit 100 − 0,4 = 99,6; Tief 99,5 darunter, Eröffnung darüber; Schluss 99,95 über Ziel 99,9
        self.candles[i] = Candle(i * MINUTE, 100.0, 100.1, 99.5, 99.95, 1.0)
        result = simulate_fade(self.candles, self.atrs, Costs(), {}, "long", notional=50.0)
        self.assertEqual(result["trades"], 1)
        self.assertEqual(result["exits"], {"ziel": 1})
        self.assertEqual(result["taker_fees"], 0.0)
        self.assertAlmostEqual(result["gross"], 50.0 / 99.6 * 0.3, places=6)
        self.assertGreater(result["net"], 0.0)

    def test_fade_rejects_candle_opening_below_limit(self):
        i = 16 * 60
        self.candles[i] = Candle(i * MINUTE, 99.5, 99.6, 99.4, 99.5, 1.0)  # eröffnet unter 99,6
        result = simulate_fade(self.candles, self.atrs, Costs(), {}, "long")
        self.assertEqual(result["trades"], 0)

    def test_fade_stop_beats_target_in_same_candle(self):
        i = 16 * 60
        # Tief 99,1 unter Stop 99,2, Schluss trotzdem über Ziel: Stop zählt, Taker-Fee
        self.candles[i] = Candle(i * MINUTE, 100.0, 100.1, 99.1, 99.95, 1.0)
        result = simulate_fade(self.candles, self.atrs, Costs(), {}, "long")
        self.assertEqual(result["exits"], {"stop": 1})
        self.assertGreater(result["taker_fees"], 0.0)
        self.assertLess(result["net"], 0.0)

    def test_fade_time_stop_after_60_minutes(self):
        i = 16 * 60
        self.candles[i] = Candle(i * MINUTE, 100.0, 100.1, 99.5, 99.7, 1.0)
        for k in range(i + 1, i + 70):
            self.candles[k] = Candle(k * MINUTE, 99.7, 99.8, 99.6, 99.7, 1.0)
        result = simulate_fade(self.candles, self.atrs, Costs(), {}, "long")
        self.assertEqual(result["exits"], {"zeit": 1})


class WeekendTests(unittest.TestCase):
    def build(self) -> list[Candle]:
        # Do 2026-07-23 00:00 bis Di 2026-08-11 00:00, Preis stückweise konstant mit Sprüngen an den Fenstern
        start, end = utc(2026, 7, 23), utc(2026, 8, 11)
        marks = {
            utc(2026, 7, 27, 13, 0): 102.0,  # Montag 1: Wochenende +2 %
            utc(2026, 7, 27, 13, 30): 101.0,  # erste Stunde −1 %
            utc(2026, 7, 27, 14, 30): 100.5,  # Tag −1,5 %
            utc(2026, 7, 27, 20, 0): 100.5,
            utc(2026, 7, 31, 19, 0): 100.0,  # Freitag 2, vor dem Schluss
            utc(2026, 8, 3, 13, 0): 99.0,  # Montag 2: Wochenende −1 % (unter Schwelle)
            utc(2026, 8, 3, 13, 30): 99.5,
            utc(2026, 8, 3, 14, 30): 99.2,
            utc(2026, 8, 7, 19, 0): 100.0,
            utc(2026, 8, 10, 13, 0): 104.0,  # Montag 3: +4 %, Tag weiter +1 %
            utc(2026, 8, 10, 13, 30): 104.0,
            utc(2026, 8, 10, 14, 0): 105.04,  # vor 14:30, damit der Schluss 14:29 ihn trägt
        }
        out = []
        price = 100.0
        ts = start
        while ts < end:
            if ts in marks:
                price = marks[ts]
            out.append(Candle(ts, price, price, price, price, 1.0))
            ts += MINUTE
        return out

    def test_mondays_need_friday_close_in_range(self):
        mondays = mondays_between(utc(2026, 7, 23), utc(2026, 8, 11))
        self.assertEqual([datetime.fromtimestamp(m / 1000, tz=timezone.utc).strftime("%m-%d") for m in mondays], ["07-27", "08-03", "08-10"])
        # beginnt die Reihe erst Samstag, fehlt der Freitag-Schluss der ersten Woche
        self.assertEqual(len(mondays_between(utc(2026, 7, 25), utc(2026, 8, 11))), 2)

    def test_windows_measure_the_right_moves(self):
        windows = weekend_windows(self.build())
        self.assertEqual([w["monday"] for w in windows], ["2026-07-27", "2026-08-03", "2026-08-10"])
        w = windows[0]
        self.assertAlmostEqual(w["move_weekend"], 0.02, places=9)
        self.assertAlmostEqual(w["move_h1"], 101.0 / 102.0 - 1, places=9)
        self.assertAlmostEqual(w["move_day"], 100.5 / 102.0 - 1, places=9)
        self.assertAlmostEqual(windows[1]["move_weekend"], -0.01, places=9)
        self.assertAlmostEqual(windows[2]["move_h1"], 0.01, places=9)

    def test_fade_simulation_filters_and_signs(self):
        windows = weekend_windows(self.build())
        costs = Costs()
        fade = simulate(windows, costs, {}, "h1", "fade")
        self.assertEqual(fade["trades"], 2)  # Woche 2 liegt unter 1,5 %
        self.assertEqual([t["side"] for t in fade["trade_list"]], ["short", "short"])
        # Woche 1: Short 102 → 101 ist +0,98 % brutto minus Kosten; Woche 3: Short 104 → 105,04 verliert
        self.assertGreater(fade["trade_list"][0]["net"], 0.0)
        self.assertLess(fade["trade_list"][1]["net"], 0.0)
        follow = simulate(windows, costs, {}, "h1", "follow")
        self.assertEqual(follow["trades"], 2)
        self.assertLess(follow["trade_list"][0]["net"], 0.0)
        self.assertGreater(THRESHOLD, 0.01)

    def test_price_at_tolerates_small_gaps_only(self):
        candles = flat_minutes(utc(2026, 7, 27, 12, 0), 60)
        self.assertEqual(price_at(candles, utc(2026, 7, 27, 13, 0)), 100.0)
        self.assertEqual(price_at(candles, utc(2026, 7, 27, 13, 20)), 100.0)  # 20 Minuten alt
        self.assertIsNone(price_at(candles, utc(2026, 7, 27, 13, 40)))  # 40 Minuten alt


class FundingWindowTests(unittest.TestCase):
    def test_windows_and_buckets(self):
        start = utc(2026, 8, 1)  # 00:00 UTC ist ein Funding-Zeitpunkt
        candles = []
        for i in range(24 * 60):
            ts = start + i * MINUTE
            price = 100.0
            if utc(2026, 8, 1, 7, 30) <= ts < utc(2026, 8, 1, 8, 0):
                price = 99.0  # 30 Minuten vor 08:00 um 1 % tiefer
            elif ts >= utc(2026, 8, 1, 8, 0):
                price = 100.5
            candles.append(Candle(ts, price, price, price, price, 1.0))
        rates = {utc(2026, 8, 1, 0, 0): 0.0001, utc(2026, 8, 1, 8, 0): 0.0003, utc(2026, 8, 1, 16, 0): -0.00005, utc(2026, 8, 2, 0, 0): 0.0001}
        rows = funding_windows(candles, rates)
        # 00:00 hat keine 30 Minuten davor, 02.08. 00:00 keine danach: zwei Fenster bleiben
        self.assertEqual([r["ts"] for r in rows], [utc(2026, 8, 1, 8, 0), utc(2026, 8, 1, 16, 0)])
        r8 = rows[0]
        self.assertEqual((r8["sign"], r8["size"]), ("pos", "1-3bp"))
        self.assertAlmostEqual(r8["before"], 99.0 / 100.0 - 1, places=9)  # Schluss 07:59 gegen Schluss 07:29
        self.assertAlmostEqual(r8["after"], 100.5 / 99.0 - 1, places=9)
        self.assertEqual((rows[1]["sign"], rows[1]["size"]), ("neg", "<1bp"))
        summary = summarize(rows)
        self.assertEqual(summary["all"]["n"], 2)
        self.assertEqual(summary["pos"]["n"], 1)
        self.assertIn("pos/1-3bp", summary)
        self.assertAlmostEqual(summary["pos"]["before_bp"], -100.0, places=6)

    def test_size_buckets_are_fixed(self):
        self.assertEqual(size_bucket(0.0001), "=1bp")
        self.assertEqual(size_bucket(-0.0001), "=1bp")
        self.assertEqual(size_bucket(0.00005), "<1bp")
        self.assertEqual(size_bucket(0.00025), "1-3bp")
        self.assertEqual(size_bucket(0.0005), ">3bp")


if __name__ == "__main__":
    unittest.main()
