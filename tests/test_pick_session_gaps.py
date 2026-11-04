"""A missing whole exchange session must not move a frozen horizon."""
import copy
import unittest
from scripts.update_pick_validation import freeze_picks,compile_report
import test_pick_validation as f

class PickSessionGapTests(unittest.TestCase):
    def report(self,archive):
        frozen=freeze_picks(f.feed(),archive['days'][f.DATES[0]],f.DATES[0])
        original=copy.deepcopy(frozen)
        result=compile_report(frozen,archive,'2026-10-20 16:00')
        self.assertEqual(frozen,original)
        return result

    def test_missing_whole_session_does_not_shift_three_day_exit(self):
        a=f.archive(6);a['days'].pop('2026-10-15')
        r=self.report(a)
        for p in r['picks']:
            o=p['outcomes'][0]
            self.assertEqual(o['status'],'missing_price')
            self.assertEqual(o['end_day'],'2026-10-16')
            self.assertEqual(o['observed_closes'],2)
            self.assertEqual(o['expected_closes'],3)
            self.assertNotIn('estimated_net_return_pct',o)
        self.assertEqual(r['groups']['attack']['3']['completed'],0)
        self.assertEqual(r['groups']['attack']['3']['missing_price'],2)

    def test_low_coverage_whole_session_is_not_silently_removed(self):
        a=f.archive(6);a['days']['2026-10-15']={'2344':97}
        r=self.report(a)
        self.assertTrue(all(p['outcomes'][0]['status']=='missing_price' for p in r['picks']))
        self.assertTrue(all(p['outcomes'][0]['end_day']=='2026-10-16' for p in r['picks']))

    def test_missing_exit_session_keeps_its_calendar_date(self):
        a=f.archive(6);a['days'].pop('2026-10-16')
        r=self.report(a)
        for p in r['picks']:
            self.assertEqual(p['outcomes'][0]['status'],'missing_price')
            self.assertEqual(p['outcomes'][0]['end_day'],'2026-10-16')

    def test_gap_after_closed_horizon_does_not_change_earlier_outcome(self):
        full=self.report(f.archive(6));a=f.archive(6);a['days'].pop('2026-10-19');gap=self.report(a)
        self.assertEqual([p['outcomes'][0] for p in gap['picks']],[p['outcomes'][0] for p in full['picks']])

    def test_weekends_and_known_closures_do_not_create_missing_sessions(self):
        a=f.archive(8)
        for day in ['2026-10-27','2026-10-28','2026-10-29']:
            a['days'][day]=copy.deepcopy(a['days']['2026-10-22'])
        # 10/23 confirmed typhoon closure; 10/26 scheduled closure.
        # Fixture feed prices differ on this date, so use a fixed existing signal.
        frozen=[{'id':'fixture','day':'2026-10-22','code':'2344','group':'attack','rank':1,'name':'fixture','score':90,'signal_close':120}]
        r=compile_report(frozen,a,'2026-10-29 16:00');o=r['picks'][0]['outcomes'][0]
        self.assertEqual(o['status'],'complete');self.assertEqual(o['end_day'],'2026-10-29')

    def test_recovered_day_restores_original_horizon_without_changing_signal(self):
        a=f.archive(6);expected=self.report(a);saved=a['days'].pop('2026-10-15')
        self.report(a);a['days']['2026-10-15']=saved
        self.assertEqual(self.report(a),expected)

if __name__=='__main__':unittest.main()
