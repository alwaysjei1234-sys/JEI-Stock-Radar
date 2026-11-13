import unittest
from unittest.mock import patch
from datetime import datetime
from scripts import update_system as u

class MisOutageDiagnosticsTests(unittest.TestCase):
    def test_invalid_envelope_reason_is_not_mislabeled_as_network_or_http(self):
        rows=[{'code':'2330','market':'TWSE'}]
        with patch.object(u,'mis_service_probe',return_value=(False,3,'invalid_response')):
            _,count,_,errors,stats=u.enrich_live(rows,asof=datetime(2026,11,13,10,0,tzinfo=u.TZ))
        self.assertEqual(count,0)
        self.assertEqual(stats['outage_reason'],'invalid_response')
        self.assertIsNone(stats['unavailable_http_status'])
        self.assertTrue(stats['bulk_scan_skipped'])
        self.assertTrue(any('回應格式或狀態無效' in error for error in errors))

if __name__=='__main__':unittest.main()
