import json
import unittest
from unittest.mock import Mock,patch
from urllib.error import HTTPError,URLError
from scripts import diagnose_line_recipient as d


class LineRecipientDiagnosticTests(unittest.TestCase):
    uid='U'+'a'*32
    token='PRIVATE_TOKEN'

    def response(self,body,status=200):
        r=Mock();r.status=status;r.read.return_value=body
        r.__enter__=Mock(return_value=r);r.__exit__=Mock(return_value=False)
        return r

    def test_accessible_is_read_only_and_never_returns_profile_information(self):
        opener=Mock();opener.open.return_value=self.response(json.dumps({'userId':self.uid,'displayName':'PRIVATE_NAME','pictureUrl':'PRIVATE_URL'}).encode())
        r=d.diagnose('true',self.token,self.uid,opener)
        self.assertEqual(r['status'],'profile_accessible')
        self.assertFalse(r['delivery_confirmed']);self.assertFalse(r['message_sent'])
        req=opener.open.call_args.args[0]
        self.assertEqual(req.get_method(),'GET');self.assertIsNone(req.data)
        self.assertEqual(opener.open.call_count,1)
        for secret in (self.uid,self.token,'PRIVATE_NAME','PRIVATE_URL'):
            self.assertNotIn(secret,json.dumps(r))

    def test_profile_404_is_ambiguous_and_not_retried(self):
        opener=Mock();opener.open.side_effect=HTTPError('PRIVATE_URL',404,'PRIVATE',{},None)
        r=d.diagnose('true',self.token,self.uid,opener)
        self.assertEqual(r['status'],'recipient_unavailable')
        self.assertEqual(r['profile_http_status'],404)
        self.assertEqual(opener.open.call_count,1)
        self.assertNotIn('blocked',json.dumps(r))

    def test_credentials_and_rate_limits_are_distinct_without_retries(self):
        for code,status in [(400,'recipient_rejected'),(401,'token_rejected'),(403,'permission_denied'),(429,'rate_limited'),(302,'unexpected_response')]:
            opener=Mock();opener.open.side_effect=HTTPError('PRIVATE',code,'PRIVATE',{},None)
            r=d.diagnose('true',self.token,self.uid,opener)
            self.assertEqual(r['status'],status);self.assertEqual(r['attempts'],1)

    def test_transient_error_retries_once_and_recovers(self):
        opener=Mock();opener.open.side_effect=[URLError('PRIVATE'),self.response(json.dumps({'userId':self.uid}).encode())]
        with patch.object(d.time,'sleep') as sleep:r=d.diagnose('true',self.token,self.uid,opener)
        self.assertEqual(r['status'],'profile_accessible');self.assertEqual(r['attempts'],2)
        sleep.assert_called_once_with(1)

    def test_persistent_service_or_transport_errors_are_bounded_and_sanitized(self):
        for error,status in [(HTTPError('PRIVATE',503,'PRIVATE',{},None),'service_error'),(URLError('PRIVATE'),'network_error')]:
            opener=Mock();opener.open.side_effect=error
            with patch.object(d.time,'sleep'):r=d.diagnose('true',self.token,self.uid,opener)
            self.assertEqual(r['status'],status);self.assertEqual(opener.open.call_count,2)
            self.assertNotIn('PRIVATE',json.dumps(r))

    def test_unknown_body_mismatched_user_and_oversize_are_not_accessible(self):
        for body,status in [(b'not JSON PRIVATE','invalid_response'),(b'[]','profile_mismatch'),(b'{"userId":"OTHER_PRIVATE"}','profile_mismatch'),(b'x'*65537,'invalid_response')]:
            opener=Mock();opener.open.return_value=self.response(body)
            r=d.diagnose('true',self.token,self.uid,opener)
            self.assertEqual(r['status'],status);self.assertEqual(r['attempts'],1)
            self.assertNotIn('PRIVATE',json.dumps(r))

    def test_disabled_or_invalid_configuration_never_contacts_api(self):
        for enabled,token,uid in [('false',self.token,self.uid),('true','',self.uid),('true',self.token,'Ubad'),('true',self.token,None)]:
            opener=Mock();r=d.diagnose(enabled,token,uid,opener)
            self.assertNotEqual(r['status'],'profile_accessible');opener.open.assert_not_called()

    def test_redirects_never_forward_token_or_user_id(self):
        self.assertIsNone(d.NoRedirect().redirect_request(None,None,302,'redirect',{},'https://example.com'))


if __name__=='__main__':unittest.main()
