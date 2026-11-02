import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from scripts import send_line_brief as line

class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,2,9,10,tzinfo=ZoneInfo('Asia/Taipei'))

    def test_pending_check_sends_notice_without_old_prices_or_picks(self):
        old={'date':'2026-10-23','edition':'morning','status':'ready','blocks':[{'items':['OLD_PRICE','OLD_PICK']}]}
        doc={'morning':old,'checks':{'morning':{'date':'2026-11-02','status':'pending','note':'官方收盤行情尚未驗證'}}}
        report,edition=line.select_dispatch(doc,'morning',self.now)
        self.assertEqual(edition,'morning_unavailable')
        self.assertTrue(line.can_send(report,edition,self.now,'true','token','U'+'a'*32)[0])
        body=str(line.payload(report,'U'+'a'*32))
        self.assertNotIn('OLD_PRICE',body)
        self.assertNotIn('OLD_PICK',body)
        self.assertIn('未通過驗證',body)

    def test_recovery_uses_normal_independent_retry_bucket(self):
        current={'date':'2026-11-02','edition':'morning','status':'ready'}
        doc={'morning':current,'checks':{'morning':{'date':'2026-11-02','status':'ready'}}}
        self.assertEqual(line.select_dispatch(doc,'morning',self.now),(current,'morning'))

    def test_old_pending_check_never_creates_today_notice(self):
        doc={'checks':{'morning':{'date':'2026-10-30','status':'pending'}}}
        report,edition=line.select_dispatch(doc,'morning',self.now)
        self.assertFalse(line.can_send(report,edition,self.now,'true','token','U'+'a'*32)[0])
