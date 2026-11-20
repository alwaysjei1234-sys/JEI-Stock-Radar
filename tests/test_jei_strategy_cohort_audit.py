"""Fail-closed integrity checks for real frozen prospective pick cohorts."""
import copy
import unittest

from scripts.update_pick_validation import net_percent
from tools.jei_strategy_cohort_audit import audit_cohorts
from tools.jei_strategy_evolution import EFFECTIVE_DAY

DAYS = ("2026-11-19", "2026-11-20", "2026-11-23", "2026-11-24")
POLICY = "jei-user-radar-gates-v1"


def sample():
    # Every day has 500+ valid quotes. Four consecutive trading days
    # 11/19 Thu -> 11/20 Fri -> 11/23 Mon -> 11/24 Tue.
    day_prices = {}
    for i, day in enumerate(DAYS):
        day_prices[day] = {str(3000+x): 100.0 for x in range(500)}
        day_prices[day]["3017"] = 100.0+10*i/3
    archive = {"schema": 1, "kind": "official_daily_close", "days": day_prices}
    ledger = {"schema": 1, "mode": "immutable_asof_pick_archive", "picks": []}
    for day in DAYS:
        row = {"id": f"{day}:attack:3017", "day": day,
               "group": "attack", "code": "3017", "rank": 1,
               "score": 88.0, "signal_close": archive["days"][day]["3017"],
               "origin": "scheduled_close", "selection_policy": POLICY}
        ledger["picks"].append(row)
    report = {"schema": 1, "mode": "forward_official_close_pick_validation",
              "latest_official_day": DAYS[-1], "picks": []}
    for row in ledger["picks"]:
        copy_row = copy.deepcopy(row)
        copy_row["outcomes"] = [
            {"trading_days": h, "status": "pending"}
            for h in (3, 7, 15, 20, 30, 40, 60)]
        if row["day"] == DAYS[0]:
            copy_row["outcomes"][0] = {
                "trading_days": 3, "status": "complete", "end_day": DAYS[3],
                "end_close": archive["days"][DAYS[3]]["3017"],
                "estimated_net_return_pct": round(net_percent(100, 110), 3),
                "observed_closes": 3, "expected_closes": 3,
            }
        report["picks"].append(copy_row)
    return report, ledger, archive


