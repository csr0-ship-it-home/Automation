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


class SourceTests(unittest.TestCase):
    def test_tiingo(self):
        txt = json.dumps([{"date": "2024-01-02T00:00:00.000Z", "close": 10, "adjClose": 9.5}])
        self.assertEqual(data_sources.parse_tiingo(txt), [("2024-01-02", 9.5)])

    def test_fred_api(self):
        txt = json.dumps({"observations": [{"date": "2024-01-01", "value": "."}, {"date": "2024-01-02", "value": "0.35"}]})
        self.assertEqual(data_sources.parse_fred_api(txt), [("2024-01-02", 0.35)])

    def test_redacts_keys(self):
        self.assertNotIn("SECRET", data_sources._redact("https://x.org/a?series_id=A&api_key=SECRET&token=SECRET"))

    def test_yfinance_frame(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas not installed")
        idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
        cols = pd.MultiIndex.from_product([["SPY", "QQQ"], ["Open", "Close"]])
        frame = pd.DataFrame([[1, 2, 3, 4], [5, 6, 7, None]], index=idx, columns=cols)
        out = data_sources.frame_to_series(frame, ["SPY", "QQQ", "XLE"])
        self.assertEqual(out["SPY"], [("2024-01-02", 2.0), ("2024-01-03", 6.0)])
        self.assertEqual(out["QQQ"], [("2024-01-02", 4.0)])
        self.assertNotIn("XLE", out)

    def test_fallback_when_bulk_fails(self):
        from unittest import mock
        with mock.patch.object(data_sources, "fetch_yfinance_bulk", side_effect=RuntimeError("blocked")):
            prices, errors = data_sources.fetch_all_prices(
                ["SPY", "BAD"], fetch_one=lambda s: [("2024-01-01", 1.0)] if s == "SPY" else (_ for _ in ()).throw(RuntimeError("nope")))
        self.assertIn("SPY", prices)
        self.assertIn("BAD", errors)

    def test_blocked_host_fails_fast(self):
        from unittest import mock
        data_sources._host_failures["blocked.example"] = data_sources.HOST_FAILURE_LIMIT
        with mock.patch("urllib.request.urlopen") as op:
            with self.assertRaises(RuntimeError):
                data_sources._get("https://blocked.example/x")
            op.assert_not_called()


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

    def test_commentary_demo(self):
        from datetime import datetime, timezone
        from engine.run import add_commentary
        now = datetime.now(timezone.utc)
        prices = demo.prices([a["symbol"] for a in ASSETS])
        out = build(prices, demo.macro(MACRO_SERIES), {}, now, is_demo=True)
        add_commentary(out, now, is_demo=True)
        self.assertEqual([t["symbol"] for t in out["top5"]], [a["symbol"] for a in out["assets"][:5]])
        for t in out["top5"]:
            self.assertTrue(t["strengths"] and t["risks"] and t["watch"])
        self.assertTrue(out["news"]["themes"])
        self.assertTrue(out["news"]["brief"]["paragraphs"])

    def test_news_parsing_and_dedupe(self):
        from datetime import datetime, timezone
        from engine.news import parse_rss, tag_and_rank
        xml = ("<rss><channel>"
               "<item><title>Fed signals rate cut - Reuters</title><link>https://a.com/1</link><pubDate>Tue, 29 Sep 2026 14:00:00 GMT</pubDate></item>"
               "<item><title>Fed signals rate cut</title><link>https://b.com/2</link><pubDate>Tue, 29 Sep 2026 15:00:00 GMT</pubDate></item>"
               "<item><title>Old news about oil</title><link>https://c.com/3</link><pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item>"
               "<item><title>Bad link</title><link>javascript:alert(1)</link></item>"
               "</channel></rss>")
        items = parse_rss(xml, "Google News")
        self.assertEqual(len(items), 3)
        ranked = tag_and_rank(items, datetime(2026, 9, 30, tzinfo=timezone.utc))
        self.assertEqual(len(ranked), 1)
        self.assertIn("Fed & interest rates", ranked[0]["themes"])

    def test_ai_skipped_without_key(self):
        import os
        from engine import ai
        os.environ.pop("ANTHROPIC_API_KEY", None)
        self.assertIsNone(ai.write({}, [], [], [], {}))

    def test_runs_without_macro_data(self):
        from datetime import datetime, timezone
        prices = demo.prices([a["symbol"] for a in ASSETS])
        out = build(prices, {}, {}, datetime.now(timezone.utc), is_demo=True)
        self.assertEqual(len(out["assets"]), len(ASSETS))
        self.assertEqual(out["gauges"], [])

    def test_macro_alerts(self):
        raw = demo.macro(MACRO_SERIES)
        d = raw["SAHMREALTIME"][-1][0]
        raw["SAHMREALTIME"][-1] = (d, 0.7)
        m = build_macro(raw, MACRO_SERIES)
        self.assertIn("macro:sahm", [a["id"] for a in m["alerts"]])


if __name__ == "__main__":
    unittest.main()
