"""Fast index-only risk siren must not depend on a 1,973-stock feed scan."""
import contextlib
from datetime import datetime
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts import early_index_crash_alert as siren

TZ=ZoneInfo("Asia/Taipei")
NOW=datetime(2026,11,16,9,27,tzinfo=TZ)
SECRET="SENSITIVE_FAKE_TOKEN"
RECIPIENT="U"+"a"*32


def quote(**changes):
    m={"c":"t00","ex":"tse","ch":"t00.tw","d":"20261116",
       "t":"09:26:00","z":"970","y":"1000"}
    m.update(changes)
    return m


class EarlyIndexCrashTests(unittest.TestCase):
    def test_fast_3pct_drop_uses_only_verified_current_taiex_trade(self):
        report,reason=siren.report_for_index([quote()],NOW)
        self.assertEqual(reason,"verified_index_decline")
        self.assertEqual(report["edition"],"intraday_index_crash")
        self.assertEqual(report["status"],"ready")
        self.assertIn("-3.00%",report["blocks"][0]["items"][0])
        self.assertIn("尚非全市場",report["blocks"][1]["items"][0])
        self.assertNotIn("個股將下跌",str(report))

    def test_exact_two_percent_triggers_but_smaller_drop_does_not(self):
        self.assertIsNotNone(siren.report_for_index([quote(z="980")],NOW)[0])
        self.assertEqual(siren.report_for_index([quote(z="980.1")],NOW)[1],
                         "decline_below_threshold")

    def test_rejects_old_day_stale_time_wrong_exchange_and_wrong_index(self):
        bad=(
            {"d":"20261113"}, {"t":"09:16:00"},
            {"t":"09:29:00"}, {"c":"2330"}, {"ex":"otc"},
            {"ch":"2330.tw"}, {"y":"0"}, {"z":"-"},
        )
        for change in bad:
            with self.subTest(change=change):
                report,reason=siren.report_for_index([quote(**change)],NOW)
                self.assertIsNone(report)
                self.assertNotEqual(reason,"verified_index_decline")

    def test_duplicate_conflict_and_bid_ask_never_substitute_for_index_trade(self):
        report,reason=siren.report_for_index([quote(),quote(z="969")],NOW)
        self.assertIsNone(report)
        self.assertEqual(reason,"index_conflicting_quotes")
        report,reason=siren.report_for_index(
            [quote(z="-",b="1000_1001",a="900_901")],NOW)
        self.assertIsNone(report)

    def test_closed_day_or_offhours_never_notifies(self):
        for at in (
          datetime(2026,11,15,9,27,tzinfo=TZ),
          datetime(2026,12,25,9,27,tzinfo=TZ),
          datetime(2026,11,16,8,59,tzinfo=TZ),
          datetime(2026,11,16,13,31,tzinfo=TZ),
        ):
            with self.subTest(at=at):
                report,_=siren.report_for_index([quote()],at)
                self.assertIsNone(report)

    def test_master_switch_and_missing_credentials_stop_before_network(self):
        for environment,status in (
          ({"JEI_LINE_ALERTS_ENABLED":"false"},"disabled"),
          ({"JEI_LINE_ENABLED":"false"},"blocked"),
          ({"JEI_LINE_CHANNEL_ACCESS_TOKEN":""},"blocked"),
        ):
            env={"JEI_LINE_ENABLED":"true","JEI_LINE_ALERTS_ENABLED":"true",
                 "JEI_LINE_CHANNEL_ACCESS_TOKEN":SECRET,
                 "JEI_LINE_USER_ID":RECIPIENT}
            env.update(environment)
            receipt={"status":"failed"}
            with patch.dict(os.environ,env,clear=True),patch.object(siren,"fetch_mis_channels") as fetch:
                siren.dispatch(NOW,receipt)
                fetch.assert_not_called()
            self.assertEqual(receipt["status"],status)

    def test_accepted_api_is_not_phone_delivery_and_uses_separate_edition(self):
        receipt={"status":"failed","delivery_confirmed":False}
        env={"JEI_LINE_ENABLED":"true","JEI_LINE_ALERTS_ENABLED":"true",
             "JEI_LINE_CHANNEL_ACCESS_TOKEN":SECRET,"JEI_LINE_USER_ID":RECIPIENT}
        def fake_push(report,edition,token,recipient,receipt):
            self.assertEqual(edition,"intraday_index_crash")
            receipt.update(status="accepted",stage="push",http_status=200,attempts=1)
            return "LINE accepted"
        with patch.dict(os.environ,env,clear=True),patch.object(
             siren,"fetch_mis_channels",return_value=[quote()]) as fetch,patch.object(
             siren,"push",side_effect=fake_push) as push,contextlib.redirect_stdout(io.StringIO()):
            siren.dispatch(NOW,receipt)
            fetch.assert_called_once_with(["tse_t00.tw"])
            self.assertEqual(push.call_count,1)
        self.assertEqual(receipt["status"],"accepted")
        self.assertEqual(receipt["edition"],"intraday_index_crash")
        self.assertIs(receipt["delivery_confirmed"],False)
        self.assertNotIn(SECRET,json.dumps(receipt))
        self.assertNotIn(RECIPIENT,json.dumps(receipt))

    def test_mis_unavailable_saves_unverified_not_fabricated_red(self):
        receipt={}
        env={"JEI_LINE_ENABLED":"true","JEI_LINE_ALERTS_ENABLED":"true",
             "JEI_LINE_CHANNEL_ACCESS_TOKEN":SECRET,"JEI_LINE_USER_ID":RECIPIENT}
        with patch.dict(os.environ,env,clear=True),patch.object(
             siren,"fetch_mis_channels",side_effect=OSError("network unavailable")),patch.object(
             siren,"push") as push:
            siren.dispatch(NOW,receipt)
            push.assert_not_called()
        self.assertEqual((receipt["status"],receipt["reason_code"]),
                         ("unverified","index_source_unavailable"))


if __name__=="__main__":
    unittest.main()
