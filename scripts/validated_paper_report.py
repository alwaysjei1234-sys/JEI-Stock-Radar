"""Strict, read-only input validation for JEI official-close price series.

Input format:
 {"source":"TWSE/TPEX verified daily close","prices":{"2330":[{"date":"2026-10-16","close":100}]},"benchmark":[{"date":"2026-10-16","close":27000}]}

The source field is an operator declaration, not cryptographic verification.
Do not label the resulting return as officially audited without independent
source evidence and price-adjustment checks.
"""
import argparse
import json
from datetime import date
from math import isfinite
from pathlib import Path

def _validate_series(series, label):
    if not isinstance(series,list):
        raise ValueError(f"{label}: expected list")
    prev=None
    for row in series:
        d=date.fromisoformat(row["date"])
        p=row["close"]
        if prev is not None and d<=prev:
            raise ValueError(f"{label}: dates must be unique and increasing")
        if isinstance(p,bool) or not isinstance(p,(int,float)) or not isfinite(p) or p<=0:
            raise ValueError(f"{label}: close must be finite positive number")
        prev=d

def validate(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get("prices"),dict):
        raise ValueError("prices mapping required")
    if not isinstance(payload.get("source"),str) or not payload["source"].strip():
        raise ValueError("explicit source declaration required")
    if "benchmark" not in payload:
        raise ValueError("benchmark trading calendar is mandatory")
    _validate_series(payload["benchmark"],"benchmark")
    if not payload["benchmark"]:
        raise ValueError("benchmark cannot be empty")
    for code,series in payload["prices"].items():
        if not isinstance(code,str) or not code:
            raise ValueError("invalid stock code")
        _validate_series(series,code)
    return {"prices":payload["prices"],"benchmark":payload["benchmark"],
            "source":payload["source"]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--picks",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    from scripts.paper_report import build_report
    source=validate(json.loads(args.input.read_text(encoding="utf-8")))
    picks=json.loads(args.picks.read_text(encoding="utf-8"))
    result=build_report(picks,source["prices"],source["benchmark"])
    result["data_quality"]={"declared_source":source["source"],
                            "verified_by_system":False,
                            "benchmark_calendar_present":True,
                            "note":"Source label alone does not independently verify prices."}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
