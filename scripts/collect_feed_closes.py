"""Convert append-only JEI feed price snapshots into dated per-symbol series.

These are feed observations, NOT independently verified official closes.
"""
import argparse
import json
from pathlib import Path
from datetime import date
from math import isfinite

def collect(directory):
    series = {}
    for path in sorted(Path(directory).glob("????-??-??.json")):
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        day = date.fromisoformat(snapshot["data_date"]).isoformat()
        if path.stem != day:
            raise ValueError(f"snapshot date/filename mismatch: {path}")
        if "official close not independently confirmed" not in snapshot.get("source", ""):
            raise ValueError(f"unrecognized price provenance: {path}")
        if not isinstance(snapshot.get("conflict_codes",[]),list):
            raise ValueError(f"invalid conflict list: {path}")
        conflicted=set(snapshot.get("conflict_codes",[]))
        if not isinstance(snapshot.get("prices"),dict):
            raise ValueError(f"invalid price map: {path}")
        for code, observation in snapshot["prices"].items():
            if code in conflicted:
                raise ValueError(f"conflicted symbol was included in price map: {path} {code}")
            if observation["date"] != day:
                raise ValueError(f"price date mismatch: {path} {code}")
            close=observation["close"]
            if isinstance(close,bool) or not isinstance(close,(int,float)) or not isfinite(close) or close<=0:
                raise ValueError(f"invalid observed close: {path} {code}")
            series.setdefault(code, []).append({"date": day, "close": close})
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
