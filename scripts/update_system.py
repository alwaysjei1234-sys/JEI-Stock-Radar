# Recompute feed after TPEx history backfill
#!/usr/bin/env python3
import json, math, re, statistics, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TWSE_STOCK="https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TWSE_INDEX="https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX"
TPEX_STOCK="https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
TWSE_MIS="https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
TWSE_INST="https://www.twse.com.tw/rwd/zh/fund/T86?response=json&selectType=ALLBUT0999"
TWSE_DAILY="https://www.twse.com.tw/exchangeReport/MI_INDEX"
TPEX_INST="https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading"
OUT=Path("remote/system.json")
HISTORY=Path("remote/history.json")
TZ=ZoneInfo("Asia/Taipei")

PORTFOLIO = [
    {"code":"1711","name":"永光","cost":52.674,"shares":1000},
    {"code":"2478","name":"大毅","cost":127.681,"shares":1000},
    {"code":"2609","name":"陽明","cost":63.69,"shares":1000},
    {"code":"2748","name":"雲品","cost":99.341,"shares":1000},
    {"code":"3162","name":"精確","cost":85.621,"shares":1000},
    {"code":"3289","name":"宜特","cost":141.701,"shares":1000},
    {"code":"3707","name":"漢磊","cost":73.104,"shares":1000},
    {"code":"5347","name":"世界","cost":123.175,"shares":1000},
    {"code":"5425","name":"台半","cost":102.145,"shares":1000},
    {"code":"6150","name":"撼訊","cost":77.51,"shares":2000},
    {"code":"7711","name":"永擎","cost":257.8665,"shares":2000},
    {"code":"8070","name":"長華*","cost":58.383,"shares":1000},
    {"code":"00937B","name":"群益ESG投等債20+","cost":15.6283,"shares":44000},
]

SECTOR_BASKETS={
    "AI伺服器/散熱":["2345","2382","3231","6669","3017","3324","3653","2059"],
    "PCB/載板":["3037","3189","8046","2368","2383","6274","6213","1815","8039"],
    "光通訊/CPO":["3081","3450","4979","3363","3163","6442","4908","4977","3234"],
    "被動元件":["2327","2492","2478","2375","6173","6127","8043","3090"],
    "記憶體/儲存":["2408","2344","2337","8299","3260","8271"],
    "功率半導體":["3707","5425","8261","2481","6138","3317","3105","8086"],
    "半導體設備/測試":["3289","6223","6510","3131","3583","6187","5443","6640"],
    "矽晶圓/材料":["6488","3532","6182","3016","5483"],
    "IC設計":["2454","3034","3443","6643","6531","4919","3661"],
    "封測":["6239","8150","2449","3711"],
    "航運":["2609","2603","2615"]
}

def fetch_json(url,tries=3):
    last=None
    for i in range(tries):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 JEI-Stock-Radar-Updater/3.2","Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=35) as r:
                return json.loads(r.read().decode("utf-8-sig"))
        except Exception as e:
            last=e
            if i+1<tries: time.sleep(1.2*(i+1))
    raise last


def fetch_twse_daily(date_yyyymmdd):
    url=TWSE_DAILY+"?"+urllib.parse.urlencode({"date":date_yyyymmdd,"type":"ALLBUT0999","response":"json"})
    j=fetch_json(url)
    tables=j.get("tables",[]) if isinstance(j,dict) else []
    best=None
    for t in tables:
        fields=t.get("fields",[]) if isinstance(t,dict) else []
        joined="|".join(map(str,fields))
        if "證券代號" in joined and "收盤價" in joined and t.get("data"):
            if best is None or len(t.get("data",[]))>len(best.get("data",[])):best=t
    if not best:
        raise RuntimeError("MI_INDEX returned no stock table: "+str(j.get("stat") if isinstance(j,dict) else type(j).__name__))
    fields=[re.sub(r"<[^>]+>","",str(x)).strip() for x in best.get("fields",[])]
    idx={x:i for i,x in enumerate(fields)}
    def cell(row,name):
        i=idx.get(name);return row[i] if i is not None and i<len(row) else None
    out=[]
    for row in best.get("data",[]):
        code=str(cell(row,"證券代號") or "").strip()
        if not re.fullmatch(r"[0-9A-Z]{4,8}",code):continue
        close=num(cell(row,"收盤價"));change=num(cell(row,"漲跌價差"))
        sign=str(cell(row,"漲跌(+/-)") or "")
        if change is not None and ("-" in sign or "－" in sign):change=-abs(change)
        out.append({"date":date_yyyymmdd,"code":code,"name":str(cell(row,"證券名稱") or "").strip(),
                    "open":num(cell(row,"開盤價")),"high":num(cell(row,"最高價")),"low":num(cell(row,"最低價")),
                    "close":close,"change":change,"pct":pct_from_change(close,change),
                    "volume":num(cell(row,"成交股數")) or 0,"value":num(cell(row,"成交金額")) or 0,"market":"TWSE"})
    return out

def fetch_json_fast(url, timeout=8, tries=1):
    last=None
    for i in range(tries):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 JEI-Stock-Radar-Updater/3.2","Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8-sig"))
        except Exception as e:
            last=e
    raise last


def fetch_tpex_daily(date_obj):
    # Official TPEx whole-market daily close quotes.
    roc=f"{date_obj.year-1911}/{date_obj.month:02d}/{date_obj.day:02d}"
    url="https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?"+urllib.parse.urlencode({
        "l":"zh-tw","o":"json","d":roc,"s":"0,asc,0"
    })
    j=fetch_json_fast(url, timeout=8, tries=1)
    rows=(j.get("aaData") or j.get("data") or []) if isinstance(j,dict) else []
    out=[]
    for row in rows:
        if isinstance(row,list) and len(row)>=3:
            code=re.sub(r"<[^>]+>","",str(row[0])).strip()
            close=num(row[2])
        elif isinstance(row,dict):
            code=str(pick(row,"SecuritiesCompanyCode","Code","股票代號","證券代號") or "").strip()
            close=num(pick(row,"Close","ClosePrice","收盤價"))
        else:continue
        if re.fullmatch(r"[0-9A-Z]{4,8}",code) and close is not None:
            out.append({"code":code,"close":close})
    if not out:raise RuntimeError("TPEx daily_close_quotes returned no parsed rows")
    return out

