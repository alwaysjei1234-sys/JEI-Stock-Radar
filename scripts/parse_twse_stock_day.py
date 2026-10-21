"""Parse TWSE STOCK_DAY monthly official daily-close responses, offline.

TWSE endpoint (listed securities):
https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=YYYYMM01&stockNo=2330

Never claim an API response was verified merely because a file matches its shape.
TWSE listed stocks only; OTC securities require separate TPEx ingestion.
"""
import argparse
import json
import re
from datetime import date
from math import isfinite
from pathlib import Path

def parse_twse_stock_day(payload, expected_code=None):
    if not isinstance(payload, dict) or payload.get("stat") != "OK":
        raise ValueError("TWSE response is not OK")
    fields=payload.get("fields")
    rows=payload.get("data")
    if not isinstance(fields,list) or not isinstance(rows,list):
        raise ValueError("TWSE fields/data must be lists")
    normalized=[str(f).replace(" ","").replace("\u3000","") for f in fields]
    matches=[i for i,f in enumerate(normalized) if f in ("收盤價","收盤")]
    if len(matches)!=1:
        raise ValueError("unique closing-price column required")
    close_idx=matches[0]
    date_matches=[i for i,f in enumerate(normalized) if f=="日期"]
    if len(date_matches)!=1:
        raise ValueError("unique date column required")
    date_idx=date_matches[0]
    if expected_code is not None:
        title=str(payload.get("title",""))
        # Do not accept a payload for another stock without confirming title.
        if not re.search(r"(?<!\d)"+re.escape(str(expected_code))+r"(?!\d)",title):
            raise ValueError("TWSE title does not match requested stock code")
    result=[]
    seen=set()
    for row in rows:
        if not isinstance(row,list) or len(row)<=max(date_idx,close_idx):
            raise ValueError("malformed TWSE row")
        raw_date=str(row[date_idx]).strip()
        m=re.fullmatch(r"(\d{2,3})/(\d{1,2})/(\d{1,2})",raw_date)
        if not m:
            raise ValueError("invalid ROC date")
        day=date(int(m.group(1))+1911,int(m.group(2)),int(m.group(3))).isoformat()
        raw_close=str(row[close_idx]).replace(",","").strip()
        # '--' represents suspended/no trade; never forward-fill.
        if raw_close in ("--","---",""):
            continue
        try:
            close=float(raw_close)
        except ValueError as exc:
            raise ValueError("invalid close price") from exc
        if not isfinite(close) or close<=0:
            raise ValueError("close must be finite positive")
        if day in seen:
            raise ValueError("duplicate TWSE trade date")
        seen.add(day)
        result.append({"date":day,"close":close})
    if result!=sorted(result,key=lambda r:r["date"]):
        raise ValueError("TWSE dates must be ascending")
    return result

def parse_twse_stock_day_ohlcv(payload, expected_code=None):
    """Strict OHLCV parsing; fail closed if any required TWSE column is absent.

    Volume is TWSE 成交股數 (shares), not lots. Untraded rows are omitted.
    This is raw, unadjusted exchange data, not adjusted candles.
    """
    closes=parse_twse_stock_day(payload, expected_code)
    fields=payload["fields"]
    names=[str(x).replace(" ","").replace("\\u3000","") for x in fields]
    columns={"open":"開盤價","high":"最高價","low":"最低價","close":"收盤價","volume":"成交股數"}
    indexes={}
    for key,header in columns.items():
        matches=[i for i,name in enumerate(names) if name in (("成交股數","交易股數") if key=="volume" else (header,))]
        if len(matches)!=1:
            raise ValueError("unique TWSE OHLCV column required: "+header)
        indexes[key]=matches[0]
    date_idx=names.index("日期")
    valid_dates={x["date"]:x["close"] for x in closes}
    result=[]
    for row in payload["data"]:
        raw_date=str(row[date_idx]).strip()
        match=re.fullmatch(r"(\d{2,3})/(\d{1,2})/(\d{1,2})",raw_date)
        day=date(1911+int(match[1]),int(match[2]),int(match[3])).isoformat()
        if day not in valid_dates:
            continue
        values={}
        for key,index in indexes.items():
            raw=str(row[index]).replace(",","").strip()
            try:
                value=float(raw)
            except ValueError as exc:
                raise ValueError("invalid TWSE OHLCV "+key) from exc
            if not isfinite(value) or value<0 or (key!="volume" and value<=0):
                raise ValueError("invalid TWSE OHLCV "+key)
            values[key]=int(value) if key=="volume" and value.is_integer() else value
        if not isinstance(values["volume"],int):
            raise ValueError("volume must be an integer share count")
        if not (values["low"]<=values["open"]<=values["high"] and values["low"]<=values["close"]<=values["high"]):
            raise ValueError("TWSE OHLC range inconsistent")
        if values["close"]!=valid_dates[day]:
            raise ValueError("TWSE close mismatch")
        result.append({"date":day,**values})
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--stock-code",required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    raw=json.loads(args.input.read_text(encoding="utf-8"))
    series=parse_twse_stock_day(raw,args.stock_code)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({"code":args.stock_code,"market":"TWSE",
      "source":"TWSE STOCK_DAY supplied response; authenticity not independently checked",
      "prices":series},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Parsed {len(series)} daily closes for {args.stock_code}")

if __name__=="__main__":
    main()
