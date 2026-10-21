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
    # Prefer symbols with the fewest already verified month files. A fixed
    # trading-date rotation can repeatedly revisit the same eight names during
    # a holiday or stale close, leaving the remaining watchlist uncovered.
    # Rotate ties deterministically so coverage improves on every scheduled run.
    if codes:
        start=asof.toordinal()%len(codes)
        rotated=codes[start:]+codes[:start]
        months=target_months(asof)
        codes=sorted(rotated,key=lambda code:sum(
            (output_dir/f"{code}-{month}.json").exists() for month in months))[:max_codes]
    print(json.dumps({"status":"backfill_plan","data_date":asof.isoformat(),
                      "watchlist_codes":len(set(str(row.get("code",""))
                          for rows in patterns.get("signals",{}).values() for row in rows)),
                      "selected_codes":codes,"months":target_months(asof)},
                     ensure_ascii=False))
    for code in codes:
        for month in target_months(asof):
            path=output_dir/f"{code}-{month}.json"
            if path.exists():
                try:
                    old=json.loads(path.read_text(encoding="utf-8"))
                    good=(old.get("code")==code and old.get("market")=="TWSE"
                          and old.get("adjusted_for_corporate_actions") is False
                          and old.get("ohlcv_units",{}).get("volume")=="shares"
                          and isinstance(old.get("ohlcv"),list) and len(old["ohlcv"])>0)
                    if good:
                        print("Existing official OHLCV file:",path)
                        continue
                except (OSError,ValueError,AttributeError):
                    pass
                print("Existing invalid file; preserving for manual review:",path)
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
