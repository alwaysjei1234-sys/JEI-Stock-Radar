"""Fetch TWSE listed-stock monthly daily closes with conservative rate limiting.

Uses the TWSE public STOCK_DAY endpoint. Output retains URL, retrieval timestamp,
and parsed prices. HTTP retrieval alone does not verify corporate actions or
guarantee every historical session is present.
"""
import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from scripts.parse_twse_stock_day import parse_twse_stock_day

BASE="https://www.twse.com.tw/exchangeReport/STOCK_DAY"

def fetch_month(code, month, timeout=20):
    code=str(code)
    if not (code.isdigit() and len(code) in (4,5,6)):
        raise ValueError("invalid stock code")
    if len(month)!=6 or not month.isdigit() or not (1<=int(month[4:])<=12):
        raise ValueError("month must be YYYYMM")
    params=urllib.parse.urlencode({"response":"json","date":month+"01","stockNo":code})
    url=BASE+"?"+params
    request=urllib.request.Request(url,headers={"User-Agent":"JEI-Stock-Radar/1.0 (research data validation)","Accept":"application/json"})
    with urllib.request.urlopen(request,timeout=timeout) as response:
        if response.status!=200:
            raise ValueError(f"TWSE HTTP {response.status}")
        raw=response.read(4_000_001)
    if len(raw)>4_000_000:
        raise ValueError("TWSE response unexpectedly large")
    payload=json.loads(raw.decode("utf-8-sig"))
    series=parse_twse_stock_day(payload,code)
    return {"code":code,"market":"TWSE","source":"TWSE STOCK_DAY fetched via HTTPS; corporate actions not adjusted",
            "source_url":url,"retrieved_at":datetime.now(timezone.utc).isoformat(),
            "prices":series}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--stock-code",required=True)
    p.add_argument("--months",nargs="+",required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--pause",type=float,default=4.0)
    args=p.parse_args()
    if args.pause<3:
        p.error("--pause must be at least 3 seconds")
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for index,month in enumerate(args.months):
        output=args.output_dir/(str(args.stock_code)+"-"+month+".json")
        if output.exists():
            print("Skip existing",output)
            continue
        if index:
            time.sleep(args.pause)
        result=fetch_month(args.stock_code,month)
        with output.open("x",encoding="utf-8") as stream:
            json.dump(result,stream,ensure_ascii=False,indent=2)
            stream.write("\n")
        print("Saved",output,len(result["prices"]),"sessions")

if __name__=="__main__":
    main()
