"""Incomplete portfolio valuations cannot certify a full-path drawdown."""
import copy
import unittest
from scripts.paper_evidence import full_drawdown
from scripts.update_paper_performance import advance,initial_state,price_for,validate
from test_paper_performance import archive,feed,prices,DAY1,DAY2,DAY3,DAY4

class MissingValuationTests(unittest.TestCase):
    def test_gap_cannot_look_like_zero_drawdown(self):
        self.assertIsNone(full_drawdown([{'equity':100},{'equity':None},{'equity':100}],100))

    def test_missing_early_or_latest_value_makes_full_path_unknown(self):
        for values in ([None,90,100],[100,90,None],[100,90,120,None,100]):
            with self.subTest(values=values):
                self.assertIsNone(full_drawdown([{'equity':v} for v in values],100))

    def test_missing_field_empty_and_all_missing_have_no_measurement(self):
        for history in ([],[{'equity':None}],[{}],[{'equity':100},{}]):
            with self.subTest(history=history):self.assertIsNone(full_drawdown(history,100))

    def test_complete_paths_keep_peak_and_initial_capital_arithmetic(self):
        for values,expected in [([120,90,110],25),([90,100],10),([100,100],0),([100,0],100)]:
            with self.subTest(values=values):
                history=[{'equity':v} for v in values];before=copy.deepcopy(history)
                self.assertEqual(full_drawdown(history,100),expected)
                self.assertEqual(history,before)

    def test_malformed_value_after_gap_is_still_rejected(self):
        for value in (True,-1,'100',float('nan'),float('inf')):
            with self.subTest(value=value),self.assertRaises(ValueError):
                full_drawdown([{'equity':None},{'equity':value}],100)

    def test_boolean_quote_is_not_a_one_dollar_trade(self):
        for value in (True,False):
            self.assertIsNone(price_for({'2603':value},'2603'))
        self.assertEqual(price_for({'2603':'100.25'},'2603'),100.25)

    def test_boolean_quote_rows_do_not_satisfy_official_coverage(self):
        data=archive((DAY1,100));data['days'][DAY1]={str(1000+i):True for i in range(600)}
        with self.assertRaises(ValueError):validate(feed(DAY1),data,DAY1)

    def test_missing_held_close_stays_unknown_after_price_recovers(self):
        state=initial_state();data=archive((DAY1,100),(DAY2,100))
        advance(feed(DAY1),data,state,DAY1);advance(feed(DAY2,False),data,state,DAY2)
        data['days'][DAY3]=prices(100);data['days'][DAY3].pop('2603')
        advance(feed(DAY3,False),data,state,DAY3)
        for account in state['strategies'].values():
            self.assertIsNone(account['equity_history'][-1]['equity'])
            self.assertIsNone(account['summary']['max_drawdown_pct'])
        data['days'][DAY4]=prices(106);advance(feed(DAY4,False),data,state,DAY4)
        for account in state['strategies'].values():
            self.assertIsNotNone(account['summary']['estimated_liquidation_equity_ntd'])
            self.assertIsNone(account['summary']['max_drawdown_pct'])
        self.assertEqual(len(state['strategies']['fixed5']['closed']),1)

if __name__=='__main__':unittest.main()
