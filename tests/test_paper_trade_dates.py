"""Reject impossible chronology before descriptive performance can be scored."""
import copy
import json
from pathlib import Path
import unittest
from scripts.paper_evidence import trade_metrics
from scripts.update_paper_performance import FEE, SELL_TAX


def example():
    entry, exit_price, qty = 100, 106, 100
    return {'signal_day':'2026-10-13','entry_day':'2026-10-14','exit_day':'2026-10-15',
            'entry_price':entry,'exit_price':exit_price,'qty':qty,
            'net':round(qty*(exit_price*(1-FEE-SELL_TAX)-entry*(1+FEE)),2)}


class TradeChronologyTests(unittest.TestCase):
    def test_signal_must_precede_entry(self):
        for signal in ['2026-10-14','2026-10-15']:
            with self.subTest(signal=signal),self.assertRaises(ValueError):
                trade_metrics([{**example(),'signal_day':signal}],FEE,SELL_TAX)

    def test_exit_must_follow_entry_for_this_close_to_close_model(self):
        for exit_day in ['2026-10-14','2026-10-13']:
            with self.subTest(exit_day=exit_day),self.assertRaises(ValueError):
                trade_metrics([{**example(),'exit_day':exit_day}],FEE,SELL_TAX)

    def test_missing_or_noncanonical_date_is_not_scored(self):
        for field in ['signal_day','entry_day','exit_day']:
            for value in [None,True,20261015,'20261015','2026-10-3','2026-02-30','2026-10-15T13:30:00','2026-W42-4']:
                with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                    trade_metrics([{**example(),field:value}],FEE,SELL_TAX)
            missing=example();del missing[field]
            with self.subTest(field=field,missing=True),self.assertRaises(ValueError):
                trade_metrics([missing],FEE,SELL_TAX)

    def test_one_bad_trade_stops_whole_report_without_dropping_a_loss(self):
        valid=example();bad={**example(),'signal_day':'2026-10-16','net':-100}
        # Keep arithmetic consistent too, so chronology is independently needed.
        bad['exit_price']=95;bad['net']=round(100*(95*(1-FEE-SELL_TAX)-100*(1+FEE)),2)
        trades=[valid,bad];before=copy.deepcopy(trades)
        with self.assertRaises(ValueError):trade_metrics(trades,FEE,SELL_TAX)
        self.assertEqual(trades,before)

    def test_valid_chronology_preserves_costs_and_research_only_qualification(self):
        trades=[example()];before=copy.deepcopy(trades)
        result=trade_metrics(trades,FEE,SELL_TAX)
        self.assertEqual(result['closed'],1)
        self.assertEqual(result['qualification'],'research_only')
        self.assertEqual(trades,before)

    def test_every_current_public_trade_still_matches_stored_evidence(self):
        root=Path(__file__).resolve().parents[1]
        state=json.loads((root/'remote/strategy_performance.json').read_text())
        for key,account in state['strategies'].items():
            with self.subTest(strategy=key):
                self.assertEqual(trade_metrics(account['closed'],FEE,SELL_TAX),account['summary']['evidence'])
