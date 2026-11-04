"""Preserve real raw closes while refusing unadjusted corporate-action returns."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from scripts import update_system as u
from scripts import update_pick_validation as v
from scripts import update_paper_performance as paper
import test_pick_validation as picks_fixture
import test_paper_performance as paper_fixture


class CorporateActionPriceTests(unittest.TestCase):
    def test_actual_updater_archives_exrights_close_without_scoring_unknown_change(self):
        moment = datetime(2026,11,4,16,5,tzinfo=u.TZ)
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return moment
        twse=[{'Code':str(1000+i),'Name':'fixture','Date':'1151104','ClosingPrice':'100','Change':'1','TradeVolume':'1000000'} for i in range(550)]
        tpex=[{'SecuritiesCompanyCode':str(4000+i),'CompanyName':'fixture','Date':'1151104','Close':'100','Change':'1','TradingShares':'1000000'} for i in range(550)]
        tpex.append({'SecuritiesCompanyCode':'3691','CompanyName':'fixture','Date':'1151104','Close':'119.5','Change':'除權','TradingShares':'1000000'})
        def fetch(url,*args,**kwargs):
            if url==u.TWSE_STOCK:return twse
            if url==u.TPEX_STOCK:return tpex
            if url==u.TWSE_INDEX:return []
            raise RuntimeError('No additional fixture endpoint')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'system.json';hist=root/'history.json';daily=root/'daily.json'
            out.write_text(json.dumps({'data_date':'2026-11-03','risk':{},'holdings':{}}));hist.write_text('[]')
            daily.write_text(json.dumps({'schema':1,'kind':'official_daily_close','days':{'2026-11-03':{'2330':100}},'corporate_actions':{'2026-11-03':{'2330':'除息'}}}))
            with patch.object(u,'OUT',out),patch.object(u,'HISTORY',hist),patch.object(u,'DAILY_PRICES',daily),patch.object(u,'datetime',Clock),patch.object(u,'fetch_json',side_effect=fetch),patch.object(u,'fetch_latest_offhours_close',side_effect=lambda rows,*args:(rows,None)),patch.object(u,'fetch_institutional',return_value=({},[],{})),contextlib.redirect_stdout(io.StringIO()):
                u.main()
            archive=json.loads(daily.read_text());feed=json.loads(out.read_text())
            self.assertEqual(archive['days']['2026-11-04'].get('3691'),119.5)
            self.assertEqual(archive['corporate_actions']['2026-11-04']['3691'],'除權')
            self.assertEqual(archive['corporate_actions']['2026-11-03']['2330'],'除息')
            self.assertNotIn('3691',[row['code'] for row in feed['universe']])

    def test_archive_collector_keeps_close_without_a_numeric_daily_change(self):
        row=u.norm_tpex({'SecuritiesCompanyCode':'3691','Date':'1151027','Close':'119.5','Change':'除權'})
        self.assertFalse(u.stock_only(row))
        prices,actions=u.official_close_observations([row],'2026-10-27')
        self.assertEqual(prices,{'3691':119.5});self.assertEqual(actions,{'3691':'除權'})

    def test_collector_rejects_stale_live_invalid_and_conflicting_closes(self):
        base={'code':'3691','market':'TPEX','date':'2026-10-27','close':119.5,'price_note':'除權'}
        for change in ({'date':'2026-10-22'},{'live':True},{'close':True},{'close':float('nan')},{'market':'unknown'}):
            with self.subTest(change=change):
                self.assertEqual(u.official_close_observations([{**base,**change}],'2026-10-27'),({},{}))
        with self.assertRaises(ValueError):
            u.official_close_observations([base,{**base,'close':120}],'2026-10-27')

    def report(self,action_day=None):
        archive=picks_fixture.archive(4)
        if action_day:archive['corporate_actions']={action_day:{'2344':'除權'}}
        frozen=v.freeze_picks(picks_fixture.feed(),archive['days'][picks_fixture.DATES[0]],picks_fixture.DATES[0])
        before=copy.deepcopy(frozen)
        result=v.compile_report(frozen,archive,'2026-10-16 16:00')
        self.assertEqual(frozen,before)
        return result

    def test_unadjusted_action_is_retained_and_not_scored_as_a_win_or_loss(self):
        report=self.report(picks_fixture.DATES[1]);row=next(p for p in report['picks'] if p['code']=='2344')
        outcome=row['outcomes'][0]
        self.assertEqual(outcome['status'],'corporate_action_unadjusted')
        self.assertNotIn('estimated_net_return_pct',outcome)
        self.assertEqual(report['groups']['attack']['3']['completed'],1)
        self.assertEqual(report['groups']['attack']['3']['corporate_action_unadjusted'],1)
        self.assertIsNone(row['latest_observation']['gross_return_pct'])

    def test_signal_day_and_future_actions_do_not_rewrite_past_returns(self):
        plain=self.report()
        for day in (picks_fixture.DATES[0],'2026-11-05'):
            result=self.report(day)
            self.assertEqual(result['picks'],plain['picks'])
            self.assertEqual(result['groups'],plain['groups'])

    def test_bad_action_metadata_fails_closed(self):
        for events in ([],{'not-a-date':{'2344':'除權'}},{'2026-10-14':{'2344':'unverified'}}):
            a=picks_fixture.archive(4);a['corporate_actions']=events
            frozen=v.freeze_picks(picks_fixture.feed(),a['days'][picks_fixture.DATES[0]],picks_fixture.DATES[0])
            with self.subTest(events=events),self.assertRaises(ValueError):v.compile_report(frozen,a,'2026-10-16 16:00')

    def test_held_paper_position_stops_atomically_before_unadjusted_action(self):
        f=paper_fixture;a=f.archive((f.DAY1,100),(f.DAY2,100),(f.DAY3,106));state=paper.initial_state()
        paper.advance(f.feed(f.DAY1),a,state,f.DAY1);paper.advance(f.feed(f.DAY2,False),a,state,f.DAY2)
        a['corporate_actions']={f.DAY3:{'2603':'除權'}};before=copy.deepcopy(state)
        with self.assertRaisesRegex(ValueError,'除權息'):paper.advance(f.feed(f.DAY3,False),a,state,f.DAY3)
        self.assertEqual(state,before)

    def test_entry_after_action_requires_no_preexisting_entitlement(self):
        f=paper_fixture;a=f.archive((f.DAY1,100),(f.DAY2,100));a['corporate_actions']={f.DAY2:{'2603':'除權'}}
        state=paper.initial_state();paper.advance(f.feed(f.DAY1),a,state,f.DAY1)
        self.assertTrue(paper.advance(f.feed(f.DAY2,False),a,state,f.DAY2))
        self.assertTrue(state['strategies']['fixed5']['positions'])


if __name__=='__main__':unittest.main()
