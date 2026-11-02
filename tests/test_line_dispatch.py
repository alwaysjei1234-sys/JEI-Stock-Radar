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

class AcceptanceReceiptTests(unittest.TestCase):
    def test_api_acceptance_records_request_id_without_claiming_delivery(self):
        from unittest.mock import patch, MagicMock
        response=MagicMock()
        response.__enter__.return_value=response
        response.status=200
        response.headers={'x-line-request-id':'request-123'}
        receipt={'delivery_confirmed':False}
        with patch.object(line,'quota_ok',return_value=True), patch.object(line.urllib.request,'urlopen',return_value=response):
            line.push({'date':'2026-11-02'},'close','SECRET_TOKEN','U'+'a'*32,receipt=receipt)
        self.assertEqual(receipt['status'],'accepted')
        self.assertEqual(receipt['request_id'],'request-123')
        self.assertFalse(receipt['delivery_confirmed'])
        self.assertNotIn('SECRET_TOKEN',str(receipt))
        self.assertNotIn('U'+'a'*32,str(receipt))

    def test_conflict_requires_original_acceptance_evidence(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        for headers,accepted in [({},False),({'x-line-accepted-request-id':'original-request'},True)]:
            with self.subTest(headers=headers):
                receipt={}
                error=HTTPError(line.PUSH,409,'Conflict',headers,None)
                with patch.object(line,'quota_ok',return_value=True), patch.object(line.urllib.request,'urlopen',side_effect=error):
                    if accepted:
                        line.push({'date':'2026-11-02'},'close','token','U'+'a'*32,receipt=receipt)
                        self.assertEqual(receipt['status'],'already_accepted')
                        self.assertEqual(receipt['request_id'],'original-request')
                    else:
                        with self.assertRaises(RuntimeError):
                            line.push({'date':'2026-11-02'},'close','token','U'+'a'*32,receipt=receipt)
                        self.assertEqual(receipt['status'],'failed')

    def test_quota_block_does_not_contact_push_endpoint(self):
        from unittest.mock import patch
        receipt={}
        with patch.object(line,'quota_ok',return_value=False), patch.object(line.urllib.request,'urlopen') as network:
            line.push({'date':'2026-11-02'},'close','token','U'+'a'*32,receipt=receipt)
        network.assert_not_called()
        self.assertEqual(receipt['status'],'quota_blocked')

    def test_cli_failure_still_writes_safe_result(self):
        import json, tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'remote').mkdir()
            (root/'remote/brief.json').write_text('{}')
            output=root/'result.json'
            with patch.object(line,'ROOT',root), patch('sys.argv',['send_line_brief','--edition','close','--result-path',str(output)]), patch.dict('os.environ',{},clear=True):
                with self.assertRaises(SystemExit): line.main()
            result=json.loads(output.read_text())
            self.assertEqual(result['status'],'blocked')
            self.assertFalse(result['delivery_confirmed'])
            self.assertEqual(set(result),{'date','edition','checked_at','status','delivery_confirmed','reason'})

    def test_cli_network_failure_does_not_expose_exception_content(self):
        import json, tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'remote').mkdir()
            (root/'remote/brief.json').write_text('{}')
            output=root/'result.json'
            with patch.object(line,'ROOT',root), patch('sys.argv',['send_line_brief','--edition','close','--result-path',str(output)]), patch.object(line,'can_send',return_value=(True,'ready')), patch.object(line,'push',side_effect=OSError('SECRET_TOKEN')):
                with self.assertRaises(SystemExit) as raised: line.main()
            self.assertNotIn('SECRET_TOKEN',str(raised.exception))
            result=json.loads(output.read_text())
            self.assertEqual(result['status'],'failed')
            self.assertEqual(result['error_type'],'OSError')
            self.assertNotIn('SECRET_TOKEN',str(result))

class WorkflowDispatchPolicyTests(unittest.TestCase):
    def test_schedule_and_manual_send_policy(self):
        import os, subprocess, tempfile
        from pathlib import Path
        workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/jei-daily-brief.yml').read_text()
        block=workflow.split('      - name: Select edition and LINE policy\n',1)[1].split('      - name:',1)[0]
        script='\n'.join(line[10:] for line in block.split('        run: |\n',1)[1].splitlines())
        cases=[('55 0 * * 1-5','','','morning','true'),('10 1 * * 1-5','','','morning','true'),('25 1 * * 1-5','','','morning','true'),('30 7 * * 1-5','','','close','false'),('10 10 * * 1-5','','','close','true'),('','morning','true','morning','true'),('','close','false','close','false'),('','','','close','false')]
        for schedule,selected,manual,edition,send in cases:
            with self.subTest(schedule=schedule,selected=selected,manual=manual), tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output'
                subprocess.run(['bash','-e','-c',script],check=True,env={**os.environ,'SCHEDULE':schedule,'SELECTED':selected,'MANUAL_SEND':manual,'GITHUB_OUTPUT':str(output)})
                result=dict(line.split('=',1) for line in output.read_text().splitlines())
                self.assertEqual(result,{'name':edition,'send':send})
