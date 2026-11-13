import unittest
from unittest.mock import patch
from scripts import update_system as u


class MisProbeEnvelopeTests(unittest.TestCase):
    def test_rejected_envelope_does_not_start_full_scan(self):
        channels=['tse_2330.tw','otc_6488.tw']
        with patch.object(u,'fetch_mis_channels',side_effect=ValueError('MIS unsuccessful status or invalid response envelope')) as fetch, patch.object(u.time,'sleep'):
            available,attempts,reason=u.mis_service_probe(channels)
        self.assertFalse(available)
        self.assertEqual(attempts,3)
        self.assertEqual(reason,'invalid_response')
        self.assertEqual(fetch.call_count,3)

    def test_transient_bad_envelope_recovers_on_next_probe(self):
        channels=['tse_2330.tw','otc_6488.tw']
        with patch.object(u,'fetch_mis_channels',side_effect=[ValueError('invalid response envelope'),[]]) as fetch, patch.object(u.time,'sleep'):
            available,attempts,reason=u.mis_service_probe(channels)
        self.assertTrue(available)
        self.assertEqual(attempts,2)
        self.assertIsNone(reason)
        self.assertEqual(fetch.call_count,2)


if __name__=='__main__':
    unittest.main()
