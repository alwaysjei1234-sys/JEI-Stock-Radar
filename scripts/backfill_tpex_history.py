import json, urllib.parse, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HISTORY=ROOT/"remote/history.json"
PROBES=("5347","5425","6150","6187")

def fetch_json(url, timeout=15):
    req=urllib.request.Request(url,headers={
        "User-Agent":"Mozilla/5.0 JEI-Stock-Radar/3.3",
        "Accept":"application/json"
    })
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8-sig"))

def fetch_finmind_stock(code,start_date,end_date):
    url="https://api.finmindtrade.com/api/v4/data?"+urllib.parse.urlencode({
        "dataset":"TaiwanStockPrice",
        "data_id":code,
        "start_date":start_date,
        "end_date":end_date,
    })
    j=fetch_json(url)
    rows=j.get("data") or []
    out={}
    for row in rows:
        d=str(row.get("date") or "")[:10]
        try:
            close=float(row.get("close"))
        except (TypeError,ValueError):
            continue
        if d and close>0:
            out[d]=close
    if len(out)<5:
        raise RuntimeError(f"FinMind {code} returned only {len(out)} valid rows")
    return out

def main():
    history=json.loads(HISTORY.read_text(encoding="utf-8"))
    dates=sorted(str(x.get("date")) for x in history if isinstance(x,dict) and x.get("date"))
    if not dates:
        raise RuntimeError("history.json has no dates")
    start_date,end_date=dates[0],dates[-1]
    by_date={str(x.get("date")):x for x in history if isinstance(x,dict) and x.get("date")}

    print(f"FinMind TPEx backfill range={start_date}..{end_date}, history_dates={len(dates)}")
    errors=[]
    for code in PROBES:
        try:
            px=fetch_finmind_stock(code,start_date,end_date)
            for d,close in px.items():
                if d in by_date:
                    by_date[d].setdefault("prices",{})[code]=close
            print(code,"rows",len(px),"sample",list(sorted(px.items()))[-3:])
        except Exception as e:
            errors.append(f"{code}: {e}")
            print("ERROR",code,e)

    coverage={code:sum(1 for x in history if (x.get("prices") or {}).get(code) is not None) for code in PROBES}
    print("coverage",coverage)
    if errors:
        print("errors",errors)
    if min(coverage.values())<15:
        raise RuntimeError("TPEx history still insufficient: "+json.dumps(coverage,ensure_ascii=False))

    HISTORY.write_text(json.dumps(history,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("TPEx history backfill complete")

if __name__=="__main__":
    main()
