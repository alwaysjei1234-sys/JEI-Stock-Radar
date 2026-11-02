"""Convert append-only JEI feed price snapshots into dated per-symbol series.

These are feed observations, NOT independently verified official closes.
"""
import argparse
import json
import re
from pathlib import Path
from datetime import date
from math import isfinite


def observations(snapshot, day, path):
    """Adapt known archive formats without upgrading diagnostic verification."""
    source = snapshot.get("source", "")
    if isinstance(source, str) and "official close not independently confirmed" in source:
        return snapshot.get("prices")
    official_source = (source == "remote/daily_prices.json: official daily closes" or
                       isinstance(source, str) and re.fullmatch(
                           r"remote/daily_prices\.json preserved in same-day " + day +
                           r" market feed commit [0-9a-f]{7,40}; official daily close", source))
    if (type(snapshot.get("schema")) is not int or snapshot["schema"] != 1 or
            snapshot.get("kind") != "official_daily_close" or not official_source):
        raise ValueError(f"unrecognized price provenance: {path}")
    days = snapshot.get("days")
    if not isinstance(days, dict) or set(days) != {day} or not isinstance(days[day], dict):
        raise ValueError(f"invalid official snapshot dates: {path}")
    prices = days[day]
    count = snapshot.get("coverage_count")
    if type(count) is not int or count != len(prices) or count < 500:
        raise ValueError(f"invalid official snapshot coverage: {path}")
    if any(not isinstance(code, str) or not re.fullmatch(r"[0-9A-Z]{4,8}", code) for code in prices):
        raise ValueError(f"invalid official snapshot symbol: {path}")
    return {code: {"date": day, "close": close} for code, close in prices.items()}

def collect(directory):
    series = {}
    for path in sorted(Path(directory).glob("????-??-??.json")):
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        day = date.fromisoformat(snapshot["data_date"]).isoformat()
        if path.stem != day:
            raise ValueError(f"snapshot date/filename mismatch: {path}")
        prices = observations(snapshot, day, path)
        if not isinstance(snapshot.get("conflict_codes",[]),list):
            raise ValueError(f"invalid conflict list: {path}")
        conflicted=set(snapshot.get("conflict_codes",[]))
        if not isinstance(prices,dict):
            raise ValueError(f"invalid price map: {path}")
        for code, observation in prices.items():
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
