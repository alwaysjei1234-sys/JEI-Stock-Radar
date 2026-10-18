"""Convert append-only JEI feed price snapshots into dated per-symbol series.

These are feed observations, NOT independently verified official closes.
"""
import argparse
import json
from pathlib import Path

def collect(directory):
    series = {}
    for path in sorted(Path(directory).glob("????-??-??.json")):
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        day = snapshot["data_date"]
        if path.stem != day:
            raise ValueError(f"snapshot date/filename mismatch: {path}")
        if "official close not independently confirmed" not in snapshot.get("source", ""):
            raise ValueError(f"unrecognized price provenance: {path}")
        for code, observation in snapshot["prices"].items():
            if observation["date"] != day:
                raise ValueError(f"price date mismatch: {path} {code}")
            series.setdefault(code, []).append({"date": day, "close": observation["close"]})
    return series

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--directory",type=Path,default=Path("data/feed_closes"))
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    result=collect(args.directory)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Collected feed observations for {len(result)} symbols; NOT verified official closes.")

if __name__=="__main__":
    main()
