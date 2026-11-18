"""Append-only, pre-registered comparison of public radar filters.

This is a *prospective close-observation* registry, NOT independent OOS
filled trades, broker execution, automated strategy tuning or a win-rate claim.
The fixed effective date prevents retrofitting today's already-seen losers.
"""
import argparse
import datetime as dt
import json
import math
from pathlib import Path

from tools.jei_strategy_cohort_audit import audit_cohorts

EFFECTIVE_DAY = "2026-11-19"
GROUPS = ("attack", "next", "monster", "tomorrow_monster", "future_monster")
HORIZONS = (3, 7, 15, 30)
MIN_PROSPECTIVE_COMPLETED = 30
ALLOWED_ORIGINS = {"scheduled_close", "recovered_mainline_close_observation"}
# Frozen hypotheses, evaluated on the SAME archived candidates, with no
# retrospective optimization or automatic signal changes.
POLICIES = (
    ("baseline_top5", lambda pick: 1 <= pick["rank"] <= 5),
    ("rank_top1", lambda pick: pick["rank"] == 1),
    ("rank_top3", lambda pick: 1 <= pick["rank"] <= 3),
    ("score_at_least_85", lambda pick: pick["score"] >= 85),
)


def _date(v):
    if type(v) is not str or len(v) != 10:
        return None
    try:
        day = dt.date.fromisoformat(v)
    except ValueError:
        return None
    return day if day.isoformat() == v else None


def _good_pick(p):
    if not isinstance(p, dict):
        return False
    if (p.get("origin") not in ALLOWED_ORIGINS
            or not isinstance(p.get("code"), str)
            or not isinstance(p.get("group"), str)
            or p["group"] not in GROUPS
            or type(p.get("rank")) is not int or not 1 <= p["rank"] <= 5
            or type(p.get("score")) not in (int, float)
            or not math.isfinite(p["score"]) or not 0 <= p["score"] <= 100):
        return False
    signal_day = _date(p.get("day"))
    if signal_day is None:
        return False
    # Recovered mainline signals must have traceable, contemporaneous commits.
    if p["origin"] == "recovered_mainline_close_observation":
        committed = p.get("source_committed_at")
        if type(committed) is not str:
            return False
        try:
            stamp = dt.datetime.fromisoformat(committed.replace("Z", "+00:00"))
        except ValueError:
            return False
        if stamp.tzinfo is None:
            return False
        local = stamp.astimezone(dt.timezone(dt.timedelta(hours=8)))
        if local.date() != signal_day:
            return False
    return True


def _observation(p, horizon, reference_day):
    items = p.get("outcomes")
    if not isinstance(items, list):
        return None
    for x in items:
        if (not isinstance(x, dict) or type(x.get("trading_days")) is not int
                or x["trading_days"] != horizon or x.get("status") != "complete"):
            continue
        end = _date(x.get("end_day"))
        start = _date(p.get("day"))
        if end is None or start is None or not start < end <= reference_day:
            return None
        value = x.get("estimated_net_return_pct")
        if type(value) not in (int, float) or not math.isfinite(value) or not -100 <= value <= 1000:
            return None
        return float(value)
    return None


def _summarize(picks, policy, horizon, reference_day):
    selected = [p for p in picks if policy(p)]
    finished = [net for p in selected
                if (net := _observation(p, horizon, reference_day)) is not None]
    result = {"selected_signals": len(selected), "completed": len(finished),
              "pending_or_invalid": len(selected)-len(finished),
              "win_rate_pct": round(100*sum(v > 0 for v in finished)/len(finished), 2) if finished else None,
              "avg_estimated_net_pct": round(sum(finished)/len(finished), 3) if finished else None,
              "min_completed": MIN_PROSPECTIVE_COMPLETED}
    result["evidence"] = ("OBSERVED_SAMPLE_ONLY" if len(finished) >= MIN_PROSPECTIVE_COMPLETED
                          else "INSUFFICIENT_OR_PENDING")
    return result


