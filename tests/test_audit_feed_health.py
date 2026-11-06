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

    def test_full_market_snapshot_without_partial_sample_can_pass(self):
        feed=self.healthy()
        feed['market'].update(live_count=600,live_coverage_pct=40,partial_live=None)
        before=copy.deepcopy(feed)
        self.assertEqual(check(feed),[])
        self.assertEqual(feed,before)

    def test_current_degraded_shape_reports_actual_market_coverage(self):
        feed=self.healthy()
        feed['market'].update(live_count=88,live_coverage_pct=4.5,live_valid=False,
                             partial_live={'verified_count':88,'complete':False,'quotes':[]})
        issues=check(feed)
        self.assertTrue(any('88 trades / 4.5%' in issue for issue in issues))
        self.assertFalse(any('88 trades / 0%' in issue for issue in issues))

    def test_invalid_canonical_metrics_never_use_healthy_partial_fallback(self):
        for key,values in (('live_count',(True,600.5,-1,'bad',float('inf'))),
                           ('live_coverage_pct',(True,-1,101,'NaN',float('inf')))):
            for value in values:
                with self.subTest(key=key,value=value):
                    feed=self.healthy();feed['market'][key]=value
                    issues=check(feed)
                    self.assertIn('invalid diagnostic metric: '+key,issues)
                    self.assertIn('live_valid incorrectly true',issues)

    def test_disagreeing_market_and_partial_metrics_are_flagged(self):
        feed=self.healthy();feed['market'].update(live_count=601,live_coverage_pct=41)
        issues=check(feed)
        self.assertIn('inconsistent live count between market and partial_live',issues)
        self.assertIn('inconsistent live coverage between market and partial_live',issues)

    def test_live_claim_cannot_override_explicit_readonly_flags(self):
        for flag in ('stale', 'historical_readonly', 'no_new_picks'):
            with self.subTest(flag=flag):
                feed=self.healthy();feed['market'][flag]=True
                self.assertIn('live_valid conflicts with '+flag,check(feed))

    def test_live_universe_and_coverage_must_agree(self):
        for total,issue in ((2000,'inconsistent live coverage with close_count'),
                            (500,'live count exceeds close_count'),
                            (True,'invalid diagnostic metric: close_count'),
                            (0,'invalid diagnostic metric: close_count'),
                            (1500.5,'invalid diagnostic metric: close_count'),
                            (float('nan'),'invalid diagnostic metric: close_count')):
            with self.subTest(total=total):
                feed=self.healthy();feed['market'].update(live_count=600,live_coverage_pct=40,
                                                        close_count=total,partial_live=None)
                self.assertIn(issue,check(feed))

    def test_real_sample_rounding_and_input_are_preserved(self):
        for count,total,pct in ((1036,1978,52.4),(1771,1979,89.5)):
            with self.subTest(count=count):
                feed=self.healthy();feed['market'].update(live_count=count,close_count=total,
                                                        live_coverage_pct=pct,partial_live=None)
                before=copy.deepcopy(feed)
                self.assertEqual(check(feed),[])
                self.assertEqual(feed,before)

    def test_readonly_flags_without_live_claim_are_not_contradictions(self):
        feed=self.healthy();feed['market'].update(live_valid=False,stale=True,
            historical_readonly=True,no_new_picks=True)
        self.assertFalse(any('conflicts with' in issue for issue in check(feed)))


if __name__ == "__main__":
    unittest.main()
