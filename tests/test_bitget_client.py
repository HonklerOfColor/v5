"""Blättern in get_history_candles gegen einen gefälschten Endpunkt. Kein Netz."""

from __future__ import annotations

import unittest

from bitget_client import BitgetClient

HOUR = 3_600_000


class FakeHistory:
    """Bildet /api/v2/mix/market/history-candles nach: endTime ist die Schlusszeit
    der letzten gelieferten Kerze (einschließlich), höchstens `limit` Kerzen, neueste zuerst."""

    def __init__(self, first_open: int, count: int):
        self.opens = [first_open + k * HOUR for k in range(count)]
        self.calls: list[int] = []

    def __call__(self, path: str, params: dict | None = None) -> dict:
        assert path == "/api/v2/mix/market/history-candles"
        end_time = int(params["endTime"])
        limit = int(params["limit"])
        self.calls.append(end_time)
        page = [ts for ts in self.opens if ts + HOUR <= end_time][-limit:]
        return {"code": "00000", "data": [[str(ts), "1", "2", "0.5", "1.5", "10", "10"] for ts in reversed(page)]}


class HistoryPagingTests(unittest.TestCase):
    def setUp(self):
        self.client = BitgetClient(sleep=lambda s: None)

    def test_no_candle_missing_at_page_boundary(self):
        first = 1_700_000_000_000 - 1_700_000_000_000 % HOUR
        fake = FakeHistory(first, 500)
        self.client.public_get = fake
        start = first + 50 * HOUR
        end = first + 350 * HOUR
        rows = self.client.get_history_candles("BTCUSDT", "1H", start, end)
        stamps = [int(r[0]) for r in rows]
        self.assertEqual(stamps, list(range(start, end, HOUR)))  # end ist die offene Stunde, nicht enthalten
        self.assertEqual(len(stamps), 300)
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(fake.calls[1], stamps[100])  # zweite Seite endet genau an der ältesten Kerze der ersten

    def test_terminates_when_history_is_exhausted(self):
        first = 1_700_000_000_000 - 1_700_000_000_000 % HOUR
        fake = FakeHistory(first, 250)
        self.client.public_get = fake
        rows = self.client.get_history_candles("BTCUSDT", "1H", first - 1000 * HOUR, first + 250 * HOUR)
        self.assertEqual(len(rows), 250)
        self.assertEqual(int(rows[0][0]), first)
        self.assertLessEqual(len(fake.calls), 3)


if __name__ == "__main__":
    unittest.main()
