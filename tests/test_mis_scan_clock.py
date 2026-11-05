"""Network scan latency must not make real observations look future-dated."""
import unittest
from datetime import datetime
from unittest.mock import patch
from scripts import update_system as u

class MisScanClockTests(unittest.TestCase):
    def scan(self, stock_time='10:02:00', index_time='10:03:00', frozen=False):
        class Clock(datetime):
            current=datetime(2026,11,5,10,0,tzinfo=u.TZ)
            @classmethod
            def now(cls,tz=None):return cls.current
        def fetch(channels):
            if channels==['tse_t00.tw']:
                Clock.current=datetime(2026,11,5,10,3,tzinfo=u.TZ)
                return [dict(c='t00',ex='tse',ch='t00.tw',d='20261105',t=index_time,z='40400',y='40000')]
            Clock.current=datetime(2026,11,5,10,2,tzinfo=u.TZ)
            return [dict(c='2330',ex='tse',ch='2330.tw',d='20261105',t=stock_time,z='101',y='100',v='10')]
        with patch.object(u,'datetime',Clock),patch.object(u,'mis_service_probe',return_value=(True,1,None)),patch.object(u,'fetch_mis_channels',side_effect=fetch):
            return u.enrich_live([dict(code='2330',market='TWSE',close=100)],
                                 datetime(2026,11,5,10,0,tzinfo=u.TZ) if frozen else None)
    def test_stock_uses_scan_completion_clock(self):
        self.assertEqual(self.scan()[1],1)
    def test_index_uses_clock_after_its_own_response(self):
        self.assertEqual(self.scan()[4]['index_quote_status'],'verified')
    def test_old_trade_remains_rejected(self):
        self.assertEqual(self.scan(stock_time='09:51:59')[1],0)
    def test_future_trade_and_index_remain_rejected(self):
        self.assertEqual(self.scan(stock_time='10:03:01')[1],0)
        self.assertIsNone(self.scan(index_time='10:04:01')[2])
    def test_explicit_historical_asof_is_never_advanced(self):
        result=self.scan(frozen=True)
        self.assertEqual(result[1],0)
        self.assertIsNone(result[2])

if __name__=='__main__':unittest.main()
