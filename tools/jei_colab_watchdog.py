"""Fail-safe Colab heartbeat assessment. Never pretends to restart Colab."""
import argparse
import datetime as dt
import json
from pathlib import Path


def assess(report, now=None, max_age_minutes=30):
    now = now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(report, dict):
        return {"status": "UNKNOWN", "reason": "no_accessible_colab_heartbeat",
                "restart_possible": False, "fallback": "github_actions"}
    if report.get("provider") != "google_colab":
        return {"status": "UNKNOWN", "reason": "provider_not_colab",
                "restart_possible": False, "fallback": "github_actions"}
    stamp = report.get("heartbeat_at_utc")
    try:
        last = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if last.tzinfo is None:
            raise ValueError("timezone missing")
    except (AttributeError, TypeError, ValueError):
        return {"status": "UNKNOWN", "reason": "invalid_heartbeat_timestamp",
                "restart_possible": False, "fallback": "github_actions"}
    elapsed = (now - last).total_seconds() / 60
    if elapsed < -5:
        state, reason = "UNKNOWN", "heartbeat_in_future"
    elif elapsed > max_age_minutes:
        state, reason = "STALE", "heartbeat_expired"
    else:
        state, reason = "RECENT_HEARTBEAT", "recent_heartbeat_not_proof_of_runtime"
    return {"status": state, "reason": reason, "minutes_since_heartbeat": round(elapsed, 1),
            "restart_possible": False, "fallback": "github_actions",
            "note": "Recent heartbeat is not a live Colab API check; free Colab cannot be forcibly restarted via this workflow."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--heartbeat", default="audit-input/colab_heartbeat.json")
    parser.add_argument("--output", default="audit-output/colab_watchdog.json")
    parser.add_argument("--max-age-minutes", type=float, default=30)
    args = parser.parse_args()
    try:
        report = json.loads(Path(args.heartbeat).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = None
    result = assess(report, max_age_minutes=args.max_age_minutes)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
