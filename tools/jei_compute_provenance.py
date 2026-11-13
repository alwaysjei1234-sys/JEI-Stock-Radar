"""Record verifiable compute provenance; GitHub Actions is not Google Colab."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path


def make_record(env, quality):
    risk = quality.get("short_horizon_risk", {})
    return {
        "schema": 1,
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "compute_provider": "github_actions",
        "google_colab_runtime_verified": False,
        "google_colab_helpfulness_verified": False,
        "github_run_id": env.get("GITHUB_RUN_ID"),
        "github_run_attempt": env.get("GITHUB_RUN_ATTEMPT"),
        "github_sha": env.get("GITHUB_SHA"),
        "github_workflow": env.get("GITHUB_WORKFLOW"),
        "quality_status": quality.get("status"),
        "quality_source_updated_at": quality.get("source_updated_at"),
        "quality_source_official_day": quality.get("source_official_day"),
        "short_horizon_risk": risk,
        "independent_oos_verified": False,
        "meaningful_new_strategy_improvement_verified": False,
        "note": "This proves a GitHub Actions audit ran, not an active Colab session or profitable OOS trades.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quality", default="audit-output/pick_quality.json")
    parser.add_argument("--out", default="audit-output/compute_provenance.json")
    args = parser.parse_args()
    quality = json.loads(Path(args.quality).read_text(encoding="utf-8"))
    record = make_record(os.environ, quality)
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False))
    return 0 if record["quality_status"] == "REPORTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
