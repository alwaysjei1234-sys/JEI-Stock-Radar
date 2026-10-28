import unittest

from scripts.audit_feed_health import check


class FeedAuditTests(unittest.TestCase):
    def test_missing_market_diagnostics_are_reported_without_crashing(self):
        self.assertEqual(check({"market": None}), [])
        self.assertEqual(check({"market": "invalid"}), [])
        self.assertEqual(check({"market": {"live_diagnostics": None, "partial_live": None}}), [])

    def test_open_market_with_insufficient_coverage_is_flagged(self):
        feed = {"market": {
            "live_diagnostics": {"market_open": True, "quote_refresh_window": True,
                                 "required_trades": 500, "required_coverage_pct": 35},
            "partial_live": {"verified_count": 132, "coverage_pct": 6.7},
            "live_valid": False,
        }}
        self.assertTrue(any("132 trades / 6.7%" in x for x in check(feed)))


if __name__ == "__main__":
    unittest.main()
