"""TPEx historical daily-close response parser (offline, no network).

Accepts only explicit header schemas, never guesses a price column.
Public TPEx historical individual-stock pages expose ROC dates and closing
prices, but response wrappers can vary by endpoint/version.
"""
from datetime import date
from math import isfinite
import re

def parse_tpex_daily_close(payload):
    if not isinstance(payload,dict):
        raise ValueError("TPEx response must be object")
    if payload.get("stat") not in (None,"ok","OK"):
        raise ValueError("TPEx response indicates error")
    fields=payload.get("fields")
    rows=payload.get("aaData",payload.get("data"))
    if not isinstance(fields,list) or not isinstance(rows,list):
        raise ValueError("TPEx response requires explicit fields and data")
    names=[re.sub(r"\s+","",str(v)) for v in fields]
    date_cols=[i for i,name in enumerate(names) if name in ("日期","交易日期")]
    close_cols=[i for i,name in enumerate(names) if name in ("收盤","收盤價")]
    if len(date_cols)!=1 or len(close_cols)!=1:
        raise ValueError("ambiguous TPEx date or close column")
    d_idx,c_idx=date_cols[0],close_cols[0]
    result=[]
    seen=set()
    for row in rows:
        if not isinstance(row,list) or len(row)<=max(d_idx,c_idx):
            raise ValueError("malformed TPEx row")
        raw=str(row[d_idx]).strip()
        match=re.fullmatch(r"(\d{2,3})/(\d{1,2})/(\d{1,2})",raw)
        if not match:
            raise ValueError("expected ROC trade date")
        iso=date(1911+int(match[1]),int(match[2]),int(match[3])).isoformat()
        price=str(row[c_idx]).replace(",","").strip()
        if price in ("--","---",""):
            continue
        try:
            value=float(price)
        except ValueError as exc:
            raise ValueError("invalid TPEx closing price") from exc
        if not isfinite(value) or value<=0 or iso in seen:
            raise ValueError("invalid or duplicate TPEx close")
        seen.add(iso)
        result.append({"date":iso,"close":value})
    if result!=sorted(result,key=lambda x:x["date"]):
        raise ValueError("TPEx dates out of order")
    return result
