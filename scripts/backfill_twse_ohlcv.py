"""Stage bounded official TWSE OHLCV for the current pattern watchlist.

Never fabricates candles. Missing/failed months remain absent, and the daily
feed's strict close reconciliation decides whether a chart may be published.
"""
import argparse
import json
import time
from datetime import date
from pathlib import Path
from scripts.fetch_twse_history import fetch_month


def target_months(asof):
    year, month=asof.year,asof.month
    months=[]
    for offset in (2,1,0):
        total=year*12+(month-1)-offset
        months.append(f"{total//12:04d}{total%12+1:02d}")
    return months


def run(system_path, output_dir, max_codes=8, pause=4):
    system=json.loads(Path(system_path).read_text(encoding="utf-8"))
    patterns=system.get("patterns",{})
    if patterns.get("status")!="ready":
        print("Pattern feed not ready; no downloads")
        return 0
    asof=date.fromisoformat(patterns["data_date"])
    codes=[]
    for rows in patterns.get("signals",{}).values():
        for row in rows:
            code=str(row.get("code",""))
            if len(code)==4 and code.isdigit() and code not in codes:
                codes.append(code)
    output_dir=Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    fetched=0
    for code in codes[:max_codes]:
        for month in target_months(asof):
            path=output_dir/f"{code}-{month}.json"
            if path.exists():
                print("Existing (validated during feed merge):",path)
                continue
            if fetched:time.sleep(pause)
            try:
                result=fetch_month(code,month)
                with path.open("x",encoding="utf-8") as stream:
                    json.dump(result,stream,ensure_ascii=False,separators=(",",":"))
                fetched+=1
                print("Saved",path)
            except Exception as exc:
                print("TWSE month unavailable",code,month,type(exc).__name__,str(exc)[:160])
    return fetched


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--system",type=Path,default=Path("remote/system.json"))
    parser.add_argument("--output-dir",type=Path,default=Path("data/twse_ohlcv"))
    parser.add_argument("--max-codes",type=int,default=8)
    parser.add_argument("--pause",type=float,default=4)
    args=parser.parse_args()
    if not 1<=args.max_codes<=12 or args.pause<3:
        parser.error("max-codes must be 1..12 and pause >= 3 seconds")
    main_count=run(args.system,args.output_dir,args.max_codes,args.pause)
    print("Fetched",main_count,"official monthly files")

if __name__=="__main__":main()