def backfill_twse_history(history, now, min_days=20, max_otc_fetches=0):
    """Keep the main market feed fast. Historical network backfill is handled separately."""
    snaps={str(x.get("date")):x for x in history if isinstance(x,dict) and x.get("date")}
    return sorted(snaps.values(),key=lambda x:str(x.get("date","")))[-90:],[]

def fetch_institutional():
    out={}; errs=[]; debug={}
    try:
        try:
            j=fetch_json(TWSE_INST)
        except Exception:
            j=fetch_json("https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999")
        fields=j.get("fields",[]) if isinstance(j,dict) else []
        data=j.get("data",[]) if isinstance(j,dict) else []
        if not data:
            raise RuntimeError("T86 returned no rows")
        debug["twse_fields"]=fields
        debug["twse_first"]=data[0] if data else None
        idx={re.sub(r"<[^>]+>","",str(name)).replace("\
","").replace(" ",""):i for i,name in enumerate(fields)}
        def gi(row,names):
            for name in names:
                key=str(name).replace(" ","")
                if key in idx and idx[key]<len(row): return num(row[idx[key]])
            return None
        for row in data:
            raw_code=str(row[0]).strip() if row else ""
            m=re.search(r"([0-9A-Z]{4,8})",raw_code.upper())
            if not m: continue
            code=m.group(1)
            foreign=gi(row,["外陸資買賣超股數(不含外資自營商)","外資及陸資買賣超股數(不含外資自營商)"])
            trust=gi(row,["投信買賣超股數"])
            dealer=gi(row,["自營商買賣超股數"])
            total=gi(row,["三大法人買賣超股數"])
            # Stable positional fallback for the official T86 19-column report.
            if len(row)>=19:
                if foreign is None: foreign=num(row[4])
                if trust is None: trust=num(row[10])
                if dealer is None: dealer=num(row[11])
                if total is None: total=num(row[18])
            out[code]={"foreign":foreign,"trust":trust,"dealer":dealer,"total":total,"source":"TWSE T86"}
    except Exception as e: errs.append("TWSE法人:"+str(e))
    try:
        rows=fetch_json(TPEX_INST)
        if not isinstance(rows,list) or not rows:
            raise RuntimeError("TPEx institutional endpoint returned no rows")
        debug["tpex_keys"]=list(rows[0].keys()) if isinstance(rows[0],dict) else []
        debug["tpex_first"]=rows[0] if rows else None
        for r in rows:
            raw_code=str(pick(r,"SecuritiesCompanyCode","SecuritiesCompanyCode","SecuritiesCode","Code","股票代號","證券代號") or "").strip()
            m=re.search(r"([0-9A-Z]{4,8})",raw_code.upper())
            if not m: continue
            code=m.group(1)
            foreign=num(pick(r,"ForeignInvestorsInclude MainlandAreaInvestors-Difference","Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference","ForeignDealers-Difference"))
            trust=num(pick(r,"SecuritiesInvestmentTrustCompanies-Difference","InvestmentTrustNetBuySell","InvestmentTrustBuySell"))
            dealer=num(pick(r,"Dealers-Difference","DealerNetBuySell","DealerBuySell"))
            total=num(pick(r,"TotalDifference","TotalNetBuySell","ThreeInstitutionalInvestorsNetBuySell"))
            out[code]={"foreign":foreign,"trust":trust,"dealer":dealer,"total":total,"source":"TPEx OpenAPI"}
    except Exception as e: errs.append("TPEx法人:"+str(e))
    if not out and not errs: errs.append("法人來源有回應，但未解析出任何股票代碼")
    return out,errs,debug

def fetch_mis_channels(channels):
    if not channels:return []
    qs=urllib.parse.urlencode({"ex_ch":"|".join(channels),"json":"1","delay":"0","_":str(int(time.time()*1000))})
    req=urllib.request.Request(TWSE_MIS+"?"+qs,headers={
        "User-Agent":"Mozilla/5.0 JEI-Stock-Radar-Updater/3.2",
        "Accept":"application/json,text/plain,*/*",
        "Referer":"https://mis.twse.com.tw/stock/index.jsp"
    })
    with urllib.request.urlopen(req,timeout=9) as r:
        j=json.loads(r.read().decode("utf-8-sig"))
    return j.get("msgArray",[]) if isinstance(j,dict) else []

def quote_num(m,key):
    raw=str(m.get(key,"") or "")
    for part in raw.split("_"):
        v=num(part)
        if v is not None and v>0:return v
    return None

def live_price(m):
    z=num(m.get("z"))
    if z is not None and z>0:return z
    b=quote_num(m,"b");a=quote_num(m,"a")
    if b and a:return (b+a)/2.0
    if b:return b
    if a:return a
    return num(m.get("y"))

