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
from scripts.parse_twse_stock_day import parse_twse_stock_day, parse_twse_stock_day_ohlcv

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
    candles=parse_twse_stock_day_ohlcv(payload,code)
    if [row["date"] for row in candles]!=[row["date"] for row in series]:
        raise ValueError("OHLCV and close-only trading dates disagree")
    return {"code":code,"market":"TWSE","source":"TWSE STOCK_DAY fetched via HTTPS; corporate actions not adjusted",
            "source_url":url,"retrieved_at":datetime.now(timezone.utc).isoformat(),
            "prices":series,"ohlcv":candles,
            "ohlcv_units":{"price":"TWD per share","volume":"shares"},
            "adjusted_for_corporate_actions":False}

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
            try:
                existing=json.loads(output.read_text(encoding="utf-8"))
                if (existing.get("code")==str(args.stock_code)
                    and isinstance(existing.get("ohlcv"),list)
                    and isinstance(existing.get("prices"),list)
                    and existing.get("market")=="TWSE"
                    and existing.get("ohlcv_units",{}).get("volume")=="shares"
                    and existing.get("adjusted_for_corporate_actions") is False
                    and len(existing["ohlcv"])==len(existing["prices"])
                    and all(isinstance(c,dict) and isinstance(p,dict)
                        and c.get("date")==p.get("date") and c.get("close")==p.get("close")
                        and all(isinstance(c.get(k),(int,float)) and c[k]>0 for k in ("open","high","low","close"))
                        and isinstance(c.get("volume"),int) and c["volume"]>=0
                        and c["low"]<=min(c["open"],c["close"])<=max(c["open"],c["close"])<=c["high"]
                        for c,p in zip(existing["ohlcv"],existing["prices"]))):
                    print("Skip validated existing OHLCV",output)
                    continue
            except (ValueError,KeyError,TypeError,AttributeError):
                pass
            raise ValueError(f"Existing file is not validated OHLCV; move or archive before retry: {output}")
        if index:
            time.sleep(args.pause)
        result=fetch_month(args.stock_code,month)
        with output.open("x",encoding="utf-8") as stream:
            json.dump(result,stream,ensure_ascii=False,indent=2)
            stream.write("\n")
        print("Saved",output,len(result["prices"]),"sessions")

if __name__=="__main__":
    main()
