"""Guard published OHLCV provenance and no-lookahead volume observations."""
import json
import unittest
from pathlib import Path


class PublishedCandleAcceptance(unittest.TestCase):
    def test_published_candles_match_dated_official_close_series(self):
        path=Path("remote/system.json")
        if not path.exists():
            self.skipTest("No published feed in this checkout")
        feed=json.loads(path.read_text(encoding="utf-8"))
        rows=[row for group in feed.get("patterns",{}).get("signals",{}).values()
              for row in group]
        for row in rows:
            if not row.get("ohlcv_source_verified"):
                self.assertNotIn("volume_price_observation",row)
                continue
            with self.subTest(code=row.get("code")):
                closes=row["close_series"]
                candles=row["ohlcv"]
                self.assertEqual(len(candles),len(closes))
                self.assertGreaterEqual(len(candles),21)
                self.assertEqual([(c["date"],c["close"]) for c in candles],
                                 [(p["date"],p["close"]) for p in closes])
                self.assertTrue(all(isinstance(c["volume"],int) and c["volume"]>=0
                                    for c in candles))
                prior=candles[-21:-1]
                last=candles[-1]
                observation=row["volume_price_observation"]
                self.assertAlmostEqual(observation["prior_20_high"],
                                       max(c["high"] for c in prior),places=4)
                self.assertAlmostEqual(observation["prior_20_avg_volume_shares"],
                                       sum(c["volume"] for c in prior)/20,places=2)
                self.assertEqual(observation["latest_volume_shares"],last["volume"])
                self.assertEqual(observation["price_breakout"],
                                 last["close"]>max(c["high"] for c in prior))
                avg=sum(c["volume"] for c in prior)/20
                self.assertEqual(observation["volume_ratio"],
                                 round(last["volume"]/avg,2) if avg>0 else None)
                self.assertEqual(observation["confirmed_price_volume_breakout"],
                                 observation["price_breakout"] and
                                 observation["volume_expansion"])


if __name__=="__main__":
    unittest.main()
