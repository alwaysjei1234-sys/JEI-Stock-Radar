"""Validate signed-by-evidence (not cryptographically signed) Colab run reports."""
import argparse
import datetime as dt
import json
from pathlib import Path

REQUIRED = ("run_id", "started_at_utc", "finished_at_utc", "source_commit", "status", "outputs")

def validate(report, now=None, max_age_hours=3):
    issues = []
    if not isinstance(report, dict):
        return {"verified": False, "issues": ["invalid_report"]}
    for key in REQUIRED:
        if not report.get(key):
            issues.append("missing_" + key)
    if report.get("provider") != "google_colab":
        issues.append("provider_mismatch")
    if report.get("status") != "completed":
        issues.append("not_completed")
    if not isinstance(report.get("outputs"), dict) or not report.get("outputs"):
        issues.append("missing_outputs")
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        start = dt.datetime.fromisoformat(report["started_at_utc"].replace("Z", "+00:00"))
        end = dt.datetime.fromisoformat(report["finished_at_utc"].replace("Z", "+00:00"))
        if start.tzinfo is None or end.tzinfo is None or end < start:
            issues.append("invalid_run_times")
        elif end > now + dt.timedelta(minutes=5) or now - end > dt.timedelta(hours=max_age_hours):
            issues.append("stale_or_future_run")
    except (KeyError, ValueError, TypeError, AttributeError):
        issues.append("invalid_run_times")
    return {"verified": not issues, "issues": issues,
            "run_id": report.get("run_id"), "source_commit": report.get("source_commit"),
            "note": "Report-format verification only; not proof of authentic Colab runtime or improved strategy."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report")
    parser.add_argument("--max-age-hours", type=float, default=3)
    args = parser.parse_args()
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"verified": False, "issues": [str(exc)]}))
        return 2
    result = validate(report, max_age_hours=args.max_age_hours)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