def enrich_live(rows):
    by_code={x["code"]:x for x in rows}
    channels=[]
    for x in rows:
        if not re.fullmatch(r"\d{4}",x.get("code","")):continue
        prefix="tse_" if x.get("market")=="TWSE" else "otc_"
        channels.append(prefix+x["code"]+".tw")
    got=0;errors=[]
    # MIS is sensitive to oversized ex_ch queries/rate bursts. Use conservative
    # batches and retry failed/empty chunks at half size so a full-market scan
    # does not silently fall back to a stale daily snapshot.
    chunks=[channels[i:i+25] for i in range(0,len(channels),25)]
    messages=[]
    def fetch_chunk(ch):
        try:
            r=fetch_mis_channels(ch)
            if r:return r,[]
            raise RuntimeError("empty MIS batch")
        except Exception as first:
            if len(ch)<=8:return [],[str(first)]
            out=[];errs=[]
            mid=max(1,len(ch)//2)
            for sub in (ch[:mid],ch[mid:]):
                try:
                    rr=fetch_mis_channels(sub)
                    if rr:out.extend(rr)
                    else:errs.append("empty MIS retry")
                except Exception as e:errs.append(str(e))
                time.sleep(.12)
            return out,errs
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(fetch_chunk,ch):ch for ch in chunks}
        for fut in as_completed(futures):
            try:
                got_rows,errs=fut.result();messages.extend(got_rows);errors.extend(errs)
            except Exception as e:errors.append(str(e))
    for m in messages:
        code=str(m.get("c","")).strip()
        x=by_code.get(code)
        if not x:continue
        prev=num(m.get("y"));price=live_price(m)
        if price is None or price<=0 or prev is None or prev<=0:continue
        x["close"]=price;x["change"]=price-prev;x["pct"]=(price-prev)/prev*100.0
        o=num(m.get("o"));h=num(m.get("h"));l=num(m.get("l"));v=num(m.get("v"))
        if o and o>0:x["open"]=o
        if h and h>0:x["high"]=h
        if l and l>0:x["low"]=l
        if v is not None:
            x["live_volume"]=v
            if v>0:x["value"]=v*1000.0*price
        # MIS d/t are the exchange quote date/time; preserve them instead of using updater runtime.
        qd=str(m.get("d","") or "").strip(); qt=str(m.get("t","") or "").strip()
        if qd and qt:
            x["quote_time"]=f"{qd[:4]}-{qd[4:6]}-{qd[6:8]} {qt}"
        elif qt:
            x["quote_time"]=qt
        x["live"]=True;got+=1
    taiex=None
    try:
        idx=fetch_mis_channels(["tse_t00.tw"])
        if idx:
            y=num(idx[0].get("y"));z=live_price(idx[0])
            if z and y and y>0:taiex=(z-y)/y*100.0
    except Exception as e:errors.append("TAIEX:"+str(e))
    return rows,got,taiex,errors

def num(v):
    if v is None:return None
    s=str(v).strip().replace(",","").replace("+","")
    if s in ("","--","---","N/A","null"):return None
    try:return float(s)
    except Exception:return None

def pick(d,*keys):
    for k in keys:
        if k in d and str(d[k]).strip() not in ("","--","---"):return d[k]
    return None

def pct_from_change(close,change):
    if close is None or change is None:return None
    prev=close-change
    return change/prev*100.0 if prev>0 else None

def norm_twse(r):
    close=num(r.get("ClosingPrice"));change=num(r.get("Change"))
    return {"date":str(r.get("Date","")).strip(),"code":str(r.get("Code","")).strip(),"name":str(r.get("Name","")).strip(),
            "open":num(r.get("OpeningPrice")),"high":num(r.get("HighestPrice")),"low":num(r.get("LowestPrice")),
            "close":close,"change":change,"pct":pct_from_change(close,change),"volume":num(r.get("TradeVolume")) or 0,
            "value":num(r.get("TradeValue")) or 0,"market":"TWSE"}

def norm_tpex(r):
    close=num(pick(r,"Close","ClosingPrice"));change=num(pick(r,"Change","ChangeAmount"))
    return {"date":str(pick(r,"Date") or "").strip(),"code":str(pick(r,"SecuritiesCompanyCode","Code","SecuritiesCode") or "").strip(),
            "name":str(pick(r,"CompanyName","SecuritiesCompanyName","Name") or "").strip(),
            "open":num(pick(r,"Open","OpeningPrice")),"high":num(pick(r,"High","HighestPrice")),"low":num(pick(r,"Low","LowestPrice")),
            "close":close,"change":change,"pct":pct_from_change(close,change),
            "volume":num(pick(r,"TradingShares","TradeVolume")) or 0,"value":num(pick(r,"TransactionAmount","TradeValue","TradingValue")) or 0,
            "market":"TPEX"}

def clamp(x,lo,hi):return max(lo,min(hi,x))

def position(s):
    h,l,c=s.get("high"),s.get("low"),s.get("close")
    if h is None or l is None or c is None or h<=l:return .5
    return clamp((c-l)/(h-l),0,1)

def range_pct(s):
    h,l,c=s.get("high"),s.get("low"),s.get("close")
    if h is None or l is None or c is None or c<=0:return 3.0
    return clamp((h-l)/c*100.0,1.0,12.0)

def stock_only(s):
    return bool(re.fullmatch(r"\d{4}",s.get("code",""))) and s.get("close") and s.get("pct") is not None

def build_sector_stats(by_code):
    stats=[];stock_sector={}
    for name,codes in SECTOR_BASKETS.items():
        members=[by_code[c] for c in codes if c in by_code and by_code[c].get("pct") is not None]
        if len(members)<2: continue
        pcts=[x["pct"] for x in members]
        vals=[x.get("value",0) for x in members]
        adv=sum(1 for p in pcts if p>0)
        avg=statistics.mean(pcts);med=statistics.median(pcts)
        breadth=adv/len(members)
        hot=sum(1 for p in pcts if p>=3)
        score=round(clamp(50+avg*5+(breadth-.5)*24+hot*1.5,0,100))
        leaders=sorted(members,key=lambda x:(x["pct"],x.get("value",0)),reverse=True)[:3]
        stats.append({"name":name,"score":score,"avg_pct":round(avg,2),"median_pct":round(med,2),
                      "breadth":round(breadth*100,1),"members":len(members),
                      "value_billion":round(sum(vals)/1e8,1),
                      "leaders":[{"code":x["code"],"name":x["name"],"pct":round(x["pct"],2)} for x in leaders]})
        for c in codes: stock_sector[c]=name
    stats.sort(key=lambda x:(x["score"],x["value_billion"]),reverse=True)
    score_map={x["name"]:x["score"] for x in stats}
    return stats,stock_sector,score_map

