"""Independent official feeds must overlap without losing source-specific failures."""
import threading
import unittest
from unittest.mock import patch
from scripts import update_system as m

class InitialMarketSourcesTests(unittest.TestCase):
    def test_independent_requests_overlap_and_keep_source_order(self):
        barrier=threading.Barrier(3)
        def fetch(url):
            barrier.wait(timeout=2)
            return [url]
        errors=[]
        with patch.object(m,'fetch_json',side_effect=fetch):
            result=m.fetch_initial_market_sources(errors)
        self.assertEqual(result,([m.TWSE_STOCK],[m.TWSE_INDEX],[m.TPEX_STOCK]))
        self.assertEqual(errors,[])

    def test_failure_does_not_discard_other_official_market(self):
        def fetch(url):
            if url==m.TWSE_INDEX: raise OSError('unavailable')
            return [url]
        errors=[]
        with patch.object(m,'fetch_json',side_effect=fetch):
            result=m.fetch_initial_market_sources(errors)
        self.assertEqual(result,([m.TWSE_STOCK],[],[m.TPEX_STOCK]))
        self.assertEqual(errors,['TWSE指數:unavailable'])

    def test_main_uses_parallel_loader_before_normalizing(self):
        class StopAfterLoad(Exception):pass
        with patch.object(m,'fetch_initial_market_sources',return_value=([{}],[],[])) as load, patch.object(m,'norm_twse',side_effect=StopAfterLoad), patch.object(m,'fetch_json',side_effect=AssertionError('unexpected serial access')):
            with self.assertRaises(StopAfterLoad):m.main()
        load.assert_called_once()

if __name__=='__main__':unittest.main()
