"""Validate Colab report metadata and verify the referenced output bytes."""
import argparse
import datetime as dt
import json
import hashlib
import re
from pathlib import Path

REQUIRED = ("run_id", "started_at_utc", "finished_at_utc", "source_commit", "status", "outputs")

def validate(report, now=None, max_age_hours=3, output_dir=None, expected_commit=None):
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
    commit = report.get("source_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        issues.append("invalid_source_commit")
    if expected_commit is None:
        issues.append("missing_expected_commit")
    elif commit != expected_commit:
        issues.append("source_commit_mismatch")
    if output_dir is None:
        issues.append("missing_output_directory")
    hashes = report.get("output_sha256")
    if not isinstance(hashes, dict):
        issues.append("missing_output_hashes")
    if isinstance(report.get("outputs"), dict):
        for key, filename in report["outputs"].items():
            digest = hashes.get(key) if isinstance(hashes, dict) else None
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                issues.append("invalid_output_hash_" + str(key))
            if not isinstance(filename, str) or Path(filename).name != filename or filename in (".", ".."):
                issues.append("unsafe_output_name_" + str(key))
                continue
            if output_dir is not None:
                path = Path(output_dir) / filename
                if not path.is_file() or path.is_symlink():
                    issues.append("missing_output_file_" + str(key))
                elif isinstance(digest, str):
                    try:
                        actual = hashlib.sha256(path.read_bytes()).hexdigest()
                    except OSError:
                        issues.append("unreadable_output_file_" + str(key))
                    else:
                        if actual != digest:
                            issues.append("output_hash_mismatch_" + str(key))
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
            "note": "Metadata and output integrity checks do not attest to the Colab runtime or strategy performance."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report")
    parser.add_argument("--max-age-hours", type=float, default=3)
    parser.add_argument("--output-dir")
    parser.add_argument("--expected-commit")
    args = parser.parse_args()
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"verified": False, "issues": [str(exc)]}))
        return 2
    result = validate(report, max_age_hours=args.max_age_hours, output_dir=args.output_dir, expected_commit=args.expected_commit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