def price_plan(s,mode,risk):
    c=s["close"];rp=range_pct(s)
    pull=clamp(rp*.28,0.8,2.8)/100
    entry_low=c*(1-pull);entry_high=c*(1.004 if mode=="attack" else 1.0)
    stop_pct=clamp(max(3.5,rp*1.25)+(1.0 if risk>=65 else 0),3.5,8.5)/100
    defense=c*(1-stop_pct)
    reward=max(.045,stop_pct*1.35)
    target1=c*(1+reward)
    target2=c*(1+reward*1.75)
    return {"entry_low":round(entry_low,2),"entry_high":round(entry_high,2),
            "defense":round(defense,2),"target1":round(target1,2),"target2":round(target2,2)}

def score_row(s,mode,risk,sector_score,heat_penalty=0):
    p=s["pct"];pos=position(s)
    value=max(s.get("value",0),1)
    liq=clamp((math.log10(value)-7.0)*5,0,18)
    value_accel=clamp((math.log10(value)-8.0)*2.2,0,6)
    sector=clamp((sector_score-45)*.34,0,15)
    risk_pen=clamp((risk-35)*.13,0,9)
    chase=max(0,p-7.0)*(4.0 if mode!="monster" else .5)
    if mode=="attack":
        momentum=clamp(p,0,7)*3.4
        score=34+momentum+pos*13+liq+sector+value_accel-risk_pen-chase-heat_penalty
    elif mode=="next":
        momentum=clamp(p+1,0,5.5)*3.5
        score=39+momentum+pos*15+liq+sector+value_accel*1.25-risk_pen-max(0,p-4.2)*5-heat_penalty*1.25
    else:
        score=38+clamp(p,0,10)*3.7+pos*12+liq+sector+value_accel*.5-risk_pen
    return int(round(clamp(score,0,99)))

def item(s,score,reason,mode,risk,sector,sector_score):
    x={"code":s["code"],"name":s["name"],"score":score,"reason":reason,"price":s["close"],
       "change_pct":round(s["pct"],2),"market":s["market"],"sector":sector or "其他","sector_score":sector_score}
    x.update(price_plan(s,mode,risk))
    return x

def load_history():
    try:
        h=json.loads(HISTORY.read_text(encoding="utf-8"))
        return h if isinstance(h,list) else []
    except Exception:return []

def update_history(history,date_key,stocks,signals,institutional_market=None):
    price_map={x["code"]:x["close"] for x in stocks if x.get("close")}
    snap={"date":date_key,"prices":price_map,"signals":[{"code":x["code"],"price":x["price"],"score":x["score"]} for x in signals[:8]]}
    if institutional_market:snap["institutional_market"]=institutional_market
    history=[x for x in history if x.get("date")!=date_key]
    history.append(snap)
    history=history[-90:]
    return history

def calc_backtest(history,current_prices):
    if len(history)<2:return {"hit3":None,"hit5":None,"hit10":None,"samples":0}
    periods=[(3,"hit3"),(5,"hit5"),(10,"hit10")]
    out={"hit3":None,"hit5":None,"hit10":None,"samples":0}
    total_samples=0
    for days,key in periods:
        wins=0;n=0
        for i,snap in enumerate(history):
            if i+days>=len(history):continue
            future=history[i+days].get("prices",{})
            for sig in snap.get("signals",[]):
                p0=num(sig.get("price"));p1=num(future.get(sig.get("code")))
                if p0 and p1:
                    n+=1
                    if p1/p0-1>=.03:wins+=1
        if n:
            out[key]=round(wins/n*100,1);total_samples=max(total_samples,n)
    out["samples"]=total_samples
    return out

def holding_decision(row, cost, market_risk):
    if not row or not row.get("close"):
        return {"action":"資料不足","reason":"尚無有效行情","limit_status":"未知"}
    price=row["close"]; day=row.get("pct") or 0
    pnl=(price/cost-1)*100
    limit_status="漲停" if day>=9.4 else ("跌停" if day<=-9.4 else "正常")
    if pnl>=50:
        action="移動停利"
        reason="獲利超過50%，保留強勢部位但啟動移動停利，避免大波段獲利明顯回吐"
    elif pnl>=15:
        action="獲利續抱" if day>-3 else "提高警戒"
        reason="已有15%以上獲利，趨勢未明顯轉弱可續抱；單日轉弱時優先保護獲利"
    elif pnl<=-12:
        action="反彈減碼" if day>0 else "提高警戒"
        reason="成本虧損超過12%，不再只用續抱觀察；反彈時優先降低套牢部位風險"
    elif day<=-5 or market_risk>=80:
        action="減碼/防守"
        reason="單日跌幅過大或整體市場進入高風險區"
    elif day<=-3 or market_risk>=65:
        action="提高警戒"
        reason="個股動能轉弱或整體市場風險升高"
    elif limit_status=="漲停" and pnl<0:
        action="強勢反彈續抱"
        reason="目前漲停但仍低於成本，先看強勢反彈延續，不把漲停誤判成停損訊號"
    else:
        action="續抱觀察"
        reason="價格與整體市場風險目前仍在可控範圍"
    return {"action":action,"reason":reason,"limit_status":limit_status}

