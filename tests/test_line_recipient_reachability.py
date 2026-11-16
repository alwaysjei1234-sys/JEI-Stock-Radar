"""LINE profile diagnostics should return only a coarse status, never PII."""
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from scripts import line_recipient_reachability as diag

TOKEN="SENSITIVE_TOKEN"
UID="U"+"a"*32
PII="PRIVATE-NAME-SHOULD-NOT-BE-READ"


class FakeResponse:
    status=200
    def __init__(self):self.read_count=0
    def __enter__(self):return self
    def __exit__(self,*args):return None
    def read(self):self.read_count+=1;raise AssertionError("PII profile body must never be read")


class RecipientProfileSafetyTests(unittest.TestCase):
    def test_valid_profile_checks_only_http_status_without_reading_body(self):
        response=FakeResponse();calls=[]
        def opener(req,timeout):
            calls.append((req.full_url,req.get_method(),timeout))
            return response
        self.assertEqual(diag.check_reachability(TOKEN,UID,opener),"profile_accessible")
        self.assertEqual(response.read_count,0)
        self.assertEqual(calls[0][1:],[ "GET", 10])
        self.assertEqual(len(calls),1)

    def test_missing_token_or_invalid_id_refuse_network(self):
        def no_network(*args,**kwargs):raise AssertionError("must not touch network")
        for token,user_id in (("",UID),(TOKEN,""),(TOKEN,"alice"),(TOKEN,"U"+"X"*32)):
            with self.subTest(value=user_id):
                self.assertEqual(diag.check_reachability(token,user_id,no_network),
                                 "credentials_unconfigured")

    def test_http_404_is_not_automatically_called_blocked(self):
        def fail(req,timeout):
            raise urllib.error.HTTPError(req.full_url,404,PII,None,None)
        self.assertEqual(diag.check_reachability(TOKEN,UID,fail),
                         "profile_not_accessible")

    def test_auth_and_network_are_separate_uncertain_states(self):
        for code,expected in ((401,"channel_auth_denied"),(403,"channel_auth_denied"),
                              (429,"rate_limited"),(500,"other_http_error")):
            def fail(req,timeout):
                raise urllib.error.HTTPError(req.full_url,code,PII,None,None)
            with self.subTest(code=code):
                self.assertEqual(diag.check_reachability(TOKEN,UID,fail),expected)
        def timeout(req, timeout):raise TimeoutError(PII)
        self.assertEqual(diag.check_reachability(TOKEN,UID,timeout),"network_unverified")

    def test_cli_artifact_and_stdout_do_not_contain_any_profile_or_secret(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"receipt.json"
            with patch.dict("os.environ",{
                  "JEI_LINE_CHANNEL_ACCESS_TOKEN": TOKEN,
                  "JEI_LINE_USER_ID": UID,
                }, clear=True),patch.object(diag,"check_reachability",return_value="profile_accessible"):
                with patch("sys.stdout",new_callable=io.StringIO) as stdout:
                    self.assertEqual(diag.main(["--out",str(out)]),0)
                    combined=stdout.getvalue()+out.read_text(encoding="utf-8")
            self.assertNotIn(TOKEN,combined)
            self.assertNotIn(UID,combined)
            self.assertNotIn(PII,combined)
            doc=json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(doc["handset_notification_confirmed"])
            self.assertFalse(doc["profile_delivery_proven"])


if __name__=="__main__":
    unittest.main()
