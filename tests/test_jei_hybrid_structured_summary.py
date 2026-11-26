import json
import unittest
from tools.jei_hybrid_audit import summary_counts, validate_summary_response
from jei_local_ai_router import MODEL

def response(n, weak, category, **extra):
    return {"model":MODEL,"done":True,"done_reason":"stop",
            "message":{"content":json.dumps({"eligible_aggregates":n,
                       "underperforming_aggregates":weak,"classification":category})},**extra}

class StructuredSummaryTests(unittest.TestCase):
    def test_four_classes(self):
        for n,w,category in ((0,0,"no_samples"),(7,0,"none_weak"),(8,3,"some_weak"),(5,5,"all_weak")):
            counts=summary_counts({"eligible_aggregates":n,"underperforming_aggregates":w})
            text=validate_summary_response(response(n,w,category),counts)
            self.assertIn(f"共 {n} 組，其中 {w} 組",text)
            self.assertIn("並非獨立樣本外回測",text)

    def test_wrong_counts_classification_or_boolean_rejected(self):
        counts=summary_counts({"eligible_aggregates":1,"underperforming_aggregates":1})
        for bad in (response(2,1,"some_weak"),response(1,1,"none_weak"),
                    response(True,1,"all_weak")):
            with self.assertRaisesRegex(ValueError,"incorrect_model_classification"):
                validate_summary_response(bad,counts)

    def test_token_limit_rejected_even_if_json_complete(self):
        counts=summary_counts({"eligible_aggregates":5,"underperforming_aggregates":5})
        with self.assertRaisesRegex(ValueError,"model_token_limit"):
            validate_summary_response(response(5,5,"all_weak",done_reason="length"),counts)

    def test_extra_fields_and_reasoning_text_rejected(self):
        counts=summary_counts({"eligible_aggregates":5,"underperforming_aggregates":5})
        for payload,code in (("reasoning first", "invalid_model_json"),
            (json.dumps({"eligible_aggregates":5,"underperforming_aggregates":5,
                         "classification":"all_weak","trade":"buy"}),"incorrect_model_classification")):
            with self.assertRaisesRegex(ValueError,code):
                validate_summary_response(response(5,5,"all_weak",message={"content":payload}),counts)

    def test_invalid_input_fails_closed(self):
        for n,w in ((1,2),(-1,0),(True,1),(10001,0),(1,False)):
            with self.assertRaises(ValueError):
                summary_counts({"eligible_aggregates":n,"underperforming_aggregates":w})
