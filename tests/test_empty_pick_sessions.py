"""No candidates is a sealed observation, never a synthetic trade or a data gap."""
import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
from scripts import update_pick_validation as u

DAYS=['2026-11-02','2026-11-03','2026-11-04','2026-11-05','2026-11-06']
def archive(n):
    return {'schema':1,'kind':'official_daily_close','days':{
        d:{str(1000+i):100. for i in range(600)} for d in DAYS[:n]}}
def feed(day,empty=True):
    f={'data_date':day,'updated_at':day+' 15:30','holdings':{},
       'selection_policy':'jei-user-radar-gates-v1',
       'market':{'mode':'今日收盤','stale':False,'close_count':600}}
    for group in u.GROUPS:
        f[group]=[] if empty else [{'code':'1000','name':'fixture','price':100.,'score':90}]
    return f
def now(day,hour=16):return datetime.fromisoformat(day).replace(hour=hour,tzinfo=u.TZ)
def prior():return {'schema':1,'mode':'immutable_asof_pick_archive','picks':[]}

class EmptyPickSessionTests(unittest.TestCase):
    def test_verified_empty_day_has_no_trades_no_wins_and_no_zero_percent_claim(self):
        p=prior();before=copy.deepcopy(p)
        ledger,report,captured=u.update(feed(DAYS[0]),archive(1),p,now(DAYS[0]))
        self.assertTrue(captured);self.assertEqual(p,before)
        self.assertEqual(ledger['picks'],[]);self.assertEqual(report['total_frozen_picks'],0)
        self.assertEqual(ledger['empty_sessions'][0]['day'],DAYS[0])
        self.assertEqual(ledger['empty_sessions'][0]['status'],'verified_no_candidates')
        self.assertEqual(report['empty_sessions'],ledger['empty_sessions'])
        for group in report['groups'].values():
            for metric in group.values():
                self.assertEqual(metric['completed'],0)
                self.assertIsNone(metric['win_rate_pct']);self.assertIsNone(metric['avg_estimated_net_pct'])

    def test_following_session_can_capture_without_false_gap(self):
        old,_,_=u.update(feed(DAYS[0],False),archive(1),prior(),now(DAYS[0]))
        empty,_,_=u.update(feed(DAYS[1]),archive(2),old,now(DAYS[1]))
        new,report,captured=u.update(feed(DAYS[2],False),archive(3),empty,now(DAYS[2]))
        self.assertTrue(captured);self.assertEqual(new['picks'][:5],old['picks'])
        self.assertEqual(len(new['picks']),10);self.assertEqual(len(new['empty_sessions']),1)
        self.assertEqual(report['total_frozen_picks'],10)

    def test_repeated_empty_day_is_immutable_even_if_later_feed_adds_winners(self):
        old,_,_=u.update(feed(DAYS[0]),archive(1),prior(),now(DAYS[0]))
        for f in (feed(DAYS[0]),feed(DAYS[0],False)):
            new,_,captured=u.update(f,archive(1),old,now(DAYS[0],19))
            self.assertFalse(captured);self.assertEqual(new,old)

    def test_missing_or_malformed_groups_cannot_be_sealed_as_empty(self):
        for value in (None,{},'',False):
            f=feed(DAYS[0]);f['attack']=value
            with self.subTest(value=value),self.assertRaises(ValueError):
                u.update(f,archive(1),prior(),now(DAYS[0]))
        f=feed(DAYS[0]);del f['attack']
        with self.assertRaises(ValueError):u.update(f,archive(1),prior(),now(DAYS[0]))

    def test_nonempty_but_rejected_candidates_remain_errors(self):
        for bad in ({'code':'1000','score':90,'price':200}, {'code':'bad','score':90,'price':100}):
            f=feed(DAYS[0]);f['attack']=[bad]
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                u.update(f,archive(1),prior(),now(DAYS[0]))

    def test_stale_premarket_low_coverage_or_future_stamp_not_sealed(self):
        cases=[]
        for field,value in [('stale',True),('mode','盤中即時'),('close_count',499)]:
            f=feed(DAYS[0]);f['market'][field]=value;cases.append(f)
        for stamp in ('2026-11-02 08:00','2026-11-02 17:00'):
            f=feed(DAYS[0]);f['updated_at']=stamp;cases.append(f)
        for f in cases:
            with self.subTest(f=f):
                ledger,_,captured=u.update(f,archive(1),prior(),now(DAYS[0]))
                self.assertFalse(captured);self.assertEqual(ledger,prior())

    def test_corrupt_duplicate_future_or_conflicting_empty_records_rejected(self):
        old,_,_=u.update(feed(DAYS[0]),archive(1),prior(),now(DAYS[0]))
        cases=[]
        for field,value in [('day',[]),('status','unverified'),('feed_updated_at',DAYS[0]+' 09:00'),('feed_updated_at',DAYS[1]+' 16:00'),('selection_policy',None)]:
            x=copy.deepcopy(old);x['empty_sessions'][0][field]=value;cases.append(x)
        x=copy.deepcopy(old);x['empty_sessions']*=2;cases.append(x)
        x=copy.deepcopy(old);x['empty_sessions']={};cases.append(x)
        x=copy.deepcopy(old);x['empty_sessions']=[None];cases.append(x)
        x=copy.deepcopy(old);x['picks']=[{'id':DAYS[0]+':attack:1000','day':DAYS[0],'group':'attack','code':'1000'}];cases.append(x)
        for x in cases:
            with self.subTest(x=x),self.assertRaises(ValueError):
                u.update(feed(DAYS[1]),archive(2),x,now(DAYS[1]))

    def test_true_unrecorded_gap_and_missing_official_coverage_still_block(self):
        old,_,_=u.update(feed(DAYS[0]),archive(1),prior(),now(DAYS[0]))
        with self.assertRaises(ValueError):u.update(feed(DAYS[2],False),archive(3),old,now(DAYS[2]))
        incomplete=archive(2);incomplete['days'][DAYS[0]]={'1000':100.}
        with self.assertRaises(ValueError):u.update(feed(DAYS[1]),incomplete,old,now(DAYS[1]))

    def test_first_weekend_bootstrap_and_consecutive_empty_sessions(self):
        a=archive(5);f=feed(DAYS[4]);saturday=now('2026-11-07')
        ledger,_,captured=u.update(f,a,prior(),saturday)
        self.assertTrue(captured)
        self.assertEqual(ledger['empty_sessions'][0]['origin'],'verified_archive_bootstrap')
        old,_,_=u.update(feed(DAYS[0]),archive(1),prior(),now(DAYS[0]))
        new,_,captured=u.update(feed(DAYS[1]),archive(2),old,now(DAYS[1]))
        self.assertTrue(captured);self.assertEqual(len(new['empty_sessions']),2)

    def test_recovery_accepts_empty_anchor_and_preserves_first_empty_publication(self):
        from scripts.recover_pick_history import recover, last_sealed_day
        old,_,_=u.update(feed(DAYS[0]),archive(1),prior(),now(DAYS[0]))
        sources=[{'sha':str(i+1)*40,'blob':'a'*40,'committed_at':day+'T16:00:00+08:00',
                  'feed':feed(day,empty=(i==0))} for i,day in enumerate(DAYS[1:3])]
        revised=copy.deepcopy(sources[0]);revised['feed']=feed(DAYS[1],False)
        state,proof=recover(old,archive(3),[sources[0],revised,sources[1]],now(DAYS[2],17))
        self.assertEqual([x['captured'] for x in proof],[0,5])
        self.assertEqual(len(state['empty_sessions']),2)
        self.assertEqual(state['empty_sessions'][1]['source_commit'],'1'*40)
        self.assertEqual(last_sealed_day(state),DAYS[2])
        again,proof=recover(state,archive(3),[],now(DAYS[2],18))
        self.assertEqual(again,state);self.assertEqual(proof,[])

    def test_main_writes_and_reads_empty_session_without_republishing_same_report(self):
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return now(DAYS[0])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);f=root/'system.json';a=root/'daily.json';p=root/'picks.json';r=root/'report.json'
            f.write_text(json.dumps(feed(DAYS[0])));a.write_text(json.dumps(archive(1)))
            with patch.object(u,'FEED',f),patch.object(u,'DAILY',a),patch.object(u,'PICKS',p),patch.object(u,'REPORT',r),patch.object(u,'datetime',Clock),contextlib.redirect_stdout(io.StringIO()):
                u.main();state=json.loads(p.read_text());report=json.loads(r.read_text());stamp=r.stat().st_mtime_ns
                u.main()
            self.assertEqual(json.loads(p.read_text()),state)
            self.assertEqual(json.loads(r.read_text()),report)
            self.assertEqual(r.stat().st_mtime_ns,stamp)
            self.assertEqual(len(state['empty_sessions']),1)

if __name__=='__main__':unittest.main()
