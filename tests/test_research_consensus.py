"""Evidence is not a ticker recommendation; repeated media citations count once."""
import copy
import json
import unittest
from datetime import date
from pathlib import Path
from scripts.research_consensus import build, validate_registry

REGISTRY=Path(__file__).resolve().parents[1]/"remote/research_sources.json"

class ResearchEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.sources=json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.today=date(2026,10,18)

    def test_valid_dated_public_industry_sources(self):
        self.assertTrue(validate_registry(self.sources))
        result=build(self.sources,self.today)
        self.assertTrue(result["research_evidence_only"])
        self.assertTrue(result["not_broker_rating"])
        mem=result["themes"]["記憶體/儲存"]
        self.assertEqual(mem["independent_institutions"],2)
        self.assertEqual(mem["institutions"],["SEMI","TrendForce"])
        self.assertFalse(mem["company_fundamentals_verified"])
        self.assertFalse(mem["actionable_buy_signal"])
        optical=result["themes"]["光通訊/CPO"]
        self.assertEqual(optical["independent_institutions"],1,
                         "three TrendForce articles count as one independent institution")
        self.assertGreaterEqual(optical["source_articles"],3)
        self.assertEqual(result["themes"]["航運"]["independent_institutions"],0)
        self.assertEqual(result["themes"]["PCB/載板"]["evidence_level"],"研究證據不足")

    def test_future_dated_and_old_reports_never_boost_independent_count(self):
        newer=build(self.sources,date(2026,1,1))
        self.assertEqual(newer["themes"]["光通訊/CPO"]["independent_institutions"],1)
        self.assertTrue(newer["themes"]["光通訊/CPO"]["excluded_sources"])
        aged=build(self.sources,date(2028,12,31))
        self.assertEqual(aged["themes"]["光通訊/CPO"]["independent_institutions"],0)
        self.assertEqual(aged["themes"]["半導體設備/測試"]["source_articles"],0)

    def test_institution_duplicate_cannot_forge_consensus(self):
        altered=copy.deepcopy(self.sources)
        repeated=copy.deepcopy(altered["sources"][0])
        repeated["id"]="another-reference-by-same-institution"
        altered["sources"].append(repeated)
        result=build(altered,self.today)
        self.assertEqual(result["themes"]["光通訊/CPO"]["independent_institutions"],1)
        self.assertEqual(result["themes"]["光通訊/CPO"]["source_articles"],4)

    def test_reject_unattributed_url_and_unknown_industry(self):
        for bad in ["http://example.com/x","https://someone:password@example.com/x",""]:
            changed=copy.deepcopy(self.sources)
            changed["sources"][0]["url"]=bad
            with self.subTest(url=bad),self.assertRaises(ValueError):
                validate_registry(changed)
        changed=copy.deepcopy(self.sources)
        changed["sources"][0]["sectors"]=["神祕妖股保證翻倍"]
        with self.assertRaises(ValueError):
            validate_registry(changed)

if __name__=="__main__":
    unittest.main()
