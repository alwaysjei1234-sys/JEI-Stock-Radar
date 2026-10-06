import json, re, html as htmlmod, time, urllib.parse, urllib.request
from pathlib import Path
from datetime import date

ROOT=Path(__file__).resolve().parents[1]
HISTORY=ROOT/"remote/history.json"
PROBES=("5347","5425","6150","6187")

def clean_cell(s):
    s=re.sub(r"<br\s*/?>"," ",s,flags=re.I)
    s=re.sub(r"<[^>]+>","",s)
    return htmlmod.unescape(s).replace("\xa0"," ").strip()

def num(s):
    s=str(s).replace(",","").replace("+","").strip()
    if s in ("","--","---","除權","除息","除權息"): return None
    try: return float(s)
    except: return None

def fetch_day(iso):
    y,m,d=map(int,iso.split("-"))
    roc=f"{y-1911}/{m:02d}/{d:02d}"
    url="https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?"+urllib.parse.urlencode({
        "l":"zh-tw","o":"htm","d":roc,"s":"0,asc,0"
    })
    req=urllib.request.Request(url,headers={
        "User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept":"text/html,application/xhtml+xml"
    })
    with urllib.request.urlopen(req,timeout=12) as r:
        body=r.read().decode("utf-8","replace")
    prices={}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>",body,re.I|re.S):
        cells=re.findall(r"<td[^>]*>(.*?)</td>",tr,re.I|re.S)
        if len(cells)<3: continue
        code=clean_cell(cells[0])
        close=num(clean_cell(cells[2]))
        if re.fullmatch(r"[0-9A-Z]{4,8}",code) and close is not None:
            prices[code]=close
    if len(prices)<100:
        raise RuntimeError(f"{iso}: parsed only {len(prices)} TPEx rows")
    return prices

def main():
    history=json.loads(HISTORY.read_text(encoding="utf-8"))
    changed=False; errors=[]
    targets=[x for x in history if isinstance(x,dict) and x.get("date") and not all((x.get("prices") or {}).get(c) is not None for c in PROBES)]
    print(f"TPEx backfill targets={len(targets)} history={len(history)}")
    for snap in targets:
        iso=str(snap["date"])
        try:
            px=fetch_day(iso)
            snap.setdefault("prices",{}).update(px)
            changed=True
            print(iso,"rows",len(px),"probes",{c:px.get(c) for c in PROBES})
        except Exception as e:
            errors.append(f"{iso}: {e}")
            print("ERROR",iso,e)
        time.sleep(0.15)
    if changed:
        HISTORY.write_text(json.dumps(history,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    coverage={c:sum(1 for x in history if (x.get("prices") or {}).get(c) is not None) for c in PROBES}
    print("coverage",coverage)
    if errors: print("errors",errors[:8])
    if min(coverage.values())<15:
        raise RuntimeError("TPEx history still insufficient: "+json.dumps(coverage,ensure_ascii=False))

if __name__=="__main__":
    main()
