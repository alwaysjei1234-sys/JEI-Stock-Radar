import unittest
import copy

from scripts.audit_feed_health import check


class FeedAuditTests(unittest.TestCase):
    def healthy(self):
        return {"market": {
            "live_diagnostics": {"market_open": True, "quote_refresh_window": True,
                "required_trades": 500, "required_coverage_pct": 35,
                "mis_stats": {"returned_messages": 600, "missing_last_trade": 0}},
            "partial_live": {"verified_count": 600, "coverage_pct": 40},
            "live_valid": True}}

    def test_nonfinite_or_out_of_range_coverage_never_passes(self):
        for value in (float('nan'),float('inf'),-float('inf'),'NaN',True,-1,101,[],{}):
            with self.subTest(value=value):
                f=self.healthy();f['market']['partial_live']['coverage_pct']=value
                issues=check(f)
                self.assertIn('invalid diagnostic metric: coverage_pct',issues)
                self.assertIn('live_valid incorrectly true',issues)

    def test_invalid_counts_thresholds_and_stats_degrade_without_crashing(self):
        for section,key,values in (
                ('partial_live','verified_count',(True,600.5,-1,'bad',float('inf'))),
                ('live_diagnostics','required_trades',(0,True,500.5,float('nan'))),
                ('live_diagnostics','required_coverage_pct',(0,True,101,float('nan'))),
                ('mis_stats','returned_messages',(True,-1,'bad',float('nan'))),
                ('mis_stats','missing_last_trade',(True,-1,'bad',float('inf')))):
            for value in values:
                with self.subTest(key=key,value=value):
                    f=self.healthy();m=f['market']
                    target=m['live_diagnostics']['mis_stats'] if section=='mis_stats' else m[section]
                    target[key]=value
                    self.assertIn('invalid diagnostic metric: '+key,check(f))

    def test_valid_numeric_strings_do_not_mutate_input(self):
        f=self.healthy();f['market']['partial_live'].update(verified_count='600',coverage_pct='40.0')
        before=copy.deepcopy(f)
        self.assertEqual(check(f),[])
        self.assertEqual(f,before)

    def test_impossible_missing_trade_count_is_flagged(self):
        f=self.healthy();f['market']['live_diagnostics']['mis_stats'].update(returned_messages=0,missing_last_trade=1)
        self.assertIn('MIS missing count exceeds returned messages',check(f))

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