class ProspectiveCohortIntegrityTests(unittest.TestCase):
    def test_exact_four_day_archive_and_complete_three_day_outcome_passes(self):
        report, ledger, prices = sample()
        x = audit_cohorts(report, ledger, prices, EFFECTIVE_DAY)
        self.assertEqual(x["status"], "PASS")
        self.assertEqual(x["official_sessions_checked"], 4)
        self.assertEqual(x["prospective_frozen_picks"], 4)
        self.assertTrue(x["ledger_matches_outcomes"])

    def test_missing_whole_signal_day_blocks_instead_of_hiding_losers(self):
        report, ledger, prices = sample()
        target = DAYS[1]
        ledger["picks"] = [x for x in ledger["picks"] if x["day"] != target]
        report["picks"] = [x for x in report["picks"] if x["day"] != target]
        outcome = audit_cohorts(report, ledger, prices, EFFECTIVE_DAY)
        self.assertEqual(outcome["reason"], "missing_or_conflicting_sealed_daily_cohort")
        self.assertEqual(outcome["trading_day"], target)

    def test_verified_empty_session_is_accepted_but_conflict_is_blocked(self):
        report, ledger, prices = sample()
        target = DAYS[1]
        ledger["picks"] = [x for x in ledger["picks"] if x["day"] != target]
        report["picks"] = [x for x in report["picks"] if x["day"] != target]
        ledger["empty_sessions"] = [{"day": target, "status": "verified_no_candidates",
                                     "selection_policy": POLICY}]
        self.assertEqual(audit_cohorts(report, ledger, prices, EFFECTIVE_DAY)["status"], "PASS")
        ledger["picks"].append(sample()[1]["picks"][1])
        report["picks"].append(sample()[0]["picks"][1])
        self.assertEqual(audit_cohorts(report, ledger, prices, EFFECTIVE_DAY)["reason"],
                         "missing_or_conflicting_sealed_daily_cohort")

    def test_omitted_signal_even_when_report_still_runs_blocks(self):
        report, ledger, prices = sample()
        report["picks"].pop()
        self.assertEqual(audit_cohorts(report, ledger, prices, EFFECTIVE_DAY)["reason"],
                         "frozen_pick_ids_differ")

    def test_modified_rank_score_and_entry_price_cannot_improve_hindsight(self):
        for field, change in (("rank", 2), ("score", 100), ("signal_close", 80)):
            report, ledger, prices = sample()
            report["picks"][0][field] = change
            with self.subTest(field=field):
                self.assertEqual(audit_cohorts(report, ledger, prices, EFFECTIVE_DAY)["reason"],
                                 "recomputed_or_repriced_frozen_pick")

    def test_missing_official_trade_day_blocks(self):
        report, ledger, prices = sample()
        prices["days"].pop(DAYS[1])
        self.assertEqual(audit_cohorts(report, ledger, prices, EFFECTIVE_DAY)["reason"],
                         "missing_or_unexpected_official_session")

    def test_future_exit_and_fabricated_return_are_rejected(self):
        for modified in ({"end_day": "2026-11-25"},
                         {"estimated_net_return_pct": 91.0},
                         {"observed_closes": 2},
                         {"end_close": 120.0}):
            report, ledger, prices = sample()
            report["picks"][0]["outcomes"][0].update(modified)
            with self.subTest(modified=modified):
                self.assertEqual(audit_cohorts(report, ledger, prices, EFFECTIVE_DAY)["reason"],
                                 "prospective_outcome_not_reproducible_from_closes")

    def test_completed_horizon_before_official_future_day_blocks(self):
        report, ledger, prices = sample()
        report["picks"][-1]["outcomes"][0] = {
            "trading_days": 3, "status": "complete", "end_day": "2026-11-27",
            "end_close": 110.0, "estimated_net_return_pct": 4.0,
            "observed_closes": 3, "expected_closes": 3,
        }
        self.assertEqual(audit_cohorts(report, ledger, prices, EFFECTIVE_DAY)["reason"],
                         "future_outcome_claimed_complete")

    def test_policy_drift_must_not_be_mixed_with_registered_original(self):
        report, ledger, prices = sample()
        ledger["picks"][0]["selection_policy"] = "retuned-after-seeing-results"
        report["picks"][0]["selection_policy"] = "retuned-after-seeing-results"
        self.assertEqual(audit_cohorts(report, ledger, prices, EFFECTIVE_DAY)["reason"],
                         "invalid_or_changed_prospective_selection_policy")

    def test_new_archive_without_report_and_old_no_cohort_cases(self):
        report, ledger, prices = sample()
        report["latest_official_day"] = DAYS[-2]
        self.assertEqual(audit_cohorts(report, ledger, prices, EFFECTIVE_DAY)["reason"],
                         "outcome_report_and_official_archive_date_disagree")
        # Before effective date, a complete historical archive may legitimately
        # have zero prospective picks.
        older = {"schema": 1, "kind": "official_daily_close",
                 "days": {"2026-11-17": prices["days"][DAYS[0]]}}
        report["latest_official_day"] = "2026-11-17"
        ledger["picks"] = []
        report["picks"] = []
        self.assertEqual(audit_cohorts(report, ledger, older, EFFECTIVE_DAY)["status"],
                         "PASS_PRE_EFFECTIVE_DAY")

    def test_invalid_archive_is_not_a_success(self):
        report, ledger, prices = sample()
        for bad in (None, {}, {"schema": 1,"kind": "official_daily_close","days": {}}):
            outcome = audit_cohorts(report, ledger, bad, EFFECTIVE_DAY)
            self.assertEqual(outcome["status"], "BLOCKED")

    def test_mature_outcome_cannot_be_hidden_as_pending_or_missing(self):
        for status in ("pending", "missing_price", "corporate_action_unadjusted"):
            report, ledger, prices = sample()
            # Turn this into a loss, then hide it without changing frozen picks.
            prices["days"][DAYS[-1]]["3017"] = 90.0
            for source in (ledger, report):
                source["picks"][-1]["signal_close"] = 90.0
            report["picks"][0]["outcomes"][0] = {"trading_days": 3, "status": status}
            with self.subTest(status=status):
                self.assertEqual(audit_cohorts(report, ledger, prices, EFFECTIVE_DAY)["reason"],
                                 "prospective_outcome_status_not_reproducible")

    def test_real_missing_price_remains_an_excluded_observation(self):
        from scripts.update_pick_validation import compile_report
        report, ledger, prices = sample()
        del prices["days"][DAYS[1]]["3017"]
        prices["days"][DAYS[1]]["9999"] = 100.0
        for source in (ledger, report):
            source["picks"] = [p for p in source["picks"] if p["day"] != DAYS[1]]
        ledger["empty_sessions"] = [{"day": DAYS[1], "status": "verified_no_candidates",
                                     "selection_policy": POLICY}]
        report = compile_report(ledger["picks"], prices, "test")
        self.assertEqual(report["picks"][0]["outcomes"][0]["status"], "missing_price")
        self.assertEqual(audit_cohorts(report, ledger, prices, EFFECTIVE_DAY)["status"], "PASS")

    def test_real_corporate_action_stays_excluded_and_cannot_be_completed(self):
        from scripts.update_pick_validation import compile_report
        report, ledger, prices = sample()
        prices["corporate_actions"] = {DAYS[1]: {"3017": "除息"}}
        honest = compile_report(ledger["picks"], prices, "test")
        self.assertEqual(honest["picks"][0]["outcomes"][0]["status"],
                         "corporate_action_unadjusted")
        self.assertEqual(audit_cohorts(honest, ledger, prices, EFFECTIVE_DAY)["status"], "PASS")
        self.assertEqual(audit_cohorts(report, ledger, prices, EFFECTIVE_DAY)["reason"],
                         "prospective_outcome_status_not_reproducible")

    def test_source_inputs_not_mutated(self):
        report, ledger, prices = sample()
        before = copy.deepcopy([report,ledger,prices])
        audit_cohorts(report, ledger, prices, EFFECTIVE_DAY)
        self.assertEqual([report,ledger,prices], before)


if __name__ == "__main__":
    unittest.main()