def compare(report):
    baseline = {"schema": 1,
                "kind": "pre_registered_forward_close_only_strategy_comparison",
                "effective_day": EFFECTIVE_DAY,
                "source_mode": "forward_official_close_pick_validation",
                "source_official_day": None,
                "status": "INVALID_SOURCE",
                "policies": [name for name, _ in POLICIES],
                "horizons_trading_days": list(HORIZONS),
                "independent_oos_verified": False,
                "real_execution_verified": False,
                "automatic_promotions": False,
                "uses_future_to_select_policy": False,
                "notes": [
                    "固定規則於2026-11-18建立，2026-11-19起的新訊號才納入前瞻研究。",
                    "訊號日收盤假設進場，非可成交回測；僅用已封存觀察資料。",
                    "跨組同股與重疊持有期不等於獨立交易；未考慮滑價、最低手續費及所有公司行動。",
                    "未達30筆成熟樣本的分組不得宣稱比較結果可靠，也不得自動修改正式選股策略。",
                ]}
    if (not isinstance(report, dict) or report.get("schema") != 1
            or report.get("mode") != baseline["source_mode"]):
        return baseline
    ref = _date(report.get("latest_official_day"))
    if ref is None:
        return baseline
    baseline["source_official_day"] = ref.isoformat()
    if not isinstance(report.get("picks"), list):
        return baseline
    picks = report["picks"]
    # Duplicates violate frozen-signal assumptions. A corrupted archive must
    # not be silently de-duplicated into a superficially stronger result.
    identifiers = [p.get("id") for p in picks if isinstance(p, dict)]
    if any(type(x) is not str or not x for x in identifiers) or len(identifiers) != len(picks) or len(set(identifiers)) != len(identifiers):
        return {**baseline, "status": "INVALID_DUPLICATE_OR_UNIDENTIFIED_SIGNALS"}
    eligible = [p for p in picks if _good_pick(p) and _date(p["day"]) <= ref]
    past = [p for p in eligible if p["day"] < EFFECTIVE_DAY]
    prospect = [p for p in eligible if p["day"] >= EFFECTIVE_DAY]
    result = {**baseline, "status": "WAITING_FOR_MATURE_PROSPECTIVE_SIGNALS",
              "historic_observation_only": {"signals": len(past)},
              "prospective": {}}
    for group in GROUPS:
        values = [p for p in prospect if p["group"] == group]
        by_policy = {}
        for name, predicate in POLICIES:
            by_policy[name] = {str(h): _summarize(values, predicate, h, ref) for h in HORIZONS}
        result["prospective"][group] = by_policy
    mature = sum(result["prospective"][group][name][str(h)]["completed"] >= MIN_PROSPECTIVE_COMPLETED
                 for group in GROUPS for name, _ in POLICIES for h in HORIZONS)
    result["mature_windows"] = mature
    result["total_windows"] = len(GROUPS)*len(POLICIES)*len(HORIZONS)
    result["prospective_signal_count"] = len(prospect)
    if mature:
        result["status"] = "PROSPECTIVE_OBSERVATIONS_EXIST_NOT_VALIDATED_TRADES"
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="remote/pick_validation.json")
    p.add_argument("--out", default="audit-output/strategy_evolution.json")
    p.add_argument("--ledger", default="remote/pick_history.json")
    p.add_argument("--prices", default="remote/daily_prices.json")
    a = p.parse_args()
    try:
        report = json.loads(Path(a.input).read_text(encoding="utf-8"))
        ledger = json.loads(Path(a.ledger).read_text(encoding="utf-8"))
        archive = json.loads(Path(a.prices).read_text(encoding="utf-8"))
    except (ValueError, OSError):
        report, ledger, archive = None, None, None
    result = compare(report)
    integrity = audit_cohorts(report, ledger, archive, EFFECTIVE_DAY)
    result["cohort_integrity"] = integrity
    # Zero result may be valid before 11/19. Unverified or missing days are not.
    if integrity["status"] not in ("PASS", "PASS_PRE_EFFECTIVE_DAY"):
        result["status"] = "BLOCKED_COHORT_INTEGRITY"
    path = Path(a.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({key: result.get(key) for key in (
        "status", "source_official_day", "effective_day", "prospective_signal_count",
        "mature_windows", "total_windows")}, ensure_ascii=False))
    print(json.dumps({"cohort_integrity": integrity}, ensure_ascii=False))
    return 0 if (result["status"] not in ("INVALID_SOURCE", "BLOCKED_COHORT_INTEGRITY")
                 and not result["status"].startswith("INVALID_")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
