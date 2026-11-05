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
    def test_close_backups_reuse_daily_key_after_report_refresh(self):
        from unittest.mock import patch, MagicMock
        from urllib.error import HTTPError
        response=MagicMock();response.__enter__.return_value=response
        response.status=200;response.headers={'x-line-request-id':'original'}
        duplicate=HTTPError(line.PUSH,409,'conflict',{'x-line-accepted-request-id':'original'},None)
        receipts=[]
        with patch.object(line,'quota_ok',return_value=True), patch.object(line.urllib.request,'urlopen',side_effect=[response,duplicate,duplicate]) as network, patch.object(line.time,'sleep') as pause:
            for stamp in ('18:10','18:40','19:10'):
                report={'date':'2026-11-03','edition':'close','status':'ready','title':'close '+stamp}
                receipt={'delivery_confirmed':False}
                line.push(report,'close','test-token','U'+'a'*32,receipt)
                receipts.append(receipt)
        self.assertEqual([r['status'] for r in receipts],['accepted','already_accepted','already_accepted'])
        self.assertEqual(len({c.args[0].get_header('X-line-retry-key') for c in network.call_args_list}),1)
        self.assertEqual(network.call_count,3)
        self.assertTrue(all(r['attempts']==1 and not r['delivery_confirmed'] for r in receipts))
        pause.assert_not_called()

    def test_transient_push_retries_same_body_and_key_with_bounded_backoff(self):
        from unittest.mock import patch, MagicMock, call
        from urllib.error import HTTPError
        response=MagicMock();response.__enter__.return_value=response
        response.status=200;response.headers={'x-line-request-id':'accepted'}
        receipt={'delivery_confirmed':False}
        report={'date':'2026-11-02','title':'original'}
        requests=[]
        def respond(request,timeout):
            requests.append(request)
            # A mutable caller must not alter the already-frozen retry body.
            report['title']='changed later'
            if len(requests)<3:raise HTTPError(line.PUSH,503,'SECRET_TOKEN',{},None)
            return response
        with patch.object(line,'quota_ok',return_value=True) as quota, patch.object(line.urllib.request,'urlopen',side_effect=respond), patch.object(line.time,'sleep') as pause:
            line.push(report,'close','SECRET_TOKEN','U'+'a'*32,receipt)
        self.assertEqual(quota.call_count,1)
        self.assertEqual(len(requests),3)
        self.assertEqual(len({r.data for r in requests}),1)
        self.assertEqual(len({r.get_header('X-line-retry-key') for r in requests}),1)
        self.assertIn(b'original',requests[0].data)
        self.assertEqual(pause.call_args_list,[call(1),call(2)])
        self.assertEqual(receipt['attempts'],3)
        self.assertEqual(receipt['status'],'accepted')
        self.assertFalse(receipt['delivery_confirmed'])
        self.assertNotIn('SECRET_TOKEN',str(receipt))

    def test_timeout_then_proven_duplicate_stops_without_extra_push(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        receipt={}
        errors=[TimeoutError('SECRET_TOKEN'),HTTPError(line.PUSH,409,'conflict',{'x-line-accepted-request-id':'original'},None)]
        with patch.object(line,'quota_ok',return_value=True), patch.object(line.urllib.request,'urlopen',side_effect=errors) as network, patch.object(line.time,'sleep') as pause:
            line.push({'date':'2026-11-02'},'close','SECRET_TOKEN','U'+'a'*32,receipt)
        self.assertEqual(network.call_count,2)
        pause.assert_called_once_with(1)
        self.assertEqual(receipt['status'],'already_accepted')

    def test_permanent_http_errors_are_not_retried(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        for code in (400,401,403,409,429):
            with self.subTest(code=code):
                receipt={}
                with patch.object(line,'quota_ok',return_value=True), patch.object(line.urllib.request,'urlopen',side_effect=HTTPError(line.PUSH,code,'SECRET_TOKEN',{},None)) as network, patch.object(line.time,'sleep') as pause:
                    with self.assertRaises(RuntimeError):line.push({'date':'2026-11-02'},'close','SECRET_TOKEN','U'+'a'*32,receipt)
                self.assertEqual(network.call_count,1);pause.assert_not_called()
                self.assertEqual(receipt['status'],'failed')

    def test_retry_exhaustion_is_bounded_and_does_not_leak_network_error(self):
        from unittest.mock import patch,call
        from urllib.error import HTTPError,URLError
        for error in (HTTPError(line.PUSH,500,'SECRET_TOKEN',{},None),URLError('SECRET_TOKEN')):
            with self.subTest(error=type(error).__name__):
                receipt={}
                with patch.object(line,'quota_ok',return_value=True), patch.object(line.urllib.request,'urlopen',side_effect=error) as network, patch.object(line.time,'sleep') as pause:
                    with self.assertRaises(RuntimeError) as raised:line.push({'date':'2026-11-02'},'close','SECRET_TOKEN','U'+'a'*32,receipt)
                self.assertEqual(network.call_count,3)
                self.assertEqual(pause.call_args_list,[call(1),call(2)])
                self.assertEqual(receipt['status'],'failed')
                self.assertNotIn('SECRET_TOKEN',str(raised.exception)+str(receipt))

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
        cases=[('55 0 * * 1-5','','','morning','true'),('10 1 * * 1-5','','','morning','true'),('25 1 * * 1-5','','','morning','true'),('30 7 * * 1-5','','','close','false'),('10 10 * * 1-5','','','close','true'),('40 10 * * 1-5','','','close','true'),('10 11 * * 1-5','','','close','true'),('','morning','true','morning','true'),('','close','false','close','false'),('','','','close','false')]
        for schedule,_,_,_,_ in cases:
            if schedule:
                self.assertIn("- cron: '"+schedule+"'",workflow)
        for schedule,selected,manual,edition,send in cases:
            with self.subTest(schedule=schedule,selected=selected,manual=manual), tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'output'
                subprocess.run(['bash','-e','-c',script],check=True,env={**os.environ,'SCHEDULE':schedule,'SELECTED':selected,'MANUAL_SEND':manual,'EVENT':'schedule' if schedule else 'workflow_dispatch' if manual else 'push','COMMIT_MESSAGE':'','GITHUB_OUTPUT':str(output)})
                result=dict(line.split('=',1) for line in output.read_text().splitlines())
                self.assertEqual(result,{'name':edition,'send':send})

class StrategySummaryTests(unittest.TestCase):
    def make_paper(self):
        return {'last_processed_day':'2026-11-02','capital_per_strategy':1000000,
                'strategies':{key:{'name':name,'summary':{'estimated_liquidation_equity_ntd':900000,'closed':20,'wins':5}} for key,name in [('fixed5','固定 +5%'),('fixed7','固定 +7%'),('fixed10','固定 +10%'),('trailing','移動停利')]}}

    def test_all_four_strategies_and_limits_survive_line_summary(self):
        from scripts.build_daily_brief import paper_block
        report={'blocks':[{'title':'other','items':['market']},paper_block(self.make_paper(),'2026-11-02')]}
        message=line.payload(report,'U'+'a'*32)['messages'][0]['text']
        for name in ['固定 +5%','固定 +7%','固定 +10%','移動停利']:
            self.assertIn(name,message)
        self.assertEqual(message.count('勝率 25.00%'),4)
        self.assertEqual(message.count('相對初始 -10.00%'),4)
        self.assertIn('滑價',message)
        self.assertIn('樣本外',message)
        self.assertLessEqual(len(message),3500)

    def test_stale_performance_warning_does_not_displace_fourth_strategy(self):
        from scripts.build_daily_brief import paper_block
        block=paper_block(self.make_paper(),'2026-11-03')
        message=line.payload({'blocks':[block]},'U'+'a'*32)['messages'][0]['text']
        self.assertIn('請勿視為最新績效',message)
        self.assertIn('移動停利',message)
        self.assertIn('樣本外',message)

    def test_invalid_or_zero_counts_do_not_invent_win_rate(self):
        from scripts.build_daily_brief import paper_block
        for closed,wins,expected in [(0,0,'勝率待累積'),(5,6,'勝率待驗證'),(True,True,'勝率待驗證'),(None,None,'勝率待驗證')]:
            with self.subTest(closed=closed,wins=wins):
                paper=self.make_paper()
                paper['strategies']={'fixed5':paper['strategies']['fixed5']}
                paper['strategies']['fixed5']['summary'].update(closed=closed,wins=wins,win_rate_pct=99)
                block=paper_block(paper,'2026-11-02')
                self.assertIn(expected,str(block))
                self.assertNotIn('99%',str(block))

    def test_legacy_brief_also_keeps_four_strategy_rows(self):
        block={'title':'四策略模擬復盤','items':['date','fixed5','fixed7','fixed10','trailing']}
        message=line.payload({'blocks':[block]},'U'+'a'*32)['messages'][0]['text']
        for row in block['items']: self.assertIn(row,message)

class QuotaPreflightRecoveryTests(unittest.TestCase):
    @staticmethod
    def response(body):
        import json
        from unittest.mock import MagicMock
        result=MagicMock()
        result.__enter__.return_value=result
        result.status=200
        result.read.return_value=json.dumps(body).encode()
        return result

    def test_transient_quota_reads_recover_before_one_push(self):
        from unittest.mock import patch, call
        from urllib.error import HTTPError
        replies=[HTTPError(line.BASE,503,'SECRET_TOKEN',{},None),
                 self.response({'type':'limited','value':200}),
                 TimeoutError('SECRET_TOKEN'),self.response({'totalUsage':10}),
                 self.response({})]
        receipt={'delivery_confirmed':False}
        with patch.object(line.urllib.request,'urlopen',side_effect=replies) as network, patch.object(line.time,'sleep') as pause:
            line.push({'date':'2026-11-03'},'close','SECRET_TOKEN','U'+'a'*32,receipt)
        methods=[c.args[0].get_method() for c in network.call_args_list]
        self.assertEqual(methods,['GET','GET','GET','GET','POST'])
        self.assertEqual(pause.call_args_list,[call(1),call(1)])
        self.assertEqual((receipt['status'],receipt['stage']),('accepted','push'))
        self.assertFalse(receipt['delivery_confirmed'])
        self.assertNotIn('SECRET_TOKEN',str(receipt))

    def test_quota_outage_exhausts_without_push(self):
        from unittest.mock import patch,call
        from urllib.error import URLError
        receipt={}
        with patch.object(line.urllib.request,'urlopen',side_effect=URLError('SECRET_TOKEN')) as network, patch.object(line.time,'sleep') as pause:
            with self.assertRaises(RuntimeError) as error:
                line.push({'date':'2026-11-03'},'close','token','U'+'a'*32,receipt)
        self.assertEqual(network.call_count,3)
        self.assertTrue(all(c.args[0].get_method()=='GET' for c in network.call_args_list))
        self.assertEqual(pause.call_args_list,[call(1),call(2)])
        self.assertEqual(receipt['stage'],'quota')
        self.assertNotIn('SECRET_TOKEN',str(error.exception))

    def test_permanent_quota_http_errors_stop_without_push(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        for status in (400,401,403,429):
            with self.subTest(status=status), patch.object(line.urllib.request,'urlopen',side_effect=HTTPError(line.BASE,status,'SECRET_TOKEN',{},None)) as network, patch.object(line.time,'sleep') as pause:
                with self.assertRaises(RuntimeError):
                    line.push({'date':'2026-11-03'},'close','token','U'+'a'*32,{})
                self.assertEqual(network.call_count,1)
                pause.assert_not_called()

    def test_malformed_or_non_object_quota_does_not_retry_or_push(self):
        from unittest.mock import patch
        for body in ([],None,'invalid'):
            with self.subTest(body=body), patch.object(line.urllib.request,'urlopen',return_value=self.response(body)) as network, patch.object(line.time,'sleep') as pause:
                with self.assertRaises(ValueError):
                    line.push({'date':'2026-11-03'},'close','token','U'+'a'*32,{})
                self.assertEqual(network.call_count,1)
                pause.assert_not_called()

    def test_boolean_quota_values_never_authorize_push(self):
        from unittest.mock import patch
        for maximum,used in ((True,0),(200,False)):
            with self.subTest(maximum=maximum,used=used), patch.object(line.urllib.request,'urlopen',side_effect=[self.response({'type':'limited','value':maximum}),self.response({'totalUsage':used})]) as network:
                receipt={}
                line.push({'date':'2026-11-03'},'close','token','U'+'a'*32,receipt)
                self.assertEqual(receipt['status'],'quota_blocked')
                self.assertEqual(receipt['stage'],'quota')
                self.assertEqual(network.call_count,2)