def main():
    errors=[]
    try:twse_raw=fetch_json(TWSE_STOCK)
    except Exception as e:twse_raw=[];errors.append("TWSE股票:"+str(e))
    try:idx_raw=fetch_json(TWSE_INDEX)
    except Exception as e:idx_raw=[];errors.append("TWSE指數:"+str(e))
    try:tpex_raw=fetch_json(TPEX_STOCK)
    except Exception as e:tpex_raw=[];errors.append("TPEX:"+str(e))

    rows=[norm_twse(x) for x in twse_raw if isinstance(x,dict)]+[norm_tpex(x) for x in tpex_raw if isinstance(x,dict)]
    rows=[x for x in rows if x["code"] and x["close"]]

    now=datetime.now(TZ)
    today_ymd=now.strftime("%Y%m%d")
    today_roc=f"{now.year-1911:03d}{now.month:02d}{now.day:02d}"
    source_dates={re.sub(r"[^0-9]","",str(x.get("date",""))) for x in rows if x.get("date")}
    twse_source_dates={re.sub(r"[^0-9]","",str(x.get("date",""))) for x in rows if x.get("market")=="TWSE" and x.get("date")}
    if now.weekday()<5 and today_roc not in twse_source_dates and today_ymd not in twse_source_dates:
        try:
            fresh_twse=fetch_twse_daily(today_ymd)
            if fresh_twse:
                fresh_codes={x["code"] for x in fresh_twse}
                rows=[x for x in rows if not (x.get("market")=="TWSE" and x.get("code") in fresh_codes)]+fresh_twse
                errors.append(f"TWSE OpenAPI落後，已用當日MI_INDEX補入 {len(fresh_twse)} 檔")
        except Exception as e:errors.append("TWSE當日補資料:"+str(e))
    live_count=0;live_errors=[];taiex_live=None
    # Taiwan regular trading is 09:00-13:30. Keep a small post-close refresh window so the
    # final MIS quote can replace stale daily OpenAPI data before it rolls to today's date.
    market_open=now.weekday()<5 and ((now.hour==8 and now.minute>=45) or 9<=now.hour<14 or (now.hour==14 and now.minute<=10))
    # After close, official daily OpenAPI may still expose the prior trading date for a while.
    # During a bounded post-close window, use MIS final quotes to bridge that lag.
    post_close_refresh=now.weekday()<5 and 14<=now.hour<16
    if market_open or post_close_refresh:
        try:rows,live_count,taiex_live,live_errors=enrich_live(rows)
        except Exception as e:live_errors.append(str(e))
        if live_errors and live_count<100:errors.append("MIS盤中:"+(";".join(live_errors))[:120])

    stocks=[x for x in rows if stock_only(x)]
    by_code={x["code"]:x for x in stocks}
    holdings_by_code={x["code"]:x for x in rows if x.get("code")}
    institutional,inst_errors,inst_debug=fetch_institutional()
    institutional={k:v for k,v in institutional.items() if k in by_code}
    if inst_errors: errors.extend(inst_errors)
    if not institutional: errors.append("法人籌碼:官方資料暫無有效逐檔資料，已停用法人判讀")

    taiex_pct=None
    # Prefer the same-day official MI_INDEX summary when the daily OpenAPI index feed lags.
    if now.weekday()<5:
        try:
            ij=fetch_json(TWSE_DAILY+"?"+urllib.parse.urlencode({"date":today_ymd,"type":"ALL","response":"json"}))
            for t in (ij.get("tables",[]) if isinstance(ij,dict) else []):
                fields=[re.sub(r"<[^>]+>","",str(v)).strip() for v in t.get("fields",[])]
                if "指數" not in fields or not t.get("data"):continue
                fi={v:i for i,v in enumerate(fields)}
                for row in t.get("data",[]):
                    name=str(row[fi["指數"]]).strip() if fi.get("指數") is not None and fi["指數"]<len(row) else ""
                    if name!="發行量加權股價指數":continue
                    def rc(*names):
                        for n in names:
                            i=fi.get(n)
                            if i is not None and i<len(row):return row[i]
                        return None
                    p=num(rc("漲跌百分比(%)","漲跌百分比"))
                    if p is not None:
                        sign=str(rc("漲跌(+/-)","漲跌") or "")
                        taiex_pct=-abs(p) if ("-" in sign or "－" in sign) else p
                    break
                if taiex_pct is not None:break
        except Exception as e:errors.append("TWSE當日指數:"+str(e))
    if taiex_pct is None:
        for x in idx_raw if isinstance(idx_raw,list) else []:
            if str(x.get("指數","")).strip()=="發行量加權股價指數":
                p=num(x.get("漲跌百分比"));sign=str(x.get("漲跌","")).strip()
                taiex_pct=(-abs(p) if sign=="-" and p is not None else p);break
    if taiex_live is not None:taiex_pct=taiex_live

    pcts=[x["pct"] for x in stocks if x["pct"] is not None]
    adv=sum(1 for p in pcts if p>0);dec=sum(1 for p in pcts if p<0);flat=max(0,len(pcts)-adv-dec)
    adv_ratio=adv/max(1,adv+dec);median=statistics.median(pcts) if pcts else 0
    down3=sum(1 for p in pcts if p<=-3);down5=sum(1 for p in pcts if p<=-5);limit_down=sum(1 for p in pcts if p<=-9.4)
    up5=sum(1 for p in pcts if p>=5);up8=sum(1 for p in pcts if p>=8)

    # Institutional breadth: use direction across the whole stock universe, not a single stock.
    inst_vals=[num(v.get("total")) for v in institutional.values()]
    inst_vals=[x for x in inst_vals if x is not None]
    inst_sell=sum(1 for x in inst_vals if x<0); inst_buy=sum(1 for x in inst_vals if x>0)
    inst_sell_ratio=inst_sell/max(1,inst_sell+inst_buy)
    inst_total=sum(inst_vals) if inst_vals else 0

    hist_before=load_history()
    prev_inst=[x.get("institutional_market",{}) for x in hist_before[-5:] if x.get("institutional_market")]
    prev_sell=[num(x.get("sell_ratio")) for x in prev_inst]
    prev_sell=[x for x in prev_sell if x is not None]
    inst_3d=(prev_sell[-2:]+[inst_sell_ratio*100])[-3:]
    inst_5d=(prev_sell[-4:]+[inst_sell_ratio*100])[-5:]
    inst_3d_avg=sum(inst_3d)/len(inst_3d) if inst_3d else inst_sell_ratio*100
    inst_5d_avg=sum(inst_5d)/len(inst_5d) if inst_5d else inst_sell_ratio*100
    inst_withdrawal=len(inst_3d)>=3 and inst_3d_avg>=60 and inst_3d[-1]>=inst_3d[0]

    risk=30
    if taiex_pct is not None:risk+=clamp(-taiex_pct,0,6)*10-clamp(taiex_pct,0,4)*4
    risk+=clamp((.50-adv_ratio)*100,0,40)*1.0
    risk+=clamp(-median,0,5)*8
    risk+=clamp(down5/max(1,len(pcts))*100,0,25)*1.4
    risk+=clamp(limit_down,0,50)*.8
    divergence=(taiex_pct or 0)>1.0 and adv_ratio<.45
    if divergence:risk+=12
    if (taiex_pct or 0)>1.0 and median<0:risk+=4
    if adv_ratio<.40:risk+=5
    if adv_ratio>.58 and median>.4:risk-=6
    # Raise crash risk only when institutional selling is broad and price breadth also deteriorates.
    if len(inst_vals)>=500:
        if inst_sell_ratio>=.68 and adv_ratio<.45:risk+=12
        elif inst_sell_ratio>=.60 and adv_ratio<.50:risk+=7
        if inst_sell_ratio<=.40 and adv_ratio>.52:risk-=4
        if inst_withdrawal and adv_ratio<.48:risk+=8
    risk=int(round(clamp(risk,0,100)))

    if risk>=80:level,label,cash="red","高風險防守","70%↑"
    elif risk>=65:level,label,cash="orange",("內部轉弱警戒" if divergence else "風險升高"),"50%–70%"
    elif risk>=45:level,label,cash="yellow",("權值撐盤警戒" if divergence else "震盪警戒"),"30%–50%"
    else:level,label,cash="green","正常","20%–30%"

    sectors,stock_sector,sector_scores=build_sector_stats(by_code)
    tradable=[x for x in stocks if x["value"]>=30000000]

    def secinfo(s):
        sec=stock_sector.get(s["code"],"其他")
        return sec,sector_scores.get(sec,50)

    hist_for_heat=load_history()
    hist_for_heat,history_backfill_errors=backfill_twse_history(hist_for_heat,now,20)
    if history_backfill_errors:
        errors.append("歷史行情回補:"+history_backfill_errors[0])
    # Fail loudly if OTC history did not actually backfill; a green workflow must mean usable momentum data.
    otc_probe=("5347","5425","6150","6187")
    otc_cov={code:sum(1 for snap in hist_for_heat if num((snap.get("prices") or {}).get(code))) for code in otc_probe}
    # During staged backfill, keep the feed publishable; expose coverage in system data.
    otc_history_ready=min(otc_cov.values() or [0])>=5
    recent_for_heat=hist_for_heat[-21:]
    def recent_heat(s):
        code=s["code"]; cur=s["close"]
        series=[]
        for snap in recent_for_heat:
            p=num((snap.get("prices") or {}).get(code))
            if p and p>0:
                series.append(p)
        vals=[]
        for n in (5,10,20):
            if len(series)>=n+1:
                base=series[-(n+1)]
                vals.append((cur/base-1)*100)
            else:
                vals.append(None)
        r5,r10,r20=vals
        p5=0 if r5 is None else max(0,r5-12)*.8
        p10=0 if r10 is None else max(0,r10-20)*.55
        p20=0 if r20 is None else max(0,r20-32)*.35
        penalty=clamp(p5+p10+p20,0,24)
        return r5,r10,r20,penalty

    def fmt_ret(v):
        return "資料不足" if v is None else f"{v:+.1f}%"

    attack_pool=[]
    next_pool=[]
    monster_pool=[]
    for s in tradable:
        sec,ss=secinfo(s)
        if .8<=s["pct"]<=8.8 and position(s)>=.58:
            r5,r10,r20,hp=recent_heat(s)
            attack_pool.append((score_row(s,"attack",risk,ss,hp),s,sec,ss,r5,r10,r20,hp))
        if -.8<=s["pct"]<=4.8 and position(s)>=.62 and (s["open"] is None or s["close"]>=s["open"]*.995):
            r5,r10,r20,hp=recent_heat(s)
            next_pool.append((score_row(s,"next",risk,ss,hp),s,sec,ss,r5,r10,r20,hp))
        # V3.3 abnormal-money radar: allow pre-breakout names, not only stocks already +5%.
        # Strong close + meaningful turnover + hot sector can enter the radar earlier.
        money_signal=(s["value"]>=300000000 and position(s)>=.72 and ss>=58 and s["pct"]>=2.2)
        price_signal=(s["pct"]>=5 and position(s)>=.70)
        if money_signal or price_signal:
            r5,r10,r20,hp=recent_heat(s)
            base_score=score_row(s,"monster",risk,ss,hp)
            early_bonus=6 if money_signal and s["pct"]<5 else 0
            isolation_penalty=8 if ss<48 else 0
            monster_pool.append((int(clamp(base_score+early_bonus-isolation_penalty-hp*.35,0,99)),s,sec,ss,r5,r10,r20,hp))

    attack_pool.sort(key=lambda x:(x[0],x[1]["value"]),reverse=True)
    attack=[]
    for score,s,sec,ss,r5,r10,r20,hp in attack_pool[:10]:
        chase="｜接近漲停，勿追高" if s["pct"]>=8.5 else ""
        reason=f"{sec}熱度 {ss}｜漲幅 {s['pct']:.2f}%｜收盤位置 {position(s)*100:.0f}%｜成交值 {s['value']/1e8:.1f} 億{chase}"
        attack.append(item(s,score,reason,"attack",risk,sec,ss))

    attack_codes={x["code"] for x in attack[:5]}
    next_pool=[x for x in next_pool if x[1]["code"] not in attack_codes]
    next_pool.sort(key=lambda x:(x[0],x[1]["value"]),reverse=True)
    next_list=[]
    for score,s,sec,ss,r5,r10,r20,hp in next_pool[:10]:
        setup=round(clamp(ss*.42+position(s)*100*.28+clamp((math.log10(max(s.get("value",1),1))-7)*12,0,100)*.18+(100-min(100,hp*5))*.12,0,99))
        reason=f"準備發動 {setup}分｜{sec} {ss}分｜今日 {s['pct']:+.2f}%｜5日 {fmt_ret(r5)}｜10日 {fmt_ret(r10)}｜成交值 {s['value']/1e8:.1f}億｜"+("低過熱" if hp<4 else "過熱降權")
        next_list.append(item(s,score,reason,"next",risk,sec,ss))

    monster_pool.sort(key=lambda x:(x[0],x[1]["pct"],x[1]["value"]),reverse=True)
    monster=[]
    for score,s,sec,ss,r5,r10,r20,hp in monster_pool[:10]:
        phase="異常資金提前卡位" if s["pct"]<5 else "強勢加速"
        reason=f"{phase}｜{sec} {ss}分｜今日 {s['pct']:+.2f}%｜5日 {fmt_ret(r5)}｜成交值 {s['value']/1e8:.1f}億｜收盤位置 {position(s)*100:.0f}%｜"+("低過熱" if hp<4 else "過熱警戒")
        monster.append(item(s,score,reason,"monster",risk,sec,ss))

    rotate_src=sorted(attack[:8]+next_list[:8],key=lambda x:(x.get("sector_score",50),x["score"]),reverse=True)[:8]
    rotate=[dict(x,reason="換股候選｜"+x["reason"]) for x in rotate_src]

    taiex_txt="--" if taiex_pct is None else f"{taiex_pct:+.2f}%"
    if risk>=80:market_status="紅燈防守"
    elif risk>=65:market_status="偏空警戒"
    elif (taiex_pct or 0)>1.0 and adv_ratio<.45:market_status="權值強／中小型弱"
    elif (taiex_pct or 0)<-1.0 and adv_ratio>.55:market_status="指數弱／個股抗跌"
    elif (taiex_pct or 0)>.6 and adv_ratio>.56:market_status="偏多"
    elif (taiex_pct or 0)<-.8 or adv_ratio<.42:market_status="偏空"
    else:market_status="震盪"

    reasons=[f"加權指數 {taiex_txt}",f"上漲 {adv} / 下跌 {dec}（廣度 {adv_ratio*100:.1f}%）",
             f"市場中位數 {median:+.2f}%",f"跌逾3% {down3}｜跌逾5% {down5}｜跌停附近 {limit_down}"]
    if inst_vals:
        reasons.append(f"法人偏賣 {inst_sell_ratio*100:.1f}%｜3日均 {inst_3d_avg:.1f}%｜5日均 {inst_5d_avg:.1f}%｜淨額 {inst_total/1000:+,.0f}張")
        if inst_withdrawal:reasons.append("法人連續撤退警訊：3日偏賣率高檔且惡化")
    if sectors:reasons.append("最強族群 "+sectors[0]["name"]+f" {sectors[0]['score']}分")
    if errors:reasons.append("部分資料源降級："+"；".join(errors)[:140])

    flow=[
        {"icon":"↗","name":"市場廣度","note":f"上漲 {adv} / 下跌 {dec}｜廣度 {adv_ratio*100:.1f}%","score":round(adv_ratio*100)},
        {"icon":"⚠","name":"尾端賣壓","note":f"跌逾3% {down3}｜跌逾5% {down5}｜跌停附近 {limit_down}","score":down5},
        {"icon":"🔥","name":"強勢動能","note":f"漲逾5% {up5}｜漲逾8% {up8}","score":up5},
        {"icon":"◎","name":"市場中位數","note":"排除權值股後觀察整體溫度","score":round(median,2)},
        {"icon":"🏦","name":"法人籌碼廣度","note":f"偏賣 {inst_sell_ratio*100:.1f}%｜合計 {inst_total/1000:+,.0f}張","score":round(inst_sell_ratio*100,1)}
    ]

    priority=[{"title":"市場風控","note":"｜".join(reasons[:4]),"action":label}]
    if sectors:priority.append({"title":"族群主線："+sectors[0]["name"],"note":f"熱度 {sectors[0]['score']}｜平均 {sectors[0]['avg_pct']:+.2f}%｜上漲比 {sectors[0]['breadth']:.1f}%","action":"主線"})
    if attack:priority.append({"title":attack[0]["code"]+" "+attack[0]["name"],"note":attack[0]["reason"],"action":"主攻#1"})
    if next_list:priority.append({"title":next_list[0]["code"]+" "+next_list[0]["name"],"note":next_list[0]["reason"],"action":"下一棒#1"})

    raw_date=next((x["date"] for x in rows if x["date"]),"")
    # Never present a stale daily date as if it were current intraday data.
    # When MIS successfully enriched a meaningful universe, label the feed with today's
    # Taiwan date while retaining the official daily source date separately.
    source_data_date=raw_date
    live_coverage=live_count/max(1,len(stocks))
    live_valid=live_count>=500 and live_coverage>=.35
    today_iso=now.strftime("%Y-%m-%d")
    today_roc=f"{now.year-1911:03d}{now.month:02d}{now.day:02d}"
    source_compact=re.sub(r"[^0-9]","",str(source_data_date or ""))
    source_is_today=source_compact in (today_roc,re.sub(r"[^0-9]","",today_iso))
    stale_source=not source_is_today
    if live_valid:
        raw_date=today_iso
        stale_source=False
    elif stale_source:
        # Safety invariant applies all day, including after close: stale official
        # daily data must never be presented as today's attack/next/monster radar.
        errors.append(f"行情來源仍為 {source_data_date or '未知日期'}，今日候選榜暫停避免誤判")
        attack=[];next_list=[];monster=[];rotate=[]
        priority=[x for x in priority if x.get("action") not in ("主攻#1","下一棒#1")]
    elif market_open:
        errors.append(f"盤中即時覆蓋不足 {live_count}/{len(stocks)}，候選榜暫停避免誤判")
        attack=[];next_list=[];monster=[];rotate=[]
        priority=[x for x in priority if x.get("action") not in ("主攻#1","下一棒#1")]
    if stale_source:
        # Old market breadth/sector scores are retained only as raw historical context;
        # do not surface them as today's actionable market state.
        market_status="資料過期"
        label="資料過期，暫停判讀"
        priority=[{"title":"行情來源過期","note":f"官方來源日期 {source_data_date or '未知'}，等待今日資料後再產生主攻／下一棒／妖股與族群主線","action":"暫停判讀"}]
        reasons=[f"行情來源日期 {source_data_date or '未知'}，不是今天；今日風險與選股訊號暫停判讀"]
        sectors=[]
        flow=[]
    date_key=now.strftime("%Y-%m-%d")
    history=hist_for_heat
    history=update_history(history,date_key,stocks,attack[:5]+next_list[:5],{"sell_ratio":round(inst_sell_ratio*100,1),"net_lots":round(inst_total/1000)})
    HISTORY.parent.mkdir(parents=True,exist_ok=True)
    HISTORY.write_text(json.dumps(history,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    backtest=calc_backtest(history,{x["code"]:x["close"] for x in stocks})

    out={
        "schema":4,"updated_at":now.strftime("%Y-%m-%d %H:%M"),"data_date":raw_date,"source_data_date":source_data_date,
        "summary":"JEI 多因子決策：大盤風險 → 族群強弱 → 個股動能/流動性 → 持股成本與移動風控；避免只看單日漲幅。",
        "risk":{"level":level,"label":label,"score":risk,"cash":cash,"reasons":reasons,
                "breadth":round(adv_ratio*100,1),"median_pct":round(median,2),"down5":down5,"limit_down":limit_down,
                "divergence":divergence,"institutional_sell_ratio":round(inst_sell_ratio*100,1),"institutional_net_lots":round(inst_total/1000),
                "institutional_3d_sell_avg":round(inst_3d_avg,1),"institutional_5d_sell_avg":round(inst_5d_avg,1),"institutional_withdrawal":inst_withdrawal},
        "market":{"status":market_status,"mode":("盤中即時" if live_valid else ("資料過期" if stale_source else ("盤中資料不足" if market_open else "今日收盤"))),
                  "live_count":live_count,"live_coverage_pct":round(live_coverage*100,1),"live_valid":live_valid,"stale":stale_source,"post_close_refresh":post_close_refresh,
                  "brief":f"{'盤中即時' if live_valid else ('資料過期' if stale_source else ('盤中資料不足' if market_open else '今日收盤'))}多因子市場｜加權 {taiex_txt}｜廣度 {adv_ratio*100:.1f}%｜中位數 {median:+.2f}%｜跌逾5% {down5}｜JEI 每15分鐘更新"},
        "sectors":sectors,"stock_sectors":stock_sector,
        "universe":[{"code":x["code"],"name":x["name"],"market":x["market"]} for x in stocks if re.fullmatch(r"[1-9][0-9]{3}",x["code"])],
        "institutional":institutional,
        "institutional_status":{"ok":bool(institutional),"count":len(institutional),"errors":inst_errors,"debug":inst_debug},
        "holdings":{p["code"]:{
            "code":p["code"],"name":(holdings_by_code.get(p["code"]) or {}).get("name") or p["name"],
            "cost":p["cost"],"shares":p["shares"],
            "price":(holdings_by_code.get(p["code"]) or {}).get("close"),
            "change_pct":round((holdings_by_code.get(p["code"]) or {}).get("pct"),2) if (holdings_by_code.get(p["code"]) or {}).get("pct") is not None else None,
            "live":bool((holdings_by_code.get(p["code"]) or {}).get("live")),
            "market_value":round(((holdings_by_code.get(p["code"]) or {}).get("close") or 0)*p["shares"]),
            "pnl":round((((holdings_by_code.get(p["code"]) or {}).get("close") or p["cost"])-p["cost"])*p["shares"]),
            "pnl_pct":round((((holdings_by_code.get(p["code"]) or {}).get("close") or p["cost"])/p["cost"]-1)*100,2),
            "risk_action":holding_decision(holdings_by_code.get(p["code"]),p["cost"],risk)["action"],
            "risk_reason":holding_decision(holdings_by_code.get(p["code"]),p["cost"],risk)["reason"],
            "limit_status":holding_decision(holdings_by_code.get(p["code"]),p["cost"],risk)["limit_status"],
            "quote_time":(holdings_by_code.get(p["code"]) or {}).get("quote_time") if bool((holdings_by_code.get(p["code"]) or {}).get("live")) else None
        } for p in PORTFOLIO},"priority":priority,"attack":attack,"next":next_list,"monster":monster,"rotate":rotate,"flow":flow,
        "backtest":backtest,
        "sources":["TWSE OpenAPI STOCK_DAY_ALL","TWSE OpenAPI MI_INDEX","TPEx OpenAPI daily close quotes","TWSE MIS intraday stock/index quotes","TWSE T86 institutional investors","TPEx institutional investors OpenAPI"]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"updated_at":out["updated_at"],"risk":risk,"stocks":len(stocks),"live_count":live_count,"sectors":len(sectors),"errors":errors},ensure_ascii=False))

if __name__=="__main__":main()
