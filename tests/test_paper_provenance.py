import copy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from scripts import paper_provenance as evidence
from scripts import update_paper_performance as p
from test_paper_performance import feed,archive,prices,DAY1,DAY2,DAY3

NOW=datetime(2026,11,5,21,5,tzinfo=p.TZ)

class PaperProvenanceTests(unittest.TestCase):
    def spec(self,root):
        for name in evidence.RULE_FILES:
            file=root/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(name)
        return evidence.rule_spec(root,p.provenance_settings())

    def test_rule_version_changes_with_code_or_cost_but_not_input_order(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);a=self.spec(root)
            self.assertEqual(a,evidence.rule_spec(root,dict(reversed(list(p.provenance_settings().items())))))
            file=root/evidence.RULE_FILES[0];file.write_text(file.read_text()+'changed')
            self.assertNotEqual(a['version'],evidence.rule_spec(root,p.provenance_settings())['version'])
            changed=p.provenance_settings();changed['buy_fee_rate']=.002
            self.assertNotEqual(a['version'],evidence.rule_spec(root,changed)['version'])

    def test_snapshot_excludes_private_holdings_and_marks_historical_reconstruction(self):
        f=feed(DAY1);before=copy.deepcopy(f)
        record=evidence.capture(f,DAY1,[{'code':'2603','day':DAY1,'signal_close':100}],p.provenance_settings(),now=NOW)
        self.assertTrue(record['reconstructed'])
        self.assertEqual(record['qualification'],'provenance_only')
        self.assertNotIn('123456',str(record))
        self.assertNotIn('PRIVATE',str(record))
        self.assertEqual(f,before)
        changed=copy.deepcopy(f);changed['holdings']={'another':'PRIVATE'}
        again=evidence.capture(changed,DAY1,[{'code':'2603','day':DAY1,'signal_close':100}],p.provenance_settings(),now=NOW)
        self.assertEqual(record['snapshot_sha256'],again['snapshot_sha256'])

    def test_real_record_time_is_not_backdated_to_signal_day(self):
        row=evidence.capture(feed(DAY1),DAY1,[],p.provenance_settings(),now=NOW)
        self.assertEqual(row['recorded_at'],NOW.isoformat(timespec='seconds'))
        self.assertTrue(row['reconstructed'])
        with self.assertRaises(ValueError):evidence.capture(feed(DAY1),DAY1,[],p.provenance_settings(),now=NOW.replace(tzinfo=None))

    def test_signal_entry_exit_keep_identical_provenance_without_changing_fills(self):
        state=p.initial_state();a=archive((DAY1,100))
        p.advance(feed(DAY1),a,state,DAY1)
        proof=copy.deepcopy(state['signals'][0]['provenance'])
        a['days'][DAY2]=prices(100);p.advance(feed(DAY2,False),a,state,DAY2)
        self.assertEqual(state['strategies']['fixed5']['positions'][0]['provenance'],proof)
        a['days'][DAY3]=prices(106);p.advance(feed(DAY3,False),a,state,DAY3)
        closed=state['strategies']['fixed5']['closed'][0]
        self.assertEqual(closed['provenance'],proof)
        self.assertEqual(closed['entry_day'],DAY2);self.assertEqual(closed['exit_day'],DAY3)

    def test_same_day_replay_does_not_add_provenance_to_old_public_book(self):
        root=Path(__file__).resolve().parents[1]
        state=json.loads((root/'remote/strategy_performance.json').read_text());before=copy.deepcopy(state)
        f=json.loads((root/'remote/system.json').read_text());a=json.loads((root/'remote/daily_prices.json').read_text())
        self.assertFalse(p.advance(f,a,state,state['last_processed_day']))
        self.assertEqual(state,before)

    def test_copy_rejects_extra_private_fields_or_unverified_qualification(self):
        row=evidence.capture(feed(DAY1),DAY1,[],p.provenance_settings(),now=NOW)
        for change in [{'cost':123456},{'qualification':'out_of_sample_verified'},{'snapshot_sha256':'bad'},{'source_commit':None,'source_dirty':False}]:
            with self.subTest(change=change),self.assertRaises(ValueError):evidence.copy_record({**row,**change})
        cloned=evidence.copy_record(row);self.assertEqual(cloned,row);self.assertIsNot(cloned,row)
        self.assertIsNone(evidence.copy_record(None))

    def test_registration_requires_future_date_and_never_overwrites(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);spec=self.spec(root);path=root/'protocol.json'
            for day in ['2026-11-05','2026-11-04','20261106']:
                with self.subTest(day=day),self.assertRaises(ValueError):evidence.register(spec,day,path,NOW)
            evidence.register(spec,'2026-11-06',path,NOW)
            doc=json.loads(path.read_text());self.assertEqual(doc['qualification'],'protocol_registration_only')
            self.assertEqual(doc['effective_from'],'2026-11-06')
            before=path.read_bytes()
            with self.assertRaises(FileExistsError):evidence.register(spec,'2026-11-06',path,NOW)
            self.assertEqual(path.read_bytes(),before)

    def test_evidence_capture_failure_does_not_mutate_cash_or_positions(self):
        from unittest.mock import patch
        state=p.initial_state();a=archive((DAY1,100),(DAY2,100))
        p.advance(feed(DAY1),a,state,DAY1);p.advance(feed(DAY2,False),a,state,DAY2)
        a['days'][DAY3]=prices(106);before=copy.deepcopy(state)
        with patch.object(p,'capture_provenance',side_effect=OSError('unavailable source')):
            with self.assertRaises(OSError):p.advance(feed(DAY3),a,state,DAY3)
        self.assertEqual(state,before)
