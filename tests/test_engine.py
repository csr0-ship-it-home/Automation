import json
import math
import unittest

from engine import data_sources, demo
from engine.indicators import drawdown_series, forward_return_stats, last_cross, percentile_rank, rsi, sma, yoy_series
from engine.macro import build_macro
from engine.run import build
from engine.universe import ASSETS, MACRO_SERIES


class IndicatorTests(unittest.TestCase):
    def test_sma(self):
        self.assertEqual(sma([1, 2, 3, 4], 2), [None, 1.5, 2.5, 3.5])

    def test_rsi_extremes(self):
        up = list(range(1, 40))
        self.assertEqual(rsi(up)[-1], 100.0)
        down = list(range(40, 1, -1))
        self.assertAlmostEqual(rsi(down)[-1], 0.0)

    def test_drawdown(self):
        self.assertAlmostEqual(drawdown_series([100, 120, 90], 252)[-1], -0.25)

    def test_percentile(self):
        self.assertEqual(percentile_rank([1, 2, 3, 4], 2), 0.5)

    def test_cross(self):
        fast = [1, 1, 3, 3]
        slow = [2, 2, 2, 2]
        self.assertEqual(last_cross(fast, slow), ("golden", 1))

    def test_forward_stats_clusters_episodes(self):
        vals = [100 * math.exp(0.001 * i) for i in range(300)]
        cond = [i in (10, 11, 12, 100) for i in range(300)]
        st = forward_return_stats(vals, cond, horizons=(21,))
        self.assertEqual(st["episodes"], 2)
        self.assertGreater(st["h21"]["avg"], 0)

    def test_yoy(self):
        s = [("2020-01-01", 100.0), ("2021-01-01", 103.0)]
        self.assertAlmostEqual(yoy_series(s)[-1][1], 3.0)


class ParserTests(unittest.TestCase):
    def test_yahoo(self):
        txt = json.dumps({"chart": {"result": [{"timestamp": [1700000000, 1700086400],
                                                 "indicators": {"quote": [{"close": [1, 2]}], "adjclose": [{"adjclose": [1.5, None]}]}}]}})
        self.assertEqual(data_sources.parse_yahoo_chart(txt), [("2023-11-14", 1.5)])

    def test_fred(self):
        txt = "observation_date,T10Y2Y\n2024-01-01,.\n2024-01-02,0.35\n"
        self.assertEqual(data_sources.parse_fred_csv(txt), [("2024-01-02", 0.35)])

    def test_stooq(self):
        txt = "Date,Open,High,Low,Close,Volume\n2024-01-02,1,2,0.5,1.7,100\n"
        self.assertEqual(data_sources.parse_stooq_csv(txt), [("2024-01-02", 1.7)])


class PipelineTests(unittest.TestCase):
    def test_demo_pipeline(self):
        from datetime import datetime, timezone
        prices = demo.prices([a["symbol"] for a in ASSETS])
        out = build(prices, demo.macro(MACRO_SERIES), {}, datetime.now(timezone.utc), is_demo=True)
        self.assertEqual(len(out["assets"]), len(ASSETS))
        for a in out["assets"]:
            self.assertTrue(0 <= a["score"] <= 100)
            for v in a["components"].values():
                self.assertTrue(-1 <= v <= 1)
        self.assertIn(out["regime"]["label"], ("Risk-On", "Neutral", "Risk-Off"))
        # second run: nothing new
        again = build(prices, demo.macro(MACRO_SERIES), out, datetime.now(timezone.utc), is_demo=True)
        self.assertFalse(any(a["new"] for a in again["alerts"]))

    def test_macro_alerts(self):
        raw = demo.macro(MACRO_SERIES)
        d = raw["SAHMREALTIME"][-1][0]
        raw["SAHMREALTIME"][-1] = (d, 0.7)
        m = build_macro(raw, MACRO_SERIES)
        self.assertIn("macro:sahm", [a["id"] for a in m["alerts"]])


if __name__ == "__main__":
    unittest.main()
