"""Load JEI archived daily signal snapshots into paper-report input.

Snapshots are append-only, keyed by data_date. Repeated signal identities are
rejected. This does NOT manufacture missing historical prices.
"""
import argparse
import json
from pathlib import Path

def load_snapshots(directory):
    picks, dates, identities = [], set(), set()
    for path in sorted(Path(directory).glob("????-??-??.json")):
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        d = snapshot["data_date"]
        if path.stem != d:
            raise ValueError(f"snapshot date differs from filename: {path}")
        if d in dates:
            raise ValueError(f"duplicate snapshot date: {d}")
        dates.add(d)
        for pick in snapshot["picks"]:
            if pick["as_of"] != d:
                raise ValueError(f"pick date differs from snapshot date: {path}")
            identity = (d, str(pick["code"]), pick["cohort"])
            if identity in identities:
                raise ValueError(f"duplicate pick: {identity}")
            identities.add(identity)
            picks.append(pick)
    return picks

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--directory", type=Path, default=Path("data/pick_snapshots"))
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    picks = load_snapshots(args.directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(picks,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Loaded {len(picks)} archived signals.")

if __name__=="__main__":
    main()
