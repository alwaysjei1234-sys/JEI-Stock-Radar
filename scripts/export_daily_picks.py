"""Extract auditable JEI picks from the actual remote/system.json feed.

Only the feed's data_date is the signal date, NOT last_checked_at.
Use one snapshot per market date. Do not replace past snapshots with reruns.
"""
import argparse
import json
from datetime import date
from pathlib import Path

FEED_COHORTS = {"attack": "momentum", "monster": "monster", "future_monster": "pre_breakout"}

def extract(feed, limit=10):
    if isinstance(limit,bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be positive integer")
    as_of = date.fromisoformat(feed["data_date"]).isoformat()
    picks = []
    for feed_key, cohort in FEED_COHORTS.items():
        rows = feed.get(feed_key, [])
        if not isinstance(rows, list):
            raise ValueError(f"{feed_key} must be a list")
        seen = set()
        for row in rows:
            if not isinstance(row,dict):
                continue
            code = str(row.get("code", "")).strip()
            if not code or code in seen:
                continue
            seen.add(code)
            pick = {"as_of": as_of, "code": code, "cohort": cohort,
                    "rank": len(seen), "name": str(row.get("name", "")),
                    "source": f"remote/system.json:{feed_key}"}
            if isinstance(row.get("score"), (int, float)) and not isinstance(row["score"], bool) and __import__("math").isfinite(row["score"]):
                pick["signal_score"] = row["score"]
            picks.append(pick)
            if len(seen) >= limit:
                break
    return {"schema_version": 1, "data_date": as_of,
            "snapshot_policy": "one immutable file per trading date",
            "picks": picks}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--feed", type=Path, default=Path("remote/system.json"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--limit", type=int, default=10)
    args = p.parse_args()
    snapshot = extract(json.loads(args.feed.read_text(encoding="utf-8")), args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # x = exclusive create: never silently rewrite a dated pick record.
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Recorded {len(snapshot['picks'])} picks for {snapshot['data_date']}")

if __name__ == "__main__":
    main()
