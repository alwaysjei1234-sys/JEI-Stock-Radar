"""Merge TWSE parsed stock-day files into strict price-series JSON.

Never silently overwrite overlapping days or combine incompatible markets.
Inputs are outputs of scripts.parse_twse_stock_day.
"""
import argparse
import json
from pathlib import Path
from scripts.validated_paper_report import _validate_series

def merge(files):
    stocks={}
    for path in files:
        data=json.loads(Path(path).read_text(encoding="utf-8"))
        code=str(data["code"])
        if data.get("market")!="TWSE":
            raise ValueError(f"non-TWSE source: {path}")
        if "TWSE STOCK_DAY" not in str(data.get("source","")):
            raise ValueError(f"unknown source: {path}")
        rows=data["prices"]
        _validate_series(rows,code)
        dest=stocks.setdefault(code,{})
        for row in rows:
            day=row["date"]
            if day in dest:
                raise ValueError(f"duplicate {code} date {day} across input files")
            dest[day]=row["close"]
    return {code:[{"date":day,"close":close} for day,close in sorted(dates.items())]
            for code,dates in sorted(stocks.items())}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--inputs",nargs="+",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    prices=merge(args.inputs)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(prices,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Merged {len(prices)} TWSE stock series; requires benchmark before scoring.")

if __name__=="__main__":
    main()
