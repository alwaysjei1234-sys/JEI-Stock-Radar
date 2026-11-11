"""Extract auditable JEI picks from the actual remote/system.json feed.

Only the feed's data_date is the signal date, NOT last_checked_at.
Use one snapshot per market date. Do not replace past snapshots with reruns.
"""
import argparse
import json
import subprocess
from datetime import date, datetime, time
from pathlib import Path

from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")
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
    captured_at = feed.get("updated_at")
    return {"schema_version": 1, "data_date": as_of,
            "captured_at": captured_at,
            "snapshot_policy": "one immutable file per trading date",
            "picks": picks}

def first_close_snapshot(day, archive, sources, now, limit):
    """Use the earliest verified first-parent publication available as of now."""
    from scripts.update_pick_validation import close_verified

    for source in sources:
        feed = source["feed"]
        if not close_verified(feed, archive, day):
            continue
        committed = datetime.fromisoformat(source["committed_at"]).astimezone(TZ)
        published = datetime.strptime(feed["updated_at"], "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        if committed.date().isoformat() != day or not published <= committed <= now:
            continue
        return {
            **extract(feed, limit),
            "source_commit": source["sha"],
            "source_blob": source["blob"],
            "source_committed_at": source["committed_at"],
        }
    raise ValueError(f"No contemporaneous verified close published on main for {day}")


def main():
    p = argparse.ArgumentParser()
    source = p.add_mutually_exclusive_group()
    source.add_argument("--feed", type=Path)
    source.add_argument("--mainline-day", type=date.fromisoformat)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--limit", type=int, default=10)
    args = p.parse_args()
    if args.mainline_day:
        from scripts.recover_pick_history import git_snapshots

        day = args.mainline_day.isoformat()
        archive = json.loads(Path("remote/daily_prices.json").read_text(encoding="utf-8"))
        midnight = datetime.combine(args.mainline_day, time.min, TZ)
        snapshot = first_close_snapshot(day, archive, git_snapshots("HEAD", midnight.isoformat()),
                                        datetime.now(TZ), args.limit)
        original = json.loads(subprocess.check_output(
            ["git", "show", snapshot["source_commit"] + ":remote/daily_prices.json"]))
        if original.get("days", {}).get(day) != archive["days"][day]:
            raise ValueError(f"Official prices have changed since the first publication for {day}")
    else:
        feed = args.feed or Path("remote/system.json")
        snapshot = extract(json.loads(feed.read_text(encoding="utf-8")), args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # x = exclusive create: never silently rewrite a dated pick record.
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Recorded {len(snapshot['picks'])} picks for {snapshot['data_date']}")

if __name__ == "__main__":
    main()
