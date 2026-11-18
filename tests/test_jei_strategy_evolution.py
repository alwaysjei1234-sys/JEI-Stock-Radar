import copy
import json
import unittest
from datetime import datetime

from tools.jei_strategy_evolution import compare, EFFECTIVE_DAY, POLICIES


def candidate(day="2026-11-19", rank=1, score=91, net=2.4, end="2026-11-24",
              origin="scheduled_close", group="attack", code="3017"):
    return {"id": f"{day}:{group}:{code}:{rank}", "day": day, "group": group,
            "code": code, "rank": rank, "score": score, "origin": origin,
            "outcomes": [{"trading_days": 3, "status": "complete", "end_day": end,
                          "estimated_net_return_pct": net}]}


def snapshot(items, latest="2026-11-24"):
    return {"schema": 1, "mode": "forward_official_close_pick_validation",
            "latest_official_day": latest, "picks": items}


class StrategyEvolutionTests(unittest.TestCase):
    def test_fixed_start_and_report_disclaimer(self):
        self.assertEqual(EFFECTIVE_DAY, "2026-11-19")
        self.assertEqual([x[0] for x in POLICIES],
                         ["baseline_top5", "rank_top1", "rank_top3", "score_at_least_85"])
        actual = compare(snapshot([], latest="2026-11-18"))
        self.assertFalse(actual["independent_oos_verified"])
        self.assertFalse(actual["real_execution_verified"])
        self.assertFalse(actual["automatic_promotions"])
        self.assertFalse(actual["uses_future_to_select_policy"])
        self.assertEqual(actual["status"], "WAITING_FOR_MATURE_PROSPECTIVE_SIGNALS")

    def test_history_never_retroactively_becomes_prospective(self):
        old = candidate(day="2026-11-18", end="2026-11-23")
        report = compare(snapshot([old], latest="2026-11-24"))
        self.assertEqual(report["prospective_signal_count"], 0)
        self.assertEqual(report["historic_observation_only"]["signals"], 1)

    def test_mature_future_only_and_prespecified_rank_filters(self):
        rows = []
        for idx in range(32):
            day = "2026-11-19"
            p = candidate(day=day, rank=1 if idx%4==0 else 4,
                          score=90 if idx%2==0 else 75,
                          net=3 if idx%3==0 else -2, code=str(3000+idx))
            rows.append(p)
        q = compare(snapshot(rows, latest="2026-11-24"))
        self.assertEqual(q["prospective_signal_count"], 32)
        group = q["prospective"]["attack"]
        self.assertEqual(group["baseline_top5"]["3"]["completed"], 32)
        self.assertEqual(group["baseline_top5"]["3"]["evidence"], "OBSERVED_SAMPLE_ONLY")
        self.assertEqual(group["rank_top1"]["3"]["completed"], 8)
        self.assertEqual(group["rank_top3"]["3"]["completed"], 8)
        self.assertEqual(group["score_at_least_85"]["3"]["completed"], 16)
        self.assertEqual(q["status"], "PROSPECTIVE_OBSERVATIONS_EXIST_NOT_VALIDATED_TRADES")
        self.assertEqual(q["mature_windows"], 1)
        self.assertIsNone(group["rank_top1"]["7"]["avg_estimated_net_pct"])
        self.assertFalse(q["independent_oos_verified"])

    def test_future_termination_does_not_leak_on_earlier_reference_day(self):
        row = candidate(end="2026-11-26", net=25)
        q = compare(snapshot([row], latest="2026-11-24"))
        self.assertEqual(q["prospective"]["attack"]["baseline_top5"]["3"]["completed"], 0)
        self.assertEqual(q["prospective"]["attack"]["baseline_top5"]["3"]["pending_or_invalid"], 1)
        self.assertIsNone(q["prospective"]["attack"]["baseline_top5"]["3"]["win_rate_pct"])

    def test_recovered_signal_must_have_contemporaneous_archive_commit(self):
        row = candidate(origin="recovered_mainline_close_observation")
        for stamp in (None, "bad", "2026-11-23T08:19:28Z", "2026-11-19T08:19:28Z"):
            with self.subTest(stamp=stamp):
                entry = copy.deepcopy(row)
                if stamp is not None:
                    entry["source_committed_at"] = stamp
                q = compare(snapshot([entry]))
                accepted = stamp=="2026-11-19T08:19:28Z"
                self.assertEqual(q["prospective_signal_count"], 1 if accepted else 0)

    def test_invalid_or_duplicate_archive_fails_closed(self):
        one = candidate()
        for records in ([one,copy.deepcopy(one)], [{**one,"id":None}], [123]):
            with self.subTest(records=records):
                q=compare(snapshot(records))
                self.assertTrue(q["status"].startswith("INVALID_"))
                self.assertNotIn("prospective", q)
        q=compare({"schema": 1,"mode":"not_verified","picks":[one]})
        self.assertEqual(q["status"], "INVALID_SOURCE")

    def test_bootstrap_records_ignored_and_scores_boolean_blocked(self):
        boot=candidate(day="2026-11-19",origin="verified_archive_bootstrap")
        invalid=candidate(rank=True,code="1234")
        good=candidate(rank=2,score=80,code="2222")
        q=compare(snapshot([boot,invalid,good]))
        self.assertEqual(q["prospective_signal_count"], 1)
        self.assertEqual(q["prospective"]["attack"]["score_at_least_85"]["3"]["completed"],0)

    def test_never_modify_frozen_pick_archive(self):
        r=snapshot([candidate()])
        before=copy.deepcopy(r)
        _=compare(r)
        self.assertEqual(r,before)


if __name__=="__main__":
    unittest.main()
