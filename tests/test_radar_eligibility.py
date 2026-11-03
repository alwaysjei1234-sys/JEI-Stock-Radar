"""Original user gates are eligibility rules, never tuned from outcomes."""
import copy
import unittest
from scripts import update_system as u
from scripts.update_pick_validation import freeze_picks, compile_report


def row(score, code='2330', sector_score=100):
    stock={'code':code,'name':'synthetic','close':100.,'high':100.,'low':90.,'open':98.,
           'pct':2.,'value':1e12,'volume':1e8,'market':'TWSE','date':'1151103'}
    return (score,stock,'fixture',sector_score,None,None,None,0)


class RadarEligibilityTests(unittest.TestCase):
    def test_attack_rejects_below_85_and_accepts_boundary(self):
        pool=[row(84),row(85,'2317'),row(99,'2454')]
        self.assertEqual([r[0] for r in u.qualified_radar_rows(pool,'attack')],[85,99])

    def test_next_requires_both_score_and_setup_boundary(self):
        self.assertEqual(u.next_setup_score(row(80,sector_score=70)[1],70,0),80)
        self.assertEqual(u.next_setup_score(row(80,sector_score=68)[1],68,0),79)
        pool=[row(79),row(80,'2317',68),row(80,'2454',70)]
        self.assertEqual([r[1]['code'] for r in u.qualified_radar_rows(pool,'next')],['2454'])

    def test_filter_precedes_limit_without_promoting_ineligible_rows(self):
        pool=[row(99,str(1000+i),40) for i in range(10)]+[row(90,'2454',100)]
        self.assertEqual([r[1]['code'] for r in u.qualified_radar_rows(pool,'next')],['2454'])
        self.assertEqual(len(u.qualified_radar_rows([row(85,str(1000+i)) for i in range(15)],'attack')),10)

    def test_all_below_threshold_leaves_formal_lists_empty(self):
        self.assertEqual(u.qualified_radar_rows([row(84)]*20,'attack'),[])
        self.assertEqual(u.qualified_radar_rows([row(79)]*20,'next'),[])

    def test_bad_scores_do_not_create_recommendations(self):
        for bad in (None,True,'99',float('nan'),float('inf'),100,-1):
            for mode in ('attack','next'):
                with self.subTest(bad=bad,mode=mode):
                    self.assertEqual(u.qualified_radar_rows([row(bad)],mode),[])

    def test_selection_does_not_rescore_or_mutate_pool(self):
        pool=[row(99),row(90,'2317')]; before=copy.deepcopy(pool)
        self.assertEqual(u.qualified_radar_rows(pool,'attack'),pool)
        self.assertEqual(pool,before)
        with self.assertRaises(ValueError):u.qualified_radar_rows(pool,'monster')

    def test_new_snapshot_carries_policy_and_legacy_history_is_unchanged(self):
        prices={'2330':100.};feed={'attack':[{'code':'2330','price':100.,'score':85}],
                                  'selection_policy':u.SELECTION_POLICY}
        new=freeze_picks(feed,prices,'2026-11-04')
        self.assertEqual(new[0]['selection_policy'],u.SELECTION_POLICY)
        old={**new[0],'day':'2026-11-03','id':'2026-11-03:attack:2330'}
        old.pop('selection_policy');before=copy.deepcopy(old)
        archive={'days':{'2026-11-03':{**{str(1000+i):100 for i in range(500)},'2330':100.}}}
        report=compile_report([old],archive,'2026-11-04 04:44')
        self.assertEqual(old,before)
        self.assertNotIn('selection_policy',report['picks'][0])

    def test_main_uses_formal_gates_without_erasing_high_risk_watch(self):
        import contextlib,io,json,tempfile
        from pathlib import Path
        from datetime import datetime
        from unittest.mock import patch
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return cls(2026,11,3,16,30,tzinfo=u.TZ)
        stocks=[{**row(90,str(1000+i))[1],'pct':3.} for i in range(600)]
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'system.json';hist=Path(temp)/'history.json';daily=Path(temp)/'daily.json'
            def get(url,*args,**kwargs):
                if url==u.TWSE_STOCK:return stocks
                if url.startswith(u.TPEX_STOCK):return [{**stocks[0],'code':'6488','market':'TPEX'}]
                if url==u.TWSE_INDEX:return []
                raise RuntimeError('synthetic fixture has no external data')
            with patch.object(u,'OUT',out),patch.object(u,'HISTORY',hist),patch.object(u,'DAILY_PRICES',daily),patch.object(u,'datetime',Clock),patch.object(u,'fetch_json',side_effect=get),patch.object(u,'norm_twse',side_effect=lambda x:x),patch.object(u,'norm_tpex',side_effect=lambda x:x),patch.object(u,'fetch_latest_offhours_close',side_effect=lambda rows,*args:(rows,None)),patch.object(u,'fetch_institutional',return_value=({},['fixture'],{})),patch.object(u,'build_sector_stats',return_value=([],{s['code']:'fixture' for s in stocks},{'fixture':100})),patch.object(u,'score_row',side_effect=lambda s,mode,*args:84 if mode=='attack' else 79 if mode=='next' else 99),contextlib.redirect_stdout(io.StringIO()):
                u.main()
            data=json.loads(out.read_text())
            self.assertEqual(data['market']['mode'],'今日收盤')
            self.assertEqual(data['attack'],[])
            self.assertEqual(data['next'],[])
            self.assertTrue(data['monster'])
            self.assertEqual(data['selection_policy'],u.SELECTION_POLICY)
            self.assertFalse(any(x.get('action') in ('主攻#1','下一棒#1') for x in data['priority']))

if __name__=='__main__':unittest.main()
