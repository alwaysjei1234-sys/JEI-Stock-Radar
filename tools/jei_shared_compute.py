"""One portable, real computation for Colab or GitHub Actions.

Calculates risk-adjusted comparisons from *observed aggregate* pick results.
Never describes these aggregates as independent OOS or executed trades.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

# Trading-day windows produced by the public pick validation report.
OBSERVATION_HORIZONS = ("3", "7", "15", "20", "30", "40", "60")


def observed_rows(name, horizons):
    if not isinstance(horizons, dict):
        return
    for horizon in OBSERVATION_HORIZONS:
        entry = horizons.get(horizon, {})
        if not isinstance(entry, dict):
            continue
        n = entry.get("completed")
        win = entry.get("win_rate_pct")
        net = entry.get("avg_estimated_net_pct")
        if type(n) is not int or n <= 0 or type(win) not in (float, int) or type(net) not in (float, int):
            continue
        yield {"strategy": name, "horizon_days": int(horizon),
               "observed_count": n, "win_rate_pct": win,
               "avg_estimated_net_pct": net,
               "eligible_for_comparison": n >= 30,
               "underperforming": n >= 30 and (net <= 0 or win < 50)}


def compute(source):
    groups = source.get("groups", {})
    if not isinstance(groups, dict) or not groups:
        raise ValueError("missing observed pick groups")
    rows = [row for name, horizons in sorted(groups.items())
            for row in observed_rows(name, horizons)]
    if not rows:
        raise ValueError("no valid completed observations")
    return {"schema": 1, "source_official_day": source.get("latest_official_day"),
            "source_updated_at": source.get("updated_at"),
            "observed_rows": rows,
            "eligible_rows": sum(x["eligible_for_comparison"] for x in rows),
            "independent_oos_trades": 0,
            "independent_oos_verified": False,
            "strategy_improvement_verified": False,
            "note": "Aggregate forward close observations only; no independent OOS or trade fills."}


def execute(source_path, output_dir, provider, source_commit):
    source_path = Path(source_path)
    raw = source_path.read_bytes()
    report = compute(json.loads(raw))
    report["computed_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    report["compute_provider"] = provider
    report["source_commit"] = source_commit
    report["source_sha256"] = hashlib.sha256(raw).hexdigest()
    dest = Path(output_dir)
    dest.mkdir(parents=True, exist_ok=True)
    output = dest / "jei_observed_compute.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="remote/pick_validation.json")
    parser.add_argument("--output-dir", default="audit-output")
    parser.add_argument("--provider", choices=("google_colab", "github_actions"), default="github_actions")
    parser.add_argument("--source-commit", default=os.environ.get("GITHUB_SHA", "unknown"))
    args = parser.parse_args()
    print(execute(args.input, args.output_dir, args.provider, args.source_commit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
