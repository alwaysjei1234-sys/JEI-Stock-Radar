import copy
import unittest
from datetime import datetime
from scripts import recover_mainline_paper as r
from scripts.update_paper_performance import initial_state, advance
from test_paper_performance import archive, feed, DAY1, DAY2, DAY3


class MainlinePaperRecoveryTests(unittest.TestCase):
    def fixture(self):
        prices=archive((DAY1,100),(DAY2,100),(DAY3,90))
        state=initial_state()
        first=feed(DAY1); first['holdings']={}
        advance(first,archive((DAY1,100)),state,DAY1)
        sources=[]
        for i,day in enumerate((DAY2,DAY3),1):
            f=feed(day); f['holdings']={}
            sources.append({'sha':str(i)*40,'blob':'a'*40,'feed':f,
                            'committed_at':day+'T16:00:00+08:00'})
        return state,prices,sources,datetime(2026,10,15,22,tzinfo=r.TZ)

    def test_replay_preserves_original_signals_includes_losses_and_is_idempotent(self):
        state,prices,sources,now=self.fixture(); old=copy.deepcopy(state)
        result,proof=r.recover(state,prices,sources,now,lambda _:prices)
        self.assertEqual(state,old)
        self.assertEqual(result['signals'][:len(old['signals'])],old['signals'])
        for account in result['strategies'].values():
            self.assertEqual(len(account['closed']),1)
            self.assertLess(account['closed'][0]['net'],0)
        self.assertTrue(all(s['provenance']['reconstructed'] for s in result['signals'][1:]))
        self.assertTrue(all(p['qualified_oos'] is False for p in proof))
        self.assertEqual(r.recover(result,prices,[],now,lambda _:prices),(result,[]))

    def test_missing_day_late_publication_private_feed_and_rule_mismatch_are_atomic(self):
        for mode in ('missing','late','private','rules'):
            state,prices,sources,now=self.fixture(); old=copy.deepcopy(state)
            if mode=='missing':sources.pop(0)
            if mode=='late':sources[0]['committed_at']=DAY3+'T16:00:00+08:00'
            if mode=='private':sources[0]['feed']['holdings']={'2330':{'cost':123}}
            def reader(_):
                if mode=='rules':raise ValueError('Historical strategy rules differ')
                return prices
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                r.recover(state,prices,sources,now,reader)
            self.assertEqual(state,old)

    def test_first_publication_is_not_replaced_and_revised_prices_are_refused(self):
        state,prices,sources,now=self.fixture()
        later=copy.deepcopy(sources[0]);later['feed']['attack'][0]['score']=99
        result,proof=r.recover(state,prices,[sources[0],later,sources[1]],now,lambda _:prices)
        self.assertEqual(result['signals'][1]['score'],92)
        changed=copy.deepcopy(prices);changed['days'][DAY2]['2603']=101
        with self.assertRaisesRegex(ValueError,'prices conflict'):
            r.recover(state,prices,sources,now,lambda _:changed)
