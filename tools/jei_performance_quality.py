"""Read-only quality check; forward observations are not independent OOS trades."""
import argparse
import datetime as dt
import json
from pathlib import Path

from tools.jei_shared_compute import OBSERVATION_HORIZONS

def inspect(report, min_completed=30, min_win_rate=50.0):
    groups = report.get("groups")
    if not isinstance(groups, dict) or not groups:
        return {"status": "BLOCKED", "reason": "missing_groups", "groups": {}}
    results = {}
    for name, periods in groups.items():
        if not isinstance(periods, dict):
            continue
        results[name] = {}
        for horizon in OBSERVATION_HORIZONS:
            data = periods.get(horizon)
            if not isinstance(data, dict):
                continue
            count, win = data.get("completed"), data.get("win_rate_pct")
            net = data.get("avg_estimated_net_pct")
            if type(count) is not int or count < 0:
                state = "INVALID"
            elif count < min_completed or type(win) not in (float, int) or not 0 <= win <= 100:
                state = "INSUFFICIENT_EVIDENCE"
            elif type(net) not in (float, int) or not -100 <= net <= 1000:
                state = "INSUFFICIENT_EVIDENCE"
            elif win < min_win_rate or net <= 0:
                state = "UNDERPERFORMING"
            else:
                state = "OBSERVED_THRESHOLD_MET"
            results[name][horizon] = {
                "state": state, "completed": count, "win_rate_pct": win,
                "avg_estimated_net_pct": data.get("avg_estimated_net_pct")}
    evaluated = [entry for periods in results.values() for horizon, entry in periods.items()
                 if horizon in ("3", "7") and entry["state"] in ("UNDERPERFORMING", "OBSERVED_THRESHOLD_MET")]
    negative = sum(entry["state"] == "UNDERPERFORMING" for entry in evaluated)
    signal = ("REVIEW_ALL_SHORT_HORIZON_SIGNALS" if evaluated and negative == len(evaluated)
              else "REVIEW_WEAK_SIGNALS" if negative else "INSUFFICIENT_OR_NO_NEGATIVE_EVIDENCE")
    return {"status": "REPORTED", "short_horizon_risk": {
                "assessment": signal, "evaluated": len(evaluated), "underperforming": negative,
                "advisory_only": True, "automatic_trade_block": False},
            "source_updated_at": report.get("updated_at"),
            "source_official_day": report.get("latest_official_day"),
            "groups": results, "live_trading_verified": False,
            "independent_oos_verified": False,
            "note": "Forward close-based observations; not verified fills or independent OOS."}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="remote/pick_validation.json")
    parser.add_argument("--out", default="audit-output/pick_quality.json")
    args = parser.parse_args()
    try:
        result = inspect(json.loads(Path(args.input).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as exc:
        result = {"status": "BLOCKED", "reason": str(exc)}
    result["checked_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "REPORTED" else 1

if __name__ == "__main__":
    raise SystemExit(main())
