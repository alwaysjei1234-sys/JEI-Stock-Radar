"""Independent cost arithmetic and history-retention regression checks."""
import copy
import unittest
from datetime import date, timedelta
from scripts.paper_evidence import trade_metrics, wilson_interval
from scripts.update_paper_performance import FEE, SELL_TAX, initial_state, advance
from test_paper_performance import archive, feed, DAY1, DAY2


def trade(entry, exit_price, qty=100):
    return {'signal_day':'2026-01-05','entry_day':'2026-01-06','exit_day':'2026-01-07',
            'entry_price':entry, 'exit_price':exit_price, 'qty':qty,
            'net':round(qty*(exit_price*(1-FEE-SELL_TAX)-entry*(1+FEE)),2)}


class PaperEvidenceTests(unittest.TestCase):
    def test_known_wilson_interval_and_empty_samples(self):
        self.assertEqual(wilson_interval(80,100), [71.12,86.66])
        self.assertIsNone(wilson_interval(0,0))
        zero=trade_metrics([],FEE,SELL_TAX)
        self.assertIsNone(zero['mean_net_return_pct'])
        self.assertIsNone(zero['slippage_scenarios'][0]['win_rate_pct'])
        self.assertEqual(zero['qualification'],'research_only')

    def test_cost_stress_is_not_a_new_fill_or_changed_ledger(self):
        trades=[trade(100,101),trade(100,100.7),trade(100,96)]
        before=copy.deepcopy(trades)
        evidence=trade_metrics(trades,FEE,SELL_TAX)
        self.assertEqual(trades,before)
        # At +0.7% gross the base trade wins; 0.1% each side makes it lose.
        self.assertGreater(trades[1]['net'],0)
        self.assertEqual(evidence['slippage_scenarios'][0]['win_rate_pct'],33.33)
        expected=100*((101*.999*(1-FEE-SELL_TAX))/(100*1.001*(1+FEE))-1)
        single=trade_metrics([trades[0]],FEE,SELL_TAX)
        self.assertAlmostEqual(single['slippage_scenarios'][0]['mean_net_return_pct'],expected,places=3)
        self.assertLess(evidence['slippage_scenarios'][1]['mean_net_return_pct'],evidence['slippage_scenarios'][0]['mean_net_return_pct'])

    def test_invalid_or_inconsistent_ledger_is_not_scored(self):
        for change in ({'entry_price':0},{'qty':True},{'qty':float('nan')},{'net':1000000},{'exit_price':float('inf')}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                trade_metrics([{**trade(100,106),**change}],FEE,SELL_TAX)

    def test_minimum_brokerage_can_turn_a_small_gain_into_a_loss(self):
        trades=[trade(100,101,10)]
        before=copy.deepcopy(trades)
        self.assertGreater(trades[0]['net'],0)
        scenarios=trade_metrics(trades,FEE,SELL_TAX)['minimum_fee_scenarios']
        floor20=next(x for x in scenarios if x['minimum_fee_per_side_ntd']==20 and x['slippage_per_side_pct']==0)
        # Buy 1000+20; sell 1010-20-3.03 tax = 986.97, net -33.03.
        self.assertEqual(floor20['mean_net_pnl_ntd'],-33.03)
        self.assertAlmostEqual(floor20['mean_net_return_pct'],100*(-33.03)/1020,places=3)
        self.assertEqual(floor20['win_rate_pct'],0)
        self.assertEqual(floor20['affected_trades'],1)
        self.assertEqual(trades,before)

    def test_minimum_fee_keeps_tax_separate_and_large_trades_unchanged(self):
        scenarios=trade_metrics([trade(100,101,1000)],FEE,SELL_TAX)['minimum_fee_scenarios']
        no_slip=[x for x in scenarios if x['slippage_per_side_pct']==0]
        for row in no_slip:
            self.assertEqual(row['affected_trades'],0)
            self.assertEqual(row['additional_commission_ntd'],0)
            self.assertEqual(row['mean_net_pnl_ntd'],trade(100,101,1000)['net'])
        stressed=next(x for x in scenarios if x['minimum_fee_per_side_ntd']==20 and x['slippage_per_side_pct']==0.1)
        self.assertLess(stressed['mean_net_pnl_ntd'],no_slip[-1]['mean_net_pnl_ntd'])
        # A 1 TWD floor still charges sell tax on top, never inside the floor.
        tiny=trade_metrics([trade(10,10,1)],FEE,SELL_TAX)['minimum_fee_scenarios'][0]
        self.assertEqual(tiny['mean_net_pnl_ntd'],-2.03)

    def test_empty_minimum_fee_scenarios_do_not_fabricate_metrics(self):
        rows=trade_metrics([],FEE,SELL_TAX)['minimum_fee_scenarios']
        self.assertEqual(len(rows),4)
        for row in rows:
            self.assertEqual(row['closed'],0)
            self.assertIsNone(row['win_rate_pct'])
            self.assertIsNone(row['mean_net_return_pct'])
            self.assertIsNone(row['mean_net_pnl_ntd'])

    def test_lifetime_trades_and_early_drawdown_survive_daily_update(self):
        state=initial_state();state['last_processed_day']=DAY1
        for account in state['strategies'].values():
            account['closed']=[trade(100,106) for _ in range(501)]
            account['equity_history']=[{'day':(date(2026,1,1)+timedelta(days=i)).isoformat(),
                                       'equity':700000 if i==1 else 1000000} for i in range(90)]
        advance(feed(DAY2,False),archive((DAY1,100),(DAY2,100)),state,DAY2)
        for account in state['strategies'].values():
            self.assertEqual(len(account['closed']),501)
            self.assertEqual(account['summary']['closed'],501)
            self.assertEqual(len(account['equity_history']),91)
            self.assertEqual(account['summary']['max_drawdown_pct'],30)
            self.assertEqual(account['summary']['evidence']['closed'],501)
