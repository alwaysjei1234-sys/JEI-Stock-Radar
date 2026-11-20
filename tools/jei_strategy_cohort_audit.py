"""Cross-check registered prospective cohorts against immutable picks and official closes.

This is an integrity gate, not an independent proof that quotes came from the
exchange, that orders filled, or that the resulting strategy makes money.
"""
import datetime as dt
import math

GROUPS = frozenset(("attack", "next", "monster", "tomorrow_monster", "future_monster"))
EXPECTED_POLICY = "jei-user-radar-gates-v1"
HORIZONS = frozenset((3, 7, 15, 30))


def _day(v):
    if not isinstance(v, str):
        return None
    try:
        day = dt.date.fromisoformat(v)
    except ValueError:
        return None
    return day if day.isoformat() == v else None


def _close(prices, code):
    if not isinstance(prices, dict):
        return None
    value = prices.get(code)
    if type(value) not in (int, float, str):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) and number > 0 else None


def _fail(reason, **facts):
    return {"status": "BLOCKED", "reason": reason, "official_sessions_checked": 0,
            "prospective_frozen_picks": 0, **facts}


def audit_cohorts(report, ledger, prices, effective_day):
    """Fail closed if a missing day or changed frozen pick can bias evaluation."""
    start = _day(effective_day)
    if start is None:
        return _fail("invalid_effective_day")
    if (not isinstance(report, dict) or report.get("schema") != 1
            or report.get("mode") != "forward_official_close_pick_validation"
            or not isinstance(report.get("picks"), list)):
        return _fail("invalid_outcome_report")
    end = _day(report.get("latest_official_day"))
    if end is None:
        return _fail("invalid_report_official_day")
    if (not isinstance(ledger, dict) or ledger.get("schema") != 1
            or ledger.get("mode") != "immutable_asof_pick_archive"
            or not isinstance(ledger.get("picks"), list)):
        return _fail("invalid_immutable_pick_ledger")
    if (not isinstance(prices, dict) or prices.get("schema") != 1
            or prices.get("kind") != "official_daily_close"
            or not isinstance(prices.get("days"), dict)):
        return _fail("invalid_official_close_archive")

    # Identity and static fields must match exactly. Report may recompute only
    # future outcomes; it must not lose, re-rank or reprice the frozen signal.
    fixed = ("day", "group", "code", "rank", "score", "signal_close",
             "origin", "selection_policy", "source_commit", "source_blob",
             "source_committed_at")
    ledger_rows, report_rows = {}, {}
    for source, target in ((ledger["picks"], ledger_rows),
                           (report["picks"], report_rows)):
        for p in source:
            if not isinstance(p, dict) or not isinstance(p.get("id"), str):
                return _fail("invalid_pick_record")
            pid = p["id"]
            if not pid or pid in target:
                return _fail("duplicate_or_empty_frozen_pick_id")
            if pid != f"{p.get('day')}:{p.get('group')}:{p.get('code')}":
                return _fail("malformed_frozen_pick_id", example=pid[:80])
            target[pid] = p
    if ledger_rows.keys() != report_rows.keys():
        return _fail("frozen_pick_ids_differ",
                     ledger_count=len(ledger_rows), report_count=len(report_rows))
    for pid, original in ledger_rows.items():
        recent = report_rows[pid]
        if any(original.get(k) != recent.get(k) for k in fixed):
            return _fail("recomputed_or_repriced_frozen_pick", example=pid[:80])

    # Only verified close slots in the existing public archive are candidates;
    # missing/partial sessions are NOT silently skipped or counted as wins.
    archive_days = {}
    for key, quotes in prices["days"].items():
        day = _day(key)
        if day is not None and isinstance(quotes, dict):
            valid = sum(_close(quotes, code) is not None for code in quotes)
            if valid >= 500:
                archive_days[day] = quotes
    if not archive_days:
        return _fail("no_valid_official_close_days")
    last_close = max(archive_days)
    if last_close != end:
        return _fail("outcome_report_and_official_archive_date_disagree",
                     report_day=end.isoformat(), archive_day=last_close.isoformat())
    if end < start:
        return {"status": "PASS_PRE_EFFECTIVE_DAY", "reason": "no_prospective_sessions_yet",
                "official_sessions_checked": 0, "prospective_frozen_picks": 0,
                "ledger_matches_outcomes": True, "selection_policy": EXPECTED_POLICY}

    from scripts.market_sessions import next_expected_session
    from scripts.update_pick_validation import net_percent, compile_report
    sessions = sorted(day for day in archive_days if start <= day <= end)
    expected = start
    for actual in sessions:
        if actual != expected:
            return _fail("missing_or_unexpected_official_session",
                         expected=expected.isoformat(), actual=actual.isoformat())
        next_str = next_expected_session(actual.isoformat())
        next_day = _day(next_str)
        if next_day is None or next_day <= actual:
            return _fail("invalid_next_expected_session")
        expected = next_day
    if not sessions or sessions[-1] != end:
        return _fail("missing_official_session_at_end", expected=expected.isoformat())

    frozen_by_day = {day: [] for day in sessions}
    for p in ledger_rows.values():
        day = _day(p.get("day"))
        if day is None:
            return _fail("invalid_frozen_pick_date")
        if day < start or day > end:
            continue
        if day not in frozen_by_day:
            return _fail("frozen_pick_for_non_official_session")
        if (p.get("group") not in GROUPS
                or type(p.get("rank")) is not int or not 1 <= p["rank"] <= 5
                or type(p.get("score")) not in (int, float)
                or not math.isfinite(p["score"])
                or p.get("selection_policy") != EXPECTED_POLICY):
            return _fail("invalid_or_changed_prospective_selection_policy",
                         example=p.get("id", "")[:80])
        base = _close(archive_days[day], p.get("code"))
        quoted = p.get("signal_close")
        if (base is None or type(quoted) not in (int, float)
                or not math.isfinite(quoted) or quoted <= 0
                or abs(base/quoted-1) > .005):
            return _fail("signal_close_differs_from_official_archive",
                         example=p["id"][:80])
        frozen_by_day[day].append(p)

    empty_sessions = ledger.get("empty_sessions", [])
    if not isinstance(empty_sessions, list):
        return _fail("invalid_empty_sessions")
    empty_days = set()
    for row in empty_sessions:
        if not isinstance(row, dict) or not isinstance(row.get("day"), str):
            return _fail("invalid_empty_session_record")
        day = _day(row["day"])
        if day is None:
            return _fail("invalid_empty_session_day")
        if day < start or day > end:
            continue
        if (day not in frozen_by_day or day in empty_days
                or row.get("status") != "verified_no_candidates"
                or row.get("selection_policy") != EXPECTED_POLICY):
            return _fail("invalid_empty_session_attestation")
        empty_days.add(day)
    for day in sessions:
        if bool(frozen_by_day[day]) == (day in empty_days):
            return _fail("missing_or_conflicting_sealed_daily_cohort",
                         trading_day=day.isoformat())

    # A completed outcome is cross-checked against its exact horizon close
    # in the *official* dated archive; report's return cannot be cherry-picked.
    # Recompute status from sealed prices, including genuine missing closes and
    # corporate actions. Checking only "complete" allows a mature losing
    # observation to disappear from the denominator by changing its status.
    prospective_rows = [p for p in ledger_rows.values()
                        if start <= _day(p["day"]) <= end]
    recomputed = compile_report(prospective_rows, prices, "integrity-check")
    expected_statuses = {(p["id"], o["trading_days"]): o["status"]
                         for p in recomputed["picks"] for o in p["outcomes"]}
    full_archive_days = sorted(archive_days)
    positions = {day: index for index, day in enumerate(full_archive_days)}
    for p in report_rows.values():
        signal_day = _day(p["day"])
        if signal_day is None or not start <= signal_day <= end:
            continue
        seen = set()
        outcomes = p.get("outcomes")
        if not isinstance(outcomes, list):
            return _fail("missing_prospective_outcomes")
        for o in outcomes:
            if not isinstance(o, dict) or type(o.get("trading_days")) is not int:
                return _fail("invalid_prospective_outcome")
            horizon = o["trading_days"]
            if horizon in seen:
                return _fail("duplicate_prospective_horizon")
            seen.add(horizon)
            if horizon not in HORIZONS:
                continue
            expected_status = expected_statuses.get((p["id"], horizon))
            if o.get("status") != "complete":
                if o.get("status") != expected_status:
                    return _fail("prospective_outcome_status_not_reproducible",
                                 example=p["id"][:80], horizon=horizon)
                continue
            if expected_status not in ("complete", "pending"):
                return _fail("prospective_outcome_status_not_reproducible",
                             example=p["id"][:80], horizon=horizon)
            idx = positions[signal_day] + horizon
            if idx >= len(full_archive_days):
                return _fail("future_outcome_claimed_complete", example=p["id"][:80])
            target_day = full_archive_days[idx]
            end_close = _close(archive_days[target_day], p["code"])
            observed_end_close = o.get("end_close")
            result_net = o.get("estimated_net_return_pct")
            if (o.get("end_day") != target_day.isoformat() or end_close is None
                    or type(observed_end_close) not in (float, int)
                    or type(result_net) not in (float, int)
                    or not math.isfinite(observed_end_close) or observed_end_close <= 0
                    or not math.isfinite(result_net)
                    or abs(end_close/observed_end_close - 1) > .0001
                    or o.get("observed_closes") != horizon
                    or o.get("expected_closes") != horizon
                    or abs(net_percent(p["signal_close"], end_close)-result_net) > .02):
                return _fail("prospective_outcome_not_reproducible_from_closes",
                             example=p["id"][:80], horizon=horizon)
        if not HORIZONS.issubset(seen):
            return _fail("missing_expected_prospective_horizon", example=p["id"][:80])

    return {"status": "PASS", "reason": "all_official_days_sealed_and_outcomes_reproducible",
            "official_sessions_checked": len(sessions),
            "prospective_frozen_picks": sum(len(x) for x in frozen_by_day.values()),
            "legitimate_empty_sessions": len(empty_days),
            "ledger_matches_outcomes": True, "selection_policy": EXPECTED_POLICY}
