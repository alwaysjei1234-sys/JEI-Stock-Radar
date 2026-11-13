# Recompute feed after TPEx history backfill
#!/usr/bin/env python3
import json, math, re, statistics, time, urllib.request, urllib.parse, urllib.error, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
try:
    from scripts.corporate_actions import action_note, validated_actions
except ModuleNotFoundError as exc:
    if exc.name not in ('scripts','scripts.corporate_actions'):raise
    from corporate_actions import action_note, validated_actions
try:
    from scripts.pattern_signals import build_pattern_signals, attach_verified_ohlcv
except ModuleNotFoundError as exc:
    if exc.name not in ("scripts", "scripts.pattern_signals"):
        raise
    from pattern_signals import build_pattern_signals, attach_verified_ohlcv
try:
    from scripts.market_sessions import closure_reason, next_expected_session
    from scripts.public_holding_signals import is_safe_public_holdings, build_public_holding_signals
except ModuleNotFoundError as exc:
    if exc.name not in ("scripts", "scripts.market_sessions", "scripts.public_holding_signals"):
        raise
    from market_sessions import closure_reason, next_expected_session
    from public_holding_signals import is_safe_public_holdings, build_public_holding_signals

TWSE_STOCK="https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TWSE_INDEX="https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX"
TPEX_STOCK="https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
TWSE_MIS="https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
TWSE_INST="https://www.twse.com.tw/rwd/zh/fund/T86?response=json&selectType=ALLBUT0999"
TWSE_DAILY="https://www.twse.com.tw/exchangeReport/MI_INDEX"
TPEX_INST="https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading"
OUT=Path("remote/system.json")
HISTORY=Path("remote/history.json")
DAILY_PRICES=Path("remote/daily_prices.json")
TZ=ZoneInfo("Asia/Taipei")


def normalize_exchange_date(value):
    digits=re.sub(r"[^0-9]","",str(value or ""))
    if len(digits)==7:  # ROC yyyMMdd
        return f"{int(digits[:3])+1911:04d}-{digits[3:5]}-{digits[5:7]}"
    if len(digits)==8:  # Gregorian yyyyMMdd
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return None

def verified_archive_date(value):
    """Return a real ISO trading date or None; never invent a run-date candle."""
    if not isinstance(value,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",value):
        return None
    try:
        datetime.strptime(value,"%Y-%m-%d")
    except ValueError:
        return None
    return value


def latest_shared_close_date(twse_dates,tpex_dates,today,previous,market_open,now_date):
    """Use a newer, date-matched exchange close on off-hours refreshes only."""
    shared=set(twse_dates)&set(tpex_dates)
    if not shared:return None
    candidate=max(shared)
    if candidate==today:return candidate
    if market_open or candidate>today or (previous and candidate<=previous):return None
    try:
        age=(datetime.strptime(now_date,"%Y-%m-%d").date()-datetime.strptime(candidate,"%Y-%m-%d").date()).days
    except ValueError:
        return None
    return candidate if 0<=age<=7 else None

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


def require_twse_daily_date(payload, expected_date):
    """The URL date is a request, not evidence of the response's session."""
    expected=(verified_archive_date(normalize_exchange_date(expected_date))
              if isinstance(expected_date,str) and re.fullmatch(r"\d{8}",expected_date) else None)
    if expected is None:
        raise ValueError("MI_INDEX requested date is invalid")
    actual=payload.get("date") if isinstance(payload,dict) else None
    if (not isinstance(payload,dict) or payload.get("stat")!="OK" or
            actual!=expected_date):
        raise ValueError("MI_INDEX response status/date is not verified for "+expected)
    return expected


def twse_daily_index_pct(payload, expected_date):
    require_twse_daily_date(payload,expected_date)
    for table in payload.get("tables",[]):
        if not isinstance(table,dict):continue
        fields=[re.sub(r"<[^>]+>","",str(v)).strip() for v in table.get("fields",[])]
        if "指數" not in fields:continue
        for row in table.get("data",[]):
            if not isinstance(row,list):continue
            def cell(*names):
                for name in names:
                    if name in fields and fields.index(name)<len(row):return row[fields.index(name)]
                return None
            if str(cell("指數") or "").strip()!="發行量加權股價指數":continue
            pct=num(cell("漲跌百分比(%)","漲跌百分比"))
            if pct is not None:
                sign=str(cell("漲跌(+/-)","漲跌") or "")
                return -abs(pct) if ("-" in sign or "－" in sign) else pct
    return None


def twse_openapi_index_pct(payload, expected_date):
    expected=verified_archive_date(normalize_exchange_date(expected_date))
    if expected is None:return None
    for row in payload if isinstance(payload,list) else []:
        if not isinstance(row,dict):continue
        actual=row.get("日期")
        if (not isinstance(actual,str) or
                verified_archive_date(normalize_exchange_date(actual))!=expected):continue
        if str(row.get("指數","")).strip()!="發行量加權股價指數":continue
        pct=num(row.get("漲跌百分比"))
        if pct is not None:
            sign=str(row.get("漲跌","")).strip()
            return -abs(pct) if sign in ("-","－") else pct
    return None


def fetch_twse_daily(date_yyyymmdd):
    url=TWSE_DAILY+"?"+urllib.parse.urlencode({"date":date_yyyymmdd,"type":"ALLBUT0999","response":"json"})
    j=fetch_json(url)
    require_twse_daily_date(j,date_yyyymmdd)
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


def parse_tpex_latest_snapshot(payload, date_obj):
    """Accept only a full official TPEx OpenAPI snapshot for the exact requested day."""
    if not isinstance(payload,list):
        raise RuntimeError("TPEx latest OpenAPI payload is not a list")
    expected=date_obj.isoformat()
    observed=set()
    unique={}
    for row in payload:
        if not isinstance(row,dict):continue
        day=normalize_exchange_date(row.get("Date"))
        if day:observed.add(day)
        if day!=expected:continue
        code=str(row.get("SecuritiesCompanyCode") or "").strip()
        close=num(row.get("Close"))
        if re.fullmatch(r"[1-9][0-9]{3}",code) and close is not None and close>0:
            unique[code]={"code":code,"close":close}
    if observed!={expected}:
        raise RuntimeError(f"TPEx latest OpenAPI date mismatch: expected={expected}; observed={sorted(observed)[:4]}")
    if len(unique)<500:
        raise RuntimeError(f"TPEx latest OpenAPI coverage too low: {len(unique)} valid stocks")
    return list(unique.values())


def parse_tpex_dated_quotes(payload,date_obj):
    """Parse the current official TPEx table using its own date and columns.

    Return full OHLCV rows: close-only fallback rows cannot supply the OTC
    breadth, names, liquidity or tracked ETF reference used by the updater.
    """
    expected=date_obj.isoformat()
    if (not isinstance(payload,dict) or str(payload.get('stat','')).lower()!='ok'
            or normalize_exchange_date(payload.get('date'))!=expected):
        raise RuntimeError('TPEx dated root status/date mismatch')
    tables=payload.get('tables')
    if not isinstance(tables,list):raise RuntimeError('TPEx dated tables missing')
    unique={}
    for table in tables:
        if not isinstance(table,dict):continue
        fields=table.get('fields')
        if not isinstance(fields,list) or not all(isinstance(x,str) for x in fields):continue
        fields=[re.sub(r'<[^>]+>','',x).strip() for x in fields]
        if '代號' not in fields or '收盤' not in fields:continue
        # The official response also includes an empty, undated management
        # table. It contributes no observations and must not invalidate stocks.
        if table.get('data')==[]:continue
        if normalize_exchange_date(table.get('date'))!=expected:
            raise RuntimeError('TPEx dated table date mismatch')
        if len(fields)!=len(set(fields)):raise RuntimeError('TPEx dated duplicate fields')
        required={'代號','名稱','收盤','漲跌','開盤','最高','最低','成交股數','成交金額(元)'}
        if not required.issubset(fields):raise RuntimeError('TPEx dated required columns missing')
        positions={name:fields.index(name) for name in required}
        rows=table.get('data')
        if not isinstance(rows,list):raise RuntimeError('TPEx dated rows missing')
        for row in rows:
            if not isinstance(row,list) or len(row)<len(fields):continue
            cell=lambda key:row[positions[key]]
            code=str(cell('代號')).strip()
            close=num(cell('收盤'))
            if not re.fullmatch(r'(?:[1-9][0-9]{3}|0[0-9A-Z]{3,7})',code) or close is None or close<=0:continue
            change=num(re.sub(r'<[^>]+>','',str(cell('漲跌'))))
            record={'date':expected,'market':'TPEX','code':code,'name':str(cell('名稱')).strip(),
                'close':close,'change':change,'pct':pct_from_change(close,change),
                'price_note':action_note(cell('漲跌')),
                'open':num(cell('開盤')),'high':num(cell('最高')),'low':num(cell('最低')),
                'volume':num(cell('成交股數')) or 0,'value':num(cell('成交金額(元)')) or 0}
            if record['volume']<0 or record['value']<0:continue
            if code in unique and unique[code]!=record:
                raise RuntimeError('TPEx dated conflicting duplicate code')
            unique[code]=record
    ordinary=sum(bool(re.fullmatch(r'[1-9][0-9]{3}',code)) and row['pct'] is not None
                 for code,row in unique.items())
    if ordinary<500:raise RuntimeError(f'TPEx dated coverage too low: {ordinary} complete stocks')
    return list(unique.values())


def fetch_tpex_daily(date_obj):
    # Current TPEx website endpoint, with both root and table dates verified.
    modern_url='https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?'+urllib.parse.urlencode({
        'date':date_obj.strftime('%Y/%m/%d'),'id':'','response':'json'})
    try:
        return parse_tpex_dated_quotes(fetch_json_fast(modern_url,timeout=15,tries=1),date_obj)
    except Exception as exc:
        modern_problem=type(exc).__name__+': '+str(exc)[:100]
    # Try the date-specific historical endpoint first. When its CDN response
    # is empty, the official latest-only OpenAPI is a safe fallback ONLY if
    # its embedded Date matches the requested trading day exactly.
    roc=f"{date_obj.year-1911}/{date_obj.month:02d}/{date_obj.day:02d}"
    url="https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?"+urllib.parse.urlencode({
        "l":"zh-tw","o":"json","d":roc,"s":"0,asc,0"
    })
    old_problem="unknown"
    try:
        j=fetch_json_fast(url,timeout=8,tries=1)
        # Reject a cached historical response if its embedded report date disagrees
        # with the requested session; the latest OpenAPI fallback checks every row.
        if isinstance(j,dict):
            reported={normalize_exchange_date(j.get(key)) for key in ("reportDate","ReportDate","date","Date") if j.get(key)}
            reported.discard(None)
            if reported and reported!={date_obj.isoformat()}:
                raise ValueError(f"TPEx historical report date mismatch: expected={date_obj.isoformat()}, observed={sorted(reported)}")
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
            if re.fullmatch(r"[1-9][0-9]{3}",code) and close is not None and close>0:
                out.append({"code":code,"close":close})
        unique={x["code"]:x for x in out}
        if len(unique)>=500:
            return list(unique.values())
        keys=",".join(list(j)[:12]) if isinstance(j,dict) else type(j).__name__
        old_problem=f"coverage={len(unique)}, raw_rows={len(rows)}, keys={keys}"
    except Exception as exc:
        old_problem=f"{type(exc).__name__}: {str(exc)[:100]}"
    try:
        snapshot=fetch_json_fast("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",timeout=12,tries=1)
        return parse_tpex_latest_snapshot(snapshot,date_obj)
    except Exception as exc:
        raise RuntimeError(f"TPEx daily close unavailable: dated({modern_problem}); historical({old_problem}); latest({type(exc).__name__}: {str(exc)[:125]})") from exc


def fetch_latest_offhours_close(rows, now, previous_data_date):
    """Backfill a newer shared TWSE/TPEx official close after the live session."""
    minutes=now.hour*60+now.minute
    if now.weekday()<5 and 540<=minutes<810:
        return rows,None
    for offset in range(0,8):
        day=now.date()-timedelta(days=offset)
        day_key=day.isoformat()
        if day.weekday()>=5:
            continue
        if previous_data_date and day_key<=previous_data_date:
            # A same-day archive must not disable recovery when an OpenAPI
            # snapshot still lags. Revalidate dated sources so late official
            # institutional data can be incorporated on subsequent refreshes.
            if day_key!=now.date().isoformat() or day_key<previous_data_date:
                break
            complete=True
            for market in ("TWSE","TPEX"):
                observed=[x for x in rows if x.get("market")==market]
                dates={normalize_exchange_date(x.get("date")) for x in observed}
                if sum(bool(stock_only(x)) for x in observed)<500 or dates!={day_key}:
                    complete=False
            if complete:
                break
        try:
            twse=fetch_twse_daily(day.strftime("%Y%m%d"))
            tpex=fetch_tpex_daily(day)
            twse_count=len(twse)
            tpex_count=len(tpex)
            twse_dates=sorted({normalize_exchange_date(x.get("date")) for x in twse if x.get("date")})
            # Historical/latest fallbacks may return close-only rows. Those
            # certify prices, not the changes needed for breadth and scoring.
            # Never replace full analysis rows with an incomplete close table.
            if (sum(bool(stock_only(x)) for x in twse)<500
                    or sum(bool(stock_only(x)) for x in tpex)<500
                    or twse_dates!=[day_key]):
                print(json.dumps({"offhours_close_attempt":day_key,"twse_count":twse_count,
                                  "tpex_count":tpex_count,"twse_dates":twse_dates},ensure_ascii=False))
                continue
            for row in tpex:
                row["date"]=day_key
                row["market"]="TPEX"
            base=[x for x in rows if x.get("market") not in ("TWSE","TPEX")]
            print(json.dumps({"offhours_close_selected":day_key,"twse_count":twse_count,
                              "tpex_count":tpex_count},ensure_ascii=False))
            return base+twse+tpex,day_key
        except Exception as exc:
            print(json.dumps({"offhours_close_error":day_key,"error":f"{type(exc).__name__}: {str(exc)[:140]}"},ensure_ascii=False))
            continue
    return rows,None

def backfill_twse_history(history, now, min_days=20, max_otc_fetches=0):
    """Keep the main market feed fast. Historical network backfill is handled separately."""
    snaps={str(x.get("date")):x for x in history if isinstance(x,dict) and x.get("date")}
    return sorted(snaps.values(),key=lambda x:str(x.get("date","")))[-90:],[]

def institutional_totals_reconcile(row):
    # Exchange totals exclude foreign dealers to avoid double-counting.
    foreign, trust, dealer, total = (num(row.get(k)) for k in ("foreign", "trust", "dealer", "total"))
    return (all(value is not None and value.is_integer() for value in (foreign, trust, dealer, total))
            and foreign + trust + dealer == total)


def institutional_market_complete(rows, errors, expected_date):
    """Require dated, reconciled totals from both exchanges for market scoring."""
    return (not errors and {v.get("source") for v in rows.values()}=={"TWSE T86","TPEx OpenAPI"}
            and all(v.get("data_date")==expected_date and institutional_totals_reconcile(v)
                    for v in rows.values()))


def fetch_institutional(expected_date=None):
    expected_date=expected_date or datetime.now(TZ).strftime("%Y-%m-%d")
    out={}; errs=[]; debug={}
    try:
        # Request the exact session rather than relying on the endpoint's
        # latest-date default, which can lag or return a previous trading day.
        ymd=expected_date.replace("-", "")
        twse_urls=(TWSE_INST, "https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999")
        j=None; last_error=None
        for endpoint in twse_urls:
            try:
                candidate=fetch_json(endpoint+"&date="+ymd)
                if (not isinstance(candidate,dict) or candidate.get("stat")!="OK" or
                        verified_archive_date(normalize_exchange_date(candidate.get("date")))!=expected_date):
                    raise ValueError("T86 response status/date not verified for "+expected_date)
                j=candidate
                break
            except Exception as exc:
                last_error=exc
        if j is None:
            raise ValueError("T86 dated endpoints unavailable or unverified for "+expected_date) from last_error
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
            out[code]={"foreign":foreign,"trust":trust,"dealer":dealer,"total":total,"source":"TWSE T86","data_date":expected_date}
    except Exception as e: errs.append("TWSE法人:"+str(e))
    try:
        rows=fetch_json(TPEX_INST)
        if not isinstance(rows,list) or not rows:
            raise RuntimeError("TPEx institutional endpoint returned no rows")
        if any(not isinstance(r,dict) or
               verified_archive_date(normalize_exchange_date(r.get("Date")))!=expected_date for r in rows):
            raise ValueError("TPEx institutional response dates not verified for "+expected_date)
        debug["tpex_keys"]=list(rows[0].keys()) if isinstance(rows[0],dict) else []
        debug["tpex_first"]=rows[0] if rows else None
        for r in rows:
            raw_code=str(pick(r,"SecuritiesCompanyCode","SecuritiesCompanyCode","SecuritiesCode","Code","股票代號","證券代號") or "").strip()
            m=re.search(r"([0-9A-Z]{4,8})",raw_code.upper())
            if not m: continue
            code=m.group(1)
            foreign=num(pick(r,"Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference"))
            trust=num(pick(r,"SecuritiesInvestmentTrustCompanies-Difference","InvestmentTrustNetBuySell","InvestmentTrustBuySell"))
            dealer=num(pick(r,"Dealers-Difference","DealerNetBuySell","DealerBuySell"))
            total=num(pick(r,"TotalDifference","TotalNetBuySell","ThreeInstitutionalInvestorsNetBuySell"))
            out[code]={"foreign":foreign,"trust":trust,"dealer":dealer,"total":total,"source":"TPEx OpenAPI","data_date":expected_date}
    except Exception as e: errs.append("TPEx法人:"+str(e))
    invalid = {}
    for code, row in list(out.items()):
        if not institutional_totals_reconcile(row):
            source = row["source"]
            invalid[source] = invalid.get(source, 0) + 1
            del out[code]
    for source in ("TWSE T86","TPEx OpenAPI"):
        if invalid.get(source):
            errs.append(f"{source}: {invalid[source]} institutional rows do not reconcile")
        if not any(v.get("source")==source for v in out.values()):
            errs.append(source+": no dated reconciled institutional totals")
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
    # A transport success can still carry an MIS application error. Do not
    # let its payload reach quote validation or count a malformed envelope
    # as a successful service response. Existing callers handle failures.
    if (not isinstance(j,dict) or j.get("rtcode")!="0000"
            or not isinstance(j.get("msgArray"),list)):
        raise ValueError("MIS unsuccessful status or invalid response envelope")
    return j["msgArray"]

def quote_num(m,key):
    raw=str(m.get(key,"") or "")
    for part in raw.split("_"):
        v=num(part)
        if v is not None and v>0:return v
    return None

def mis_execution(m):
    """Return the price/time pair of an execution, never an order-book quote.

    MIS may send z="-" for a book update and retain the last execution in
    trade. Its own timestamp must travel with its price through every gate.
    """
    if not isinstance(m,dict):return None
    z=num(m.get("z"))
    if z is not None and z>0:return m
    if m.get("z") not in (None,"","-"):return None
    trade=m.get("trade")
    if not isinstance(trade,dict):return None
    price,volume=num(trade.get("z")),num(trade.get("v"))
    if price is None or price<=0 or volume is None or volume<=0:return None
    if trade.get("d",m.get("d"))!=m.get("d"):return None
    try:
        executed=datetime.strptime(str(trade.get("t","")),"%H:%M:%S").time()
        reported=datetime.strptime(str(m.get("t","")),"%H:%M:%S").time()
        if not (9<=executed.hour and (executed.hour,executed.minute,executed.second)<=(13,30,0)
                and executed<=reported):return None
    except (ValueError,TypeError):return None
    return {**m,"z":trade["z"],"t":trade["t"]}


def live_price(m):
    execution=mis_execution(m)
    return num(execution.get("z")) if execution is not None else None

def mis_service_probe(channels):
    """Bound a known service outage before starting a full-universe fan-out.

    Probe one symbol from each requested market. A successful or ambiguous
    response does not certify any price: the normal quote gates still apply.
    No state survives this invocation, so the next refresh always probes again.
    """
    probe=[]
    for prefix in ("tse_", "otc_"):
        sample=next((c for c in channels if c.startswith(prefix)), None)
        if sample:probe.append(sample)
    if not probe:return True,0,None
    for attempt in range(1,4):
        try:
            fetch_mis_channels(probe)
            return True,attempt,None
        except urllib.error.HTTPError as error:
            # Do not fan out on explicit denial/rate limits, or a persistent
            # service-unavailable response. Other failures retain old recovery.
            if error.code not in (403,429) and not 500<=error.code<600:
                return True,attempt,None
            if error.code in (403,429) or attempt==3:
                return False,attempt,error.code
        except (urllib.error.URLError,TimeoutError,ConnectionError):
            if attempt==3:return False,attempt,"network"
        except Exception:
            return True,attempt,None
        time.sleep(2**(attempt-1))

def recent_mis_time(message, asof):
    """Count only executed quotes within two five-minute refresh intervals."""
    try:
        message = mis_execution(message) or message
        stamp = datetime.strptime(str(message.get("d", "")) + " " + str(message.get("t", "")),
                                  "%Y%m%d %H:%M:%S").replace(tzinfo=TZ)
        seconds = (asof - stamp).total_seconds()
        return (stamp.hour >= 9 and (stamp.hour, stamp.minute, stamp.second) <= (13, 30, 0)
                and -60 <= seconds <= 600)
    except (ValueError, TypeError):
        return False

def mis_index_change(messages, asof):
    """Bind market risk to TAIEX identity, not response position or stock price."""
    if not isinstance(messages,list):return None,"invalid_response"
    if not messages:return None,"unavailable"
    matching=[m for m in messages if isinstance(m,dict) and
              m.get("c")=="t00" and m.get("ex")=="tse" and m.get("ch")=="t00.tw"]
    if not matching:return None,"identity_mismatch"
    current=[m for m in matching if m.get("d")==asof.strftime("%Y%m%d") and recent_mis_time(m,asof)]
    if not current:return None,"stale_or_invalid_time"
    values=set()
    for m in current:
        previous,price=num(m.get("y")),live_price(m)
        if previous is None or previous<=0 or price is None:
            return None,"invalid_price"
        values.add((m["d"],m["t"],previous,price))
    # Identical duplicates are harmless; differing timestamps or prices in a
    # one-channel response are ambiguous and cannot set market risk.
    if len(values)!=1:return None,"conflicting_quotes"
    _,_,previous,price=values.pop()
    change=(price-previous)/previous*100.0
    return (change,"verified") if math.isfinite(change) else (None,"invalid_price")

def mis_stock_identity(message, code, market):
    """Bind a stock quote to the exchange/channel requested for its official row."""
    exchange={"TWSE":"tse", "TPEX":"otc"}.get(market)
    return (isinstance(message,dict) and isinstance(code,str)
            and re.fullmatch(r"\d{4}",code) is not None and exchange is not None
            and message.get("c")==code and message.get("ex")==exchange
            and message.get("ch")==code+".tw")


def select_mis_retry_channels(messages, by_code, asof, priority_codes=(), omitted_codes=()):
    """Spend the existing 100-symbol retry budget on fresh, distinct symbols.

    Priority is public ticker membership only, never private position size or
    cost. Selection cannot validate a trade or bypass the normal quote gates.
    """
    priority={code for code in priority_codes if isinstance(code,str) and re.fullmatch(r"\d{4}",code)}
    candidates={}
    for message in messages:
        if not isinstance(message,dict):continue
        code=str(message.get("c", ""))
        row=by_code.get(code)
        if (not re.fullmatch(r"\d{4}",code) or not row
                or not mis_stock_identity(message,code,row.get("market"))
                or str(message.get("d", ""))!=asof.strftime("%Y%m%d")
                or not recent_mis_time(message,asof)):
            continue
        if live_price(message) is not None:
            # A usable-price duplicate needs no missing-price retry.
            candidates[code]=False
        elif (num(message.get("v")) or 0)>0 and code not in candidates:
            candidates[code]=True
    # A partial nonempty batch is not evidence that every requested symbol
    # was returned. Omitted symbols share, rather than expand, the retry budget.
    for code in omitted_codes:
        if (isinstance(code,str) and re.fullmatch(r"\d{4}",code)
                and by_code.get(code,{}).get("market") in ("TWSE","TPEX")
                and code not in candidates):
            candidates[code]=True
    codes=[code for code,missing in candidates.items() if missing]
    codes.sort(key=lambda code:code not in priority)  # stable within each group
    selected=codes[:100]
    return [(("tse_" if by_code[code]["market"]=="TWSE" else "otc_")+code+".tw")
            for code in selected],set(selected)&priority


def enrich_live(rows, asof=None, priority_codes=()):
    fixed_asof=asof is not None
    asof=asof or datetime.now(TZ)
    expected_day=asof.strftime("%Y%m%d")
    by_code={x["code"]:x for x in rows}
    channels=[]
    for x in rows:
        if (not re.fullmatch(r"\d{4}",x.get("code",""))
                or x.get("market") not in ("TWSE","TPEX")):continue
        prefix="tse_" if x.get("market")=="TWSE" else "otc_"
        channels.append(prefix+x["code"]+".tw")
    got=0;errors=[]
    stats={"requested_channels":len(channels),"returned_messages":0,"matched_codes":0,"rejected_date":0,"rejected_time":0,"duplicate_messages":0,"rejected_price":0,"missing_last_trade":0,"missing_previous_close":0,"index_quote_status":"not_requested","rejected_identity":0,"malformed_messages":0}
    available,attempts,status=mis_service_probe(channels)
    stats.update(service_probe_attempts=attempts,bulk_scan_skipped=not available,
                 unavailable_http_status=status if isinstance(status,int) else None,
                 outage_reason="network" if status=="network" else f"HTTP_{status}" if status else None,
                 skipped_channels=len(channels) if not available else 0)
    if not available:
        reason=f"HTTP {status}" if isinstance(status,int) else "network"
        errors.append(f"MIS {reason}：連線探測未通過，停止本輪全市場掃描；下輪重新探測")
        return rows,0,None,errors,stats
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
    # Live scans can span several minutes. Compare observations with the
    # collection clock, while explicit historical replay times stay frozen.
    if not fixed_asof:asof=datetime.now(TZ)
    stats["returned_messages"]=len(messages)
    stats["malformed_messages"]=sum(not isinstance(m,dict) for m in messages)
    messages=[m for m in messages if isinstance(m,dict)]
    # Retry at most 100 symbols showing volume but no last trade.
    incomplete=[m for m in messages if live_price(m) is None and
                (num(m.get("v")) or 0)>0 and
                str(m.get("c","")).isdigit() and len(str(m.get("c","")))==4]
    stats["incomplete_with_volume"]=len(incomplete)
    stats["retry_requested"]=0
    stats["retry_recovered"]=0
    returned_codes={str(m.get("c","")) for m in messages}
    requested_codes=[channel.split("_",1)[1][:-3] for channel in channels]
    omitted_codes=[code for code in requested_codes if code not in returned_codes]
    stats["omitted_symbols"]=len(omitted_codes)
    retry_channels,priority_retries=select_mis_retry_channels(
        messages,by_code,asof,priority_codes,omitted_codes=omitted_codes)
    stats["retry_requested"]=len(retry_channels)
    stats["priority_retry_requested"]=len(priority_retries)
    stats["priority_retry_recovered"]=0
    replacements={}
    requested_retry_codes={channel.split("_",1)[1][:-3] for channel in retry_channels}
    for j in range(0,len(retry_channels),20):
        try:
            for quote in fetch_mis_channels(retry_channels[j:j+20]):
                code=str(quote.get("c","")) if isinstance(quote,dict) else ""
                if (code in requested_retry_codes
                        and mis_stock_identity(quote,code,by_code[code].get("market"))
                        and live_price(quote) is not None):
                    replacements[str(quote.get("c",""))]=quote
        except Exception as exc:
            errors.append("MIS retry: "+str(exc)[:100])
    if replacements:
        messages=[replacements.get(str(m.get("c","")),m) for m in messages]
        messages.extend(replacements[code] for code in omitted_codes if code in replacements)
    if not fixed_asof:asof=datetime.now(TZ)
    stats["quotes_checked_at"]=asof.isoformat()
    accepted_codes=set()
    for m in messages:
        code=str(m.get("c","")).strip()
        x=by_code.get(code)
        if not x:continue
        stats["matched_codes"]+=1
        if not mis_stock_identity(m,code,x.get("market")):
            stats["rejected_identity"]+=1
            continue
        # MIS can return the prior session on holidays, before opening, or after outages.
        # Never overwrite official rows or count a quote without the exchange date for today.
        quote_day=re.sub(r"[^0-9]","",str(m.get("d","") or ""))
        # The last-trade time must also be a plausible current-session time.
        # A matching date alone can still refer to a stale cached MIS quote.
        quote_time=str(m.get("t","") or "").strip()
        try:
            hh,mm,ss=(int(v) for v in quote_time.split(":"))
            valid_trade_time=(9<=hh<=13 and 0<=mm<60 and 0<=ss<60
                              and (hh<13 or mm<=30))
        except (ValueError,TypeError):
            valid_trade_time=False
        if quote_day!=expected_day:
            stats["rejected_date"]+=1
            continue
        valid_trade_time=valid_trade_time and recent_mis_time(m, asof)
        if not valid_trade_time:
            stats["rejected_time"]+=1
            continue
        if code in accepted_codes:
            stats["duplicate_messages"]+=1
            continue
        prev=num(m.get("y"));price=live_price(m)
        if price is None or price<=0 or prev is None or prev<=0:
            stats["rejected_price"]+=1
            if price is None or price<=0:stats["missing_last_trade"]+=1
            if prev is None or prev<=0:stats["missing_previous_close"]+=1
            continue
        x["close"]=price;x["change"]=price-prev;x["pct"]=(price-prev)/prev*100.0
        o=num(m.get("o"));h=num(m.get("h"));l=num(m.get("l"));v=num(m.get("v"))
        if o and o>0:x["open"]=o
        if h and h>0:x["high"]=h
        if l and l>0:x["low"]=l
        if v is not None:
            x["live_volume"]=v
            if v>0:x["value"]=v*1000.0*price
        # MIS d/t are the exchange quote date/time; preserve them instead of using updater runtime.
        execution=mis_execution(m) or m
        qd=str(execution.get("d","") or "").strip(); qt=str(execution.get("t","") or "").strip()
        if qd and qt:
            x["quote_time"]=f"{qd[:4]}-{qd[4:6]}-{qd[6:8]} {qt}"
        elif qt:
            x["quote_time"]=qt
        x["live"]=True;got+=1;accepted_codes.add(code)
    # Count only replacements that survived the date/time/price gates above.
    recovered=set(replacements)&accepted_codes
    stats["retry_recovered"]=len(recovered)
    stats["priority_retry_recovered"]=len(recovered&priority_retries)
    taiex=None
    try:
        idx=fetch_mis_channels(["tse_t00.tw"])
        index_asof=asof if fixed_asof else datetime.now(TZ)
        stats["index_checked_at"]=index_asof.isoformat()
        taiex,stats["index_quote_status"]=mis_index_change(idx,index_asof)
    except Exception as e:
        stats["index_quote_status"]="request_failed"
        errors.append("TAIEX:"+str(e))
    return rows,got,taiex,errors,stats

def num(v):
    if v is None:return None
    s=str(v).strip().replace(",","").replace("+","")
    if s in ("","--","---","N/A","null"):return None
    try:
        value=float(s)
        return value if value==value and abs(value)!=float("inf") else None
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
            "close":close,"change":change,"pct":pct_from_change(close,change),"price_note":action_note(r.get("Change")),"volume":num(r.get("TradeVolume")) or 0,
            "value":num(r.get("TradeValue")) or 0,"market":"TWSE"}

def norm_tpex(r):
    close=num(pick(r,"Close","ClosingPrice"));change=num(pick(r,"Change","ChangeAmount"))
    return {"date":str(pick(r,"Date") or "").strip(),"code":str(pick(r,"SecuritiesCompanyCode","Code","SecuritiesCode") or "").strip(),
            "name":str(pick(r,"CompanyName","SecuritiesCompanyName","Name") or "").strip(),
            "open":num(pick(r,"Open","OpeningPrice")),"high":num(pick(r,"High","HighestPrice")),"low":num(pick(r,"Low","LowestPrice")),
            "close":close,"change":change,"pct":pct_from_change(close,change),"price_note":action_note(pick(r,"Change","ChangeAmount")),
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

def official_close_observations(rows,day):
    """Raw dated closes remain valid when an ex-rights note replaces change."""
    if verified_archive_date(day) is None:raise ValueError('Invalid official close day')
    prices={};events={}
    for row in rows:
        if (not isinstance(row,dict) or row.get('market') not in ('TWSE','TPEX')
                or row.get('live') is True or normalize_exchange_date(row.get('date'))!=day):continue
        code=row.get('code');raw=row.get('close')
        if (not isinstance(code,str) or not re.fullmatch(r'[1-9][0-9]{3}',code)
                or isinstance(raw,bool)):continue
        price=num(raw)
        if price is None or price<=0:continue
        price=round(price,4)
        if code in prices and prices[code]!=price:raise ValueError('Conflicting official close '+code)
        prices[code]=price
        note=action_note(row.get('price_note'))
        if note:
            if code in events and events[code]!=note:raise ValueError('Conflicting corporate action '+code)
            events[code]=note
    return prices,events

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

SELECTION_POLICY = "jei-user-radar-gates-v1"


def next_setup_score(stock, sector_score, heat_penalty):
    return round(clamp(sector_score*.42+position(stock)*100*.28+
                       clamp((math.log10(max(stock.get("value",1),1))-7)*12,0,100)*.18+
                       (100-min(100,heat_penalty*5))*.12,0,99))


def qualified_radar_rows(pool, mode, limit=10):
    """Apply the user's fixed eligibility gates BEFORE taking ranked slots.

    Input order is the existing score/value ranking. No backfill below the
    thresholds, no rescore and no change to historical signals.
    """
    if mode not in ("attack", "next"):
        raise ValueError("unsupported formal radar group")
    result=[]
    for row in pool:
        score,stock,sector,sector_score,r5,r10,r20,heat_penalty=row
        if (isinstance(score,bool) or not isinstance(score,(int,float)) or
                not math.isfinite(score) or not 0<=score<=99):
            continue
        if score < (85 if mode=="attack" else 80):
            continue
        if mode=="next" and next_setup_score(stock,sector_score,heat_penalty)<80:
            continue
        result.append(row)
        if len(result)>=limit:
            break
    return result


def item(s,score,reason,mode,risk,sector,sector_score):
    sector_label="族群未分類" if sector=="未分類" else (sector or "族群未分類")
    x={"code":s["code"],"name":s["name"],"score":score,"reason":reason,"price":s["close"],
       "change_pct":round(s["pct"],2),"market":s["market"],"sector":sector_label,"sector_score":sector_score}
    x.update(price_plan(s,mode,risk))
    return x

def attach_financial_context(rows, snapshot, as_of):
    """Add dated public financial context without changing technical ranks.

    Only the latest monthly revenue and quarterly statement already published
    by the market date are exposed. These fields are display context, not score
    inputs or historical backtest features.
    """
    try:
        cutoff=datetime.strptime(str(as_of),"%Y-%m-%d").date()
    except (TypeError,ValueError):
        return
    if not isinstance(snapshot,dict) or snapshot.get("schemaVersion") != 1:
        return
    markets=snapshot.get("markets")
    if not isinstance(markets,dict):
        return
    def record_for(code):
        for market in ("listed","otc"):
            table=markets.get(market)
            record=table.get(code) if isinstance(table,dict) else None
            if isinstance(record,dict):
                return record,market
        return {},None
    def valid_date(value, max_age_days):
        try:
            day=datetime.strptime(str(value),"%Y-%m-%d").date()
        except (TypeError,ValueError):
            return None
        age=(cutoff-day).days
        # Publication data has day-level precision only. A report dated on the
        # signal day might have appeared after the close, so require a prior day.
        return day if 0 < age <= max_age_days else None
    def valid_month(value):
        try:
            day=datetime.strptime(str(value),"%Y-%m-%d").date()
        except (TypeError,ValueError):
            return None
        age=(cutoff-day).days
        return day if day.day==1 and 0 <= age <= 120 else None
    def valid_quarter(value):
        match=re.fullmatch(r"(\d{4})-Q([1-4])",str(value or ""))
        if not match:
            return False
        year,quarter=map(int,match.groups())
        quarter_end_month=quarter*3
        return (year,quarter_end_month) <= (cutoff.year,cutoff.month)
    def pct(value):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            return None
        return f"{value:+.1f}%"
    for row in rows:
        if not isinstance(row,dict):
            continue
        previous_context=row.get("financial_context")
        reason=str(row.get("reason") or "")
        if isinstance(previous_context,dict) and isinstance(previous_context.get("text"),str):
            reason=reason.replace("｜"+previous_context["text"],"")
        code=str(row.get("code") or "").strip().upper()
        record,market=record_for(code) if code else ({},None)
        revenue=record.get("revenue") if isinstance(record.get("revenue"),dict) else {}
        financials=record.get("financials") if isinstance(record.get("financials"),dict) else {}
        sources=snapshot.get("sources") if isinstance(snapshot.get("sources"),dict) else {}
        prefix={"listed":"twse","otc":"tpex"}.get(market)
        official_sources={
            "revenue":f"{prefix}Revenue" if prefix else None,
            "income":f"{prefix}Income" if prefix else None,
            "balance":f"{prefix}Balance" if prefix else None,
        }
        expected_hosts={"listed":"https://openapi.twse.com.tw/v1/","otc":"https://www.tpex.org.tw/openapi/v1/"}
        def verified_source(key):
            source_key=official_sources.get(key)
            value=sources.get(source_key) if source_key else None
            return value if isinstance(value,str) and value.startswith(expected_hosts.get(market,"!")) else None
        revenue_date=valid_date(revenue.get("publishedAt"),60)
        statement_date=valid_date(financials.get("publishedAt"),180)
        revenue_period=valid_month(revenue.get("period"))
        statement_period=valid_quarter(financials.get("period"))
        parts=[]
        revenue_included=False
        statement_included=False
        revenue_source=verified_source("revenue")
        if revenue_date and revenue_period and revenue_source:
            period=revenue_period.strftime("%Y-%m")
            yoy=pct(revenue.get("monthlyYoYPct"))
            mom=pct(revenue.get("monthlyMoMPct"))
            if period and (yoy or mom):
                parts.append(f"月營收 {period} 公告 {revenue_date.isoformat()}"+ (f" YoY {yoy}" if yoy else "") + (f"／MoM {mom}" if mom else ""))
                revenue_included=True
        income_source=verified_source("income")
        balance_source=verified_source("balance")
        if statement_date and statement_period and income_source and balance_source:
            period=str(financials.get("period") or "")
            eps=financials.get("eps")
            gross=financials.get("grossMarginPct")
            debt=financials.get("debtRatioPct")
            metrics=[]
            if isinstance(eps,(int,float)) and not isinstance(eps,bool) and math.isfinite(eps):
                metrics.append(f"EPS {eps:.2f}")
            if isinstance(gross,(int,float)) and not isinstance(gross,bool) and math.isfinite(gross):
                metrics.append(f"毛利率 {gross:.1f}%")
            if isinstance(debt,(int,float)) and not isinstance(debt,bool) and math.isfinite(debt):
                metrics.append(f"負債率 {debt:.1f}%")
            if period and metrics:
                parts.append(f"季報 {period} 公告 {statement_date.isoformat()} " + "、".join(metrics))
                statement_included=True
        if parts:
            text="；".join(parts)+"（官方公開財務資料；僅供基本面參考，不納入現行技術分數／回測）"
            row["financial_context"]={
                "status":"verified","as_of":cutoff.isoformat(),
                "snapshot_generated_at":snapshot.get("generatedAt"),
                "publication_dates":{"revenue":revenue_date.isoformat() if revenue_included else None,
                                     "financials":statement_date.isoformat() if statement_included else None},
                "periods":{"revenue":revenue_period.strftime("%Y-%m") if revenue_included else None,
                           "financials":financials.get("period") if statement_included else None},
                "availability":financials.get("availability") if statement_included else None,
                "sources":{"revenue":revenue_source if revenue_included else None,
                           "income":income_source if statement_included else None,
                           "balance":balance_source if statement_included else None},
                "text":text,
            }
        else:
            text="財務資料未驗證，不影響現行技術排名"
            row["financial_context"]={"status":"unverified","as_of":cutoff.isoformat(),"text":text}
        row["reason"]=(reason+"｜" if reason else "")+text

def load_recent_financial_snapshot(as_of, path=Path("remote/free_research.json")):
    """Load only a recent public snapshot that is not newer than the quote date."""
    try:
        snapshot=json.loads(path.read_text(encoding="utf-8"))
        generated_day=datetime.strptime(str(snapshot.get("generatedAt") or "")[:10],"%Y-%m-%d").date()
        cutoff_day=datetime.strptime(str(as_of),"%Y-%m-%d").date()
        if (snapshot.get("schemaVersion")==1
                and 0 <= (cutoff_day-generated_day).days <= 3
                and isinstance(snapshot.get("markets"),dict)):
            return snapshot
    except (OSError,ValueError,TypeError,AttributeError):
        pass
    return {}

def sector_evidence(sector,score):
    # 50 is the neutral model input when the stock is outside our tracked baskets;
    # it is not measured sector heat and must not be presented as such.
    if sector=="未分類":
        return "族群資料未涵蓋（中性計分）"
    return f"{sector}熱度 {score}"

def load_history():
    try:
        h=json.loads(HISTORY.read_text(encoding="utf-8"))
        return h if isinstance(h,list) else []
    except Exception:return []

def retained_intraday_snapshot(previous, now, diagnostics):
    """Retain a same-day verified sample as stale research, never as fresh quotes."""
    if (not isinstance(previous,dict) or previous.get("schema")!=4
            or now.tzinfo is None or not is_safe_public_holdings(previous.get("holdings"))):
        return None
    market=previous.get("market");risk=previous.get("risk")
    if not isinstance(market,dict) or not isinstance(risk,dict):return None
    local=now.astimezone(TZ)
    try:
        stamp=datetime.strptime(previous["updated_at"],"%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    except (KeyError,TypeError,ValueError):return None
    day=local.date().isoformat()
    if (previous.get("data_date")!=day or stamp.date()!=local.date() or stamp>local
            or not 540<=stamp.hour*60+stamp.minute<810 or risk.get("as_of")!=day
            or isinstance(risk.get("score"),bool) or num(risk.get("score")) is None
            or not 0<=num(risk["score"])<=100):return None
    marker=market.get("retained_intraday_snapshot")
    if market.get("mode")=="盤中即時" and market.get("live_valid") is True and market.get("stale") is False:
        marker={"kind":"intraday","data_date":day,"updated_at":previous["updated_at"],
                "live_count":market.get("live_count"),"close_count":market.get("close_count"),
                "live_coverage_pct":market.get("live_coverage_pct")}
    elif not (market.get("mode")=="資料過期" and market.get("stale") is True
              and market.get("historical_readonly") is True and market.get("no_new_picks") is True
              and market.get("live_valid") is False and risk.get("actionable") is False
              and isinstance(marker,dict) and marker.get("kind")=="intraday"
              and marker.get("data_date")==day and marker.get("updated_at")==previous["updated_at"]):
        return None
    values=[marker.get(k) for k in ("live_count","close_count","live_coverage_pct")]
    if any(isinstance(v,bool) or num(v) is None for v in values):return None
    count,total,coverage=map(float,values)
    if not (500<=count<=total and 35<=coverage<=100 and count/total>=.35
            and abs(coverage-100*count/total)<=.15):return None
    if not all(isinstance(previous.get(k),list) for k in ("attack","next","sectors")):return None
    out=json.loads(json.dumps(previous,allow_nan=False))
    checked=local.strftime("%Y-%m-%d %H:%M")
    after_close=diagnostics.get("market_open") is False
    session="盤後資料待齊" if after_close else "盤中更新失敗"
    reason=("雙市場同日官方收盤未通過驗證；保留原盤中快照，暫停新判讀" if after_close
            else "本次成交資料未通過驗證；保留原盤中快照，暫停新判讀")
    out["market"].update(mode="資料過期",stale=True,historical_readonly=True,
        live_valid=False,live_count=diagnostics.get("valid_trades",0),
        live_coverage_pct=diagnostics.get("coverage_pct",0),no_new_picks=True,
        status_updated_at=checked,last_checked_at=checked,session_status=session,
        session_reason=reason,
        retained_intraday_snapshot=dict(marker),live_diagnostics=dict(diagnostics),partial_live=None,
        brief=f"{session}｜保留 {previous['updated_at']} 已驗證快照；非目前行情，暫停新判讀")
    out["risk"].update(actionable=False,cash="暫停判讀",label="保留已驗證風險（快照過期）")
    out["market"]["analysis_scope"]={"mode":"retained_intraday_sample","count":int(count),
        "universe_count":int(total),"as_of":previous["updated_at"]}
    event="雙市場收盤資料未齊" if after_close else "本次盤中更新未通過"
    out["summary"]=f"{checked} {event}；保留 {previous['updated_at']} 已驗證快照，不重算風險或新選股。"
    return out


def validated_previous_close(previous, now, max_age_days=7):
    """Keep a verified official close available for read-only research after the session.

    Preserve the ORIGINAL trading date and verification timestamp. Never re-label
    an old snapshot as today's live market or create a fake history candle.
    """
    if not isinstance(previous, dict) or now.tzinfo is None:
        return None
    market=previous.get("market")
    if (not isinstance(market, dict) or market.get("mode") not in ("今日收盤","最近收盤")
            or (market.get("stale") is not False and market.get("historical_readonly") is not True)
            or isinstance(market.get("close_count"), bool)
            or not isinstance(market.get("close_count"), (int,float))
            or market["close_count"] < 500):
        return None
    if not is_safe_public_holdings(previous.get("holdings")):
        return None
    try:
        verified_day=datetime.strptime(previous["data_date"], "%Y-%m-%d").date()
        stamp=datetime.strptime(previous["updated_at"], "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    except (KeyError,TypeError,ValueError):
        return None
    now=now.astimezone(TZ)
    lag_days=(now.date()-verified_day).days
    if not 0<=lag_days<=max_age_days:
        return None
    if stamp.date()!=verified_day and market.get("historical_readonly") is not True:
        return None
    if stamp.hour*60+stamp.minute < 13*60+30 or stamp>now:
        return None
    if not isinstance(previous.get("attack"),list) or not isinstance(previous.get("sectors"),list):
        return None
    # Old snapshots are never counted as live trades on the new calendar day.
    out=dict(previous)
    out["market"]={**market,"stale":verified_day!=now.date(),"historical_readonly":verified_day!=now.date(),
                   "last_checked_at":now.strftime("%Y-%m-%d %H:%M")}
    if verified_day!=now.date():
        # Every consumer of a retained snapshot must see the same read-only
        # contract, including Android clients that inspect risk.actionable.
        out["market"].update(mode="最近收盤", live_valid=False, no_new_picks=True,
                             market_data_as_of=previous["data_date"],
                             session_status="歷史唯讀",
                             brief=f"最近有效收盤 {previous['data_date']}｜歷史參考，非今日訊號；暫停新選股")
        out["risk"]={**(previous.get("risk") or {}),"actionable":False,
                     "as_of":previous["data_date"]}
        out["summary"]=f"保留 {previous['data_date']} 歷史收盤資料；本次即時行情尚未驗證，暫停今日評分及新選股。"
    return out

def refresh_public_etf_references(previous, official_by_code, as_of):
    """Refresh only already-public ETFs from a matching official daily row.

    Keep ETFs outside stock ranking, history candles and paper trades. A dated
    close is evidence of price only, never evidence for a technical score.
    """
    if not is_safe_public_holdings(previous):
        raise ValueError("Public holdings contain disallowed private fields")
    out={code:dict(value) for code,value in (previous or {}).items()}
    if verified_archive_date(as_of) is None or not isinstance(official_by_code,dict):
        return out
    for code, prior in (previous or {}).items():
        if not re.fullmatch(r"0(?:[0-9]{3}|[0-9]{4}[A-Z])",code):
            continue
        row=official_by_code.get(code)
        if (not isinstance(row,dict) or row.get("code")!=code
                or row.get("market") not in ("TWSE","TPEX") or row.get("live") is True
                or verified_archive_date(normalize_exchange_date(row.get("date")))!=as_of):
            continue
        if verified_archive_date(prior.get("as_of")) and prior["as_of"]>as_of:
            continue
        price=num(row.get("close"))
        if isinstance(row.get("close"),bool) or price is None or not 0<price<1000000:
            continue
        source="TWSE" if row["market"]=="TWSE" else "TPEx"
        out[code]={"score":None,"trend":("債券ETF" if code.endswith("B") else "ETF")+"／技術資料不足",
                   "action":"收盤參考","defense":None,"target":None,
                   "reason":f"{as_of} {source}官方收盤{price:g}元；尚未驗證ETF技術評分、防守或目標價。",
                   "as_of":as_of,"status":"官方收盤參考"}
    return out


def update_history(history,date_key,stocks,signals,institutional_market=None):
    price_map={x["code"]:x["close"] for x in stocks if x.get("close")}
    snap={"date":date_key,"prices":price_map,"signals":[{"code":x["code"],"price":x["price"],"score":x["score"]} for x in signals[:8]]}
    if institutional_market:snap["institutional_market"]=institutional_market
    else:
        previous=next((x.get("institutional_market") for x in history if x.get("date")==date_key),None)
        if isinstance(previous,dict) and previous.get("verified") is True and previous.get("data_date")==date_key:
            snap["institutional_market"]=previous
    history=[x for x in history if x.get("date")!=date_key]
    history.append(snap)
    history=history[-90:]
    return history

def calc_backtest(history,current_prices):
    periods=[(3,"hit3"),(5,"hit5"),(10,"hit10")]
    out={"hit3":None,"hit5":None,"hit10":None,"samples":0,
         "validation":{
             "status":"insufficient_evidence", "threshold_80_met":False,
             "qualified_oos_closed_trades":0,
             "hit_definition":"gross close return >= 3%; not net profitable closed trades",
             "costs_included":False, "slippage_included":False,
             "walk_forward_verified":False, "market_regimes_verified":False,
             "note":"舊hit欄位僅為收盤漲幅觀察，不能作80%樣本外勝率證據；正式紀錄見pick_validation.json及strategy_performance.json"
         }}
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

def load_previous_risk(path=OUT):
    """Read the last composite risk defensively; recover the parent snapshot if current JSON is damaged."""
    if not path.exists():
        return {}, None
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(current, dict):
            raise ValueError("current market feed is not an object")
        risk = current.get("risk") or {}
        if not isinstance(risk, dict):
            raise ValueError("current market risk is not an object")
        return risk, None
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as current_error:
        try:
            relative = path.as_posix()
            previous = subprocess.run(
                ["git", "show", f"HEAD^:{relative}"],
                check=True, capture_output=True, text=True, timeout=10,
            )
            restored = json.loads(previous.stdout)
            risk = restored.get("risk") if isinstance(restored, dict) else None
            if not isinstance(risk, dict):
                raise ValueError("parent market risk is unavailable")
            return risk, "前一版行情摘要無法解析；已從上一個 Git 版本復原風險欄位"
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError, TypeError) as recovery_error:
            detail = type(current_error).__name__ + "/" + type(recovery_error).__name__
            return {}, "前一版行情摘要與 Git 備份都無法解析（" + detail + "）；本次風險僅依新行情重算"


def fetch_initial_market_sources(errors):
    """Overlap independent hosts; retain deterministic source order and failures."""
    sources=((TWSE_STOCK,"TWSE股票"),(TWSE_INDEX,"TWSE指數"),(TPEX_STOCK,"TPEX"))
    results=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending=[pool.submit(fetch_json,url) for url,_ in sources]
        for future,(_,label) in zip(pending,sources):
            try:results.append(future.result())
            except Exception as exc:
                results.append([])
                errors.append(label+":"+str(exc))
    return tuple(results)


def main():
    errors=[]
    twse_raw,idx_raw,tpex_raw=fetch_initial_market_sources(errors)

    rows=[norm_twse(x) for x in twse_raw if isinstance(x,dict)]+[norm_tpex(x) for x in tpex_raw if isinstance(x,dict)]
    rows=[x for x in rows if x["code"] and x["close"]]

    now=datetime.now(TZ)
    today_iso=now.strftime("%Y-%m-%d")
    previous_data_date=None
    previous_feed={}
    try:
        previous_feed=json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
        candidate_date=previous_feed.get("data_date") if isinstance(previous_feed,dict) else None
        if isinstance(candidate_date,str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}",candidate_date):
            previous_data_date=candidate_date
    except (OSError,ValueError,TypeError):
        pass
    rows,offhours_close=fetch_latest_offhours_close(rows,now,previous_data_date)
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
    # TPEx OpenAPI can be CDN-cached on cloud runners. If its date lags today,
    # force a cache-busted refetch before treating the whole feed as stale.
    tpex_source_dates={re.sub(r"[^0-9]","",str(x.get("date",""))) for x in rows if x.get("market")=="TPEX" and x.get("date")}
    if now.weekday()<5 and today_roc not in tpex_source_dates and today_ymd not in tpex_source_dates:
        try:
            sep="&" if "?" in TPEX_STOCK else "?"
            fresh_tpex_raw=fetch_json(TPEX_STOCK+sep+"_="+str(int(time.time())))
            fresh_tpex=[norm_tpex(x) for x in fresh_tpex_raw if isinstance(x,dict)]
            fresh_tpex=[x for x in fresh_tpex if x.get("code") and x.get("close")]
            fresh_dates={re.sub(r"[^0-9]","",str(x.get("date",""))) for x in fresh_tpex if x.get("date")}
            if fresh_tpex and (today_roc in fresh_dates or today_ymd in fresh_dates):
                fresh_codes={x["code"] for x in fresh_tpex}
                rows=[x for x in rows if not (x.get("market")=="TPEX" and x.get("code") in fresh_codes)]+fresh_tpex
                errors.append(f"TPEx OpenAPI快取落後，已強制重抓 {len(fresh_tpex)} 檔")
        except Exception as e:errors.append("TPEx當日補資料:"+str(e))

    # Freeze official source prices before MIS can mutate normalized rows.
    official_prices,official_actions=official_close_observations(rows,today_iso)
    live_count=0;live_errors=[];taiex_live=None;live_stats={}
    # Session classification and quote collection are different: do not call final MIS
    # snapshots a live trading session after 13:30, and never trust an old quote date.
    minutes=now.hour*60+now.minute
    # Weekdays are only potential sessions: a typhoon closure or holiday must
    # also pass the exchange-date checks below before quotes become actionable.
    known_closure=closure_reason(now.date())
    market_open=not known_closure and now.weekday()<5 and 540<=minutes<810
    # Executions later than 13:30 are rejected, and quotes older than 600s
    # are rejected. After the 13:40 minute no MIS execution can qualify;
    # keep refreshing official closes without a futile full-universe scan.
    quote_refresh_window=not known_closure and now.weekday()<5 and 525<=minutes<821
    post_close_refresh=not known_closure and now.weekday()<5 and 840<=minutes<960
    if quote_refresh_window:
        try:
            public_tracked=previous_feed.get("holdings",{}) if isinstance(previous_feed,dict) else {}
            rows,live_count,taiex_live,live_errors,live_stats=enrich_live(
                rows,priority_codes=public_tracked if isinstance(public_tracked,dict) else ())
        except Exception as e:live_errors.append(str(e))
        if live_errors and live_count<100:errors.append("MIS盤中:"+(";".join(live_errors))[:120])

    stocks=[x for x in rows if stock_only(x)]
    by_code={x["code"]:x for x in stocks}
    # Coverage certifies a sample, not every official row. Keep stale closes
    # for archives/universe only; never mix them into today's risk or picks.
    analysis_stocks=[x for x in stocks if x.get("live") is True] if market_open else stocks
    analysis_by_code={x["code"]:x for x in analysis_stocks}
    holdings_by_code={x["code"]:x for x in rows if x.get("code")}
    institutional,inst_errors,inst_debug=fetch_institutional(today_iso)
    institutional={k:v for k,v in institutional.items() if k in by_code}
    inst_complete=institutional_market_complete(institutional,inst_errors,today_iso)
    if not inst_complete: errors.append("法人籌碼:雙市場同日資料不完整，停用全市場法人評分與趨勢")
    if inst_errors: errors.extend(inst_errors)
    if not institutional: errors.append("法人籌碼:官方資料暫無有效逐檔資料，已停用法人判讀")

    taiex_pct=None;taiex_source=None
    # Prefer the same-day official MI_INDEX summary when the daily OpenAPI index feed lags.
    if now.weekday()<5:
        try:
            ij=fetch_json(TWSE_DAILY+"?"+urllib.parse.urlencode({"date":today_ymd,"type":"ALL","response":"json"}))
            taiex_pct=twse_daily_index_pct(ij,today_ymd)
            if taiex_pct is not None:taiex_source="TWSE MI_INDEX dated response"
        except Exception as e:errors.append("TWSE當日指數:"+str(e))
    if taiex_pct is None:
        taiex_pct=twse_openapi_index_pct(idx_raw,today_iso)
        if taiex_pct is not None:taiex_source="TWSE OpenAPI MI_INDEX"
    if taiex_live is not None:taiex_pct=taiex_live;taiex_source="TWSE MIS validated quote"
    if taiex_pct is None:errors.append("TWSE指數缺少同日有效資料；不使用舊日漲跌幅")

    pcts=[x["pct"] for x in analysis_stocks if x["pct"] is not None]
    adv=sum(1 for p in pcts if p>0);dec=sum(1 for p in pcts if p<0);flat=max(0,len(pcts)-adv-dec)
    adv_ratio=adv/max(1,adv+dec);median=statistics.median(pcts) if pcts else 0
    down3=sum(1 for p in pcts if p<=-3);down5=sum(1 for p in pcts if p<=-5);limit_down=sum(1 for p in pcts if p<=-9.4)
    up5=sum(1 for p in pcts if p>=5);up8=sum(1 for p in pcts if p>=8)

    # Institutional breadth: use direction across the whole stock universe, not a single stock.
    inst_vals=[num(v.get("total")) for v in institutional.values()] if inst_complete else []
    inst_vals=[x for x in inst_vals if x is not None]
    inst_sell=sum(1 for x in inst_vals if x<0); inst_buy=sum(1 for x in inst_vals if x>0)
    inst_sell_ratio=inst_sell/max(1,inst_sell+inst_buy)
    inst_total=sum(inst_vals) if inst_vals else 0

    hist_before=load_history()
    prev_inst=[x.get("institutional_market",{}) for x in hist_before[-5:] if x.get("institutional_market",{}).get("verified") is True and x.get("date","")<today_iso]
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

    # JEI composite-risk guard:
    # The scheduled local-market model is only a partial model. It must not downgrade
    # a newer/manual composite alert that includes foreign futures, margin leverage,
    # high-beta behavior and US/SOX external risk unless those inputs are also present.
    # This prevents a partial refresh from overwriting an orange/red composite warning.
    previous_risk, previous_risk_warning = load_previous_risk()
    if previous_risk_warning:
        errors.append(previous_risk_warning)
    previous_score = int(previous_risk.get("score") or 0)
    previous_level = str(previous_risk.get("level") or "").lower()
    composite_fields = ("foreign_cash_billion","foreign_futures_net","margin_balance","external_risk")
    previous_is_composite = previous_level in ("orange","red") and any(k in previous_risk for k in composite_fields)
    if previous_is_composite and risk < previous_score:
        risk = previous_score

    if risk>=80:level,label,cash="red","高風險防守","70%↑"
    elif risk>=65:level,label,cash="orange",("內部轉弱警戒" if divergence else "風險升高"),"50%–70%"
    elif risk>=45:level,label,cash="yellow",("權值撐盤警戒" if divergence else "震盪警戒"),"30%–50%"
    else:level,label,cash="green","正常","20%–30%"

    sectors,stock_sector,sector_scores=build_sector_stats(analysis_by_code)
    tradable=[x for x in analysis_stocks if x["value"]>=30000000]

    def secinfo(s):
        sec=stock_sector.get(s["code"],"未分類")
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
    for score,s,sec,ss,r5,r10,r20,hp in qualified_radar_rows(attack_pool,"attack"):
        chase="｜接近漲停，勿追高" if s["pct"]>=8.5 else ""
        reason=f"{sector_evidence(sec,ss)}｜漲幅 {s['pct']:.2f}%｜收盤位置 {position(s)*100:.0f}%｜成交值 {s['value']/1e8:.1f} 億{chase}"
        attack.append(item(s,score,reason,"attack",risk,sec,ss))

    attack_codes={x["code"] for x in attack[:5]}
    next_pool=[x for x in next_pool if x[1]["code"] not in attack_codes]
    next_pool.sort(key=lambda x:(x[0],x[1]["value"]),reverse=True)
    next_list=[]
    for score,s,sec,ss,r5,r10,r20,hp in qualified_radar_rows(next_pool,"next"):
        setup=next_setup_score(s,ss,hp)
        reason=f"準備發動 {setup}分｜{sector_evidence(sec,ss)}｜今日 {s['pct']:+.2f}%｜5日 {fmt_ret(r5)}｜10日 {fmt_ret(r10)}｜成交值 {s['value']/1e8:.1f}億｜"+("低過熱" if hp<4 else "過熱降權")
        next_list.append(item(s,score,reason,"next",risk,sec,ss))

    monster_pool.sort(key=lambda x:(x[0],x[1]["pct"],x[1]["value"]),reverse=True)
    monster=[]
    for score,s,sec,ss,r5,r10,r20,hp in monster_pool[:10]:
        phase="異常資金提前卡位" if s["pct"]<5 else "強勢加速"
        reason=f"{phase}｜{sector_evidence(sec,ss)}｜今日 {s['pct']:+.2f}%｜5日 {fmt_ret(r5)}｜成交值 {s['value']/1e8:.1f}億｜收盤位置 {position(s)*100:.0f}%｜"+("低過熱" if hp<4 else "過熱警戒")
        monster.append(item(s,score,reason,"monster",risk,sec,ss))

    # 明日妖股：偏重「尚未完全噴出、收盤強、量能足、族群不弱」的隔日爆發候選。
    tomorrow_pool=[]
    for base,s,sec,ss,r5,r10,r20,hp in next_pool[:60]:
        if s["pct"] < 0.3 or s["pct"] > 5.8: continue
        if position(s) < .68 or s.get("value",0) < 100000000: continue
        if ss < 48 or hp >= 14: continue
        close_bonus=(position(s)-.68)*28
        sector_bonus=max(0,ss-50)*.22
        momentum_bonus=max(0,s["pct"])*1.6
        score=int(round(clamp(base+close_bonus+sector_bonus+momentum_bonus-hp*.45,0,99)))
        tomorrow_pool.append((score,s,sec,ss,r5,r10,r20,hp))
    tomorrow_pool.sort(key=lambda x:(x[0],x[1]["value"]),reverse=True)
    tomorrow_monster=[]
    for score,s,sec,ss,r5,r10,r20,hp in tomorrow_pool[:10]:
        reason=f"隔日爆發候選｜{sector_evidence(sec,ss)}｜今日 {s['pct']:+.2f}%｜5日 {fmt_ret(r5)}｜10日 {fmt_ret(r10)}｜收盤位置 {position(s)*100:.0f}%｜成交值 {s['value']/1e8:.1f}億｜"+("低過熱" if hp<4 else "控追價")
        tomorrow_monster.append(item(s,score,reason,"next",risk,sec,ss))

    # 未來妖股：找 1~4 週題材/族群仍有延伸性、但短線尚未過熱的提前觀察名單。
    future_pool=[]
    for s in tradable:
        sec,ss=secinfo(s)
        if ss < 50 or s["pct"] < -3.0 or s["pct"] > 6.5 or position(s) < .42: continue
        r5,r10,r20,hp=recent_heat(s)
        if hp >= 18: continue
        mom5=0 if r5 is None else clamp(r5,-8,16)
        mom10=0 if r10 is None else clamp(r10,-12,24)
        mom20=0 if r20 is None else clamp(r20,-18,35)
        liq=clamp((math.log10(max(s.get("value",1),1))-7.5)*5,0,18)
        score=44+(ss-45)*.42+position(s)*13+liq+mom5*.45+mom10*.28+mom20*.12-hp*.55-risk*.05
        future_pool.append((int(round(clamp(score,0,99))),s,sec,ss,r5,r10,r20,hp))
    future_pool.sort(key=lambda x:(x[0],x[1]["value"]),reverse=True)
    future_monster=[]
    for score,s,sec,ss,r5,r10,r20,hp in future_pool[:12]:
        reason=f"1–4週價量潛力觀察｜{sector_evidence(sec,ss)}｜今日 {s['pct']:+.2f}%｜5日 {fmt_ret(r5)}｜10日 {fmt_ret(r10)}｜20日 {fmt_ret(r20)}｜成交值 {s['value']/1e8:.1f}億｜"+("低過熱" if hp<4 else "控制追價")
        future_monster.append(item(s,score,reason,"next",risk,sec,ss))

    # Transparent outside-industry research is context, never an unearned stock
    # upgrade or proof of company revenue/orders. Keep technical scores intact.
    try:
        research=json.loads(Path("remote/industry_research.json").read_text(encoding="utf-8"))
        published=datetime.strptime(str(research.get("as_of","")),"%Y-%m-%d").date()
        if (research.get("mode")!="dated_industry_primary_source_evidence"
                or not 0 <= (now.date()-published).days <= 30):
            research={}
    except (OSError, ValueError, TypeError):
        research={}
    themes=research.get("themes") if isinstance(research.get("themes"),dict) else {}
    for x in future_monster:
        evidence=themes.get(x["sector"]) or {}
        institutions=evidence.get("institutions") or []
        independent=int(evidence.get("independent_institutions") or 0)
        if independent>=2:
            research_label="產業研究雙機構以上佐證；個股營收/估值未驗證"
        elif independent==1:
            research_label="單一研究機構產業展望；不足以稱為共識"
        else:
            research_label="尚無足夠產業研報佐證"
        x["research_status"]=research_label
        x["research_independent_sources"]=independent
        x["research_institutions"]=institutions[:5]
        x["research_only"]=True

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
    if market_open:reasons.insert(0,f"已驗證盤中樣本 {len(analysis_stocks)}/{len(stocks)}；廣度、族群與候選只使用此樣本")
    if inst_vals:
        reasons.append(f"法人偏賣 {inst_sell_ratio*100:.1f}%｜淨額 {inst_total/1000:+,.0f}張｜已驗證歷史 {len(prev_sell)} 日")
        if inst_withdrawal:reasons.append("法人連續撤退警訊：3日偏賣率高檔且惡化")
    if sectors:reasons.append("最強族群 "+sectors[0]["name"]+f" {sectors[0]['score']}分")
    if errors:reasons.append("部分資料源降級："+"；".join(errors)[:140])

    flow=[
        {"icon":"↗","name":"市場廣度","note":f"上漲 {adv} / 下跌 {dec}｜廣度 {adv_ratio*100:.1f}%","score":round(adv_ratio*100)},
        {"icon":"⚠","name":"尾端賣壓","note":f"跌逾3% {down3}｜跌逾5% {down5}｜跌停附近 {limit_down}","score":down5},
        {"icon":"🔥","name":"強勢動能","note":f"漲逾5% {up5}｜漲逾8% {up8}","score":up5},
        {"icon":"◎","name":"市場中位數","note":"排除權值股後觀察整體溫度","score":round(median,2)},
        {"icon":"🏦","name":"法人籌碼廣度","note":(f"偏賣 {inst_sell_ratio*100:.1f}%｜合計 {inst_total/1000:+,.0f}張" if inst_complete else "雙市場同日法人資料不完整，暫停判讀"),"score":round(inst_sell_ratio*100,1) if inst_complete else None}
    ]

    priority=[{"title":"市場風控","note":"｜".join(reasons[:4]),"action":label}]
    if sectors:priority.append({"title":"族群主線："+sectors[0]["name"],"note":f"熱度 {sectors[0]['score']}｜平均 {sectors[0]['avg_pct']:+.2f}%｜上漲比 {sectors[0]['breadth']:.1f}%","action":"主線"})
    if attack:priority.append({"title":attack[0]["code"]+" "+attack[0]["name"],"note":attack[0]["reason"],"action":"主攻#1"})
    if next_list:priority.append({"title":next_list[0]["code"]+" "+next_list[0]["name"],"note":next_list[0]["reason"],"action":"下一棒#1"})

    # Determine freshness per market instead of taking the first row's date.
    # The old "first row wins" logic could mark the whole feed stale even after TWSE
    # had already been refreshed to today, because TPEx rows happened to appear first.
    today_iso=now.strftime("%Y-%m-%d")
    today_roc=f"{now.year-1911:03d}{now.month:02d}{now.day:02d}"
    def market_dates(market):
        return {day for x in rows if x.get("market")==market and x.get("date")
                if (day:=normalize_exchange_date(x.get("date")))}
    final_twse_dates=market_dates("TWSE")
    final_tpex_dates=market_dates("TPEX")
    previous_data_date=None
    try:
        previous_feed=json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
        candidate_date=previous_feed.get("data_date") if isinstance(previous_feed,dict) else None
        if isinstance(candidate_date,str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}",candidate_date):
            previous_data_date=candidate_date
    except (OSError,ValueError,TypeError):
        pass
    latest_close_date=latest_shared_close_date(
        final_twse_dates,final_tpex_dates,today_iso,previous_data_date,market_open,today_iso)
    # A verified exchange closure overrides apparent source dates; never mint a holiday candle.
    # Reject mixed-date snapshots even if one date happens to be shared.
    source_is_today=(latest_close_date is not None and not known_closure
                     and final_twse_dates=={latest_close_date}
                     and final_tpex_dates=={latest_close_date})
    if source_is_today:
        source_data_date=latest_close_date
        raw_date=latest_close_date
    else:
        twse_latest=max(final_twse_dates) if final_twse_dates else "未知"
        tpex_latest=max(final_tpex_dates) if final_tpex_dates else "未知"
        source_data_date=f"TWSE:{twse_latest} / TPEx:{tpex_latest}"
        # Keep the last verified archive date, not a mixed TWSE/TPEx string.
        archived_days=[snap.get("date") for snap in hist_for_heat
                       if isinstance(snap,dict) and verified_archive_date(snap.get("date"))
                       and snap["date"]<=today_iso]
        raw_date=max(archived_days) if archived_days else source_data_date
    live_coverage=live_count/max(1,len(stocks))
    live_valid=market_open and live_count>=500 and live_coverage>=.35
    stale_source=not source_is_today
    if stale_source and not live_valid:
        diagnostic={"attempted":quote_refresh_window,"market_open":market_open,
            "quote_refresh_window":quote_refresh_window,"valid_trades":live_count,
            "coverage_pct":round(live_coverage*100,1),"mis_stats":live_stats,
            "required_trades":500,"required_coverage_pct":35,"source_data_date":source_data_date,
            "errors":list(dict.fromkeys(str(e)[:160] for e in live_errors))[:8],
            "reason":("本次盤中成交價覆蓋未達驗證門檻，暫停新判讀" if market_open
                      else "雙市場同日官方收盤未通過驗證，暫停新判讀")}
        # The same-day, validated sample remains useful read-only after 13:30
        # until both exchanges publish a verified close. Never promote it to a candle.
        retained_live=retained_intraday_snapshot(previous_feed,datetime.now(TZ),diagnostic)
        if retained_live is not None:
            OUT.write_text(json.dumps(retained_live,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps({"status":"retained_intraday_only","data_date":retained_live["data_date"],
                "updated_at":retained_live["updated_at"],"no_live_signal":True},ensure_ascii=False))
            return
        # Exchange endpoints return Friday prices on weekends and holidays. Keep
        # the prior *audited* close for dated research, not today's trading/risk alerts.
        try:
            old=json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
            retained=validated_previous_close(old, now)
        except (OSError,ValueError):
            retained=None
        if retained is not None:
            # Refresh read-only research with verified staged OHLCV even when
            # exchanges have not yet published a NEW official closing session.
            # Preserve the original data date and never create new trade signals.
            archived_patterns=retained.get("patterns")
            candle_dir=Path("data/twse_ohlcv")
            if (isinstance(archived_patterns,dict)
                    and archived_patterns.get("status")=="ready"
                    and candle_dir.is_dir()):
                archived_patterns=json.loads(json.dumps(archived_patterns))
                # Older archived signals predate close_series. Reconstruct ONLY
                # their observed historical closes, without rescoring signals.
                snapshots=json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []
                if (isinstance(snapshots,list) and len(snapshots)>=21
                        and snapshots[-1].get("date")==retained.get("data_date")):
                    last21=snapshots[-21:]
                    if len({snap.get("date") for snap in last21})==21:
                        for rows in archived_patterns.get("signals",{}).values():
                            for row in rows:
                                code=str(row.get("code",""))
                                try:
                                    observed=[{"date":snap["date"],"close":float(snap["prices"][code])}
                                              for snap in last21]
                                except (KeyError,ValueError,TypeError):
                                    continue
                                if (len(observed)==21 and observed[-1]["close"]==float(row.get("price",0))):
                                    row["close_series"]=observed
                files_by_code={}
                for code in {str(row.get("code","")) for rows in archived_patterns.get("signals",{}).values() for row in rows}:
                    monthly=[]
                    for file in sorted(candle_dir.glob(code+"-??????.json")):
                        try:
                            monthly.append(json.loads(file.read_text(encoding="utf-8")))
                        except (OSError,ValueError):
                            monthly=[]
                            break
                    if monthly:files_by_code[code]=monthly
                attach_verified_ohlcv(archived_patterns,files_by_code)
                retained["patterns"]=archived_patterns
            # Carry-over metadata from a holiday must not label the NEXT
            # trading day as a holiday while official closes are still delayed.
            stamp=now.strftime("%Y-%m-%d %H:%M")
            # Keep the verified close timestamp. A midnight status refresh must
            # not turn a valid archived close into a pre-close/unverifiable one.
            # last_checked_at and status_updated_at carry the new check time.
            retained["market"].update({
                "mode":"最近收盤",
                "stale":True,
                "historical_readonly":True,
                "live_valid":False,
                "live_count":live_count,
                "live_coverage_pct":round(live_coverage*100,1),
                "no_new_picks":True,
                "market_data_as_of":retained["data_date"],
                "status_updated_at":stamp,
            })
            if known_closure:
                retained["market"].update({
                    "session_status":"休市",
                    "session_reason":known_closure,
                    "next_expected_session":next_expected_session(now.date()),
                    "brief":f"今日休市（{known_closure}）｜最近有效收盤 {retained['data_date']}｜歷史候選僅供研究，不是今日選股"
                })
                retained["summary"]=f"今日休市：{known_closure}；保留 {retained['data_date']} 歷史名單，暫停新選股及交易訊號。"
            else:
                # Yesterday's close is expected before the opening bell. During
                # the session the missing input is live coverage, not a closing
                # file that the exchanges cannot have published yet.
                if minutes < 540:
                    session_status="盤前準備"
                    session_reason="尚未開盤；保留最近有效收盤，等待今日盤中行情驗證"
                elif market_open:
                    session_status="盤中資料不足"
                    session_reason="今日盤中成交價覆蓋未達驗證門檻，暫停新判讀"
                elif retained["data_date"]==today_iso:
                    session_status="收盤重驗失敗"
                    session_reason="本次 TWSE／TPEx 來源重抓未通過；保留今日已驗證收盤，暫停新判讀"
                else:
                    session_status="交易日資料待驗證"
                    session_reason="TWSE／TPEx 當日官方收盤尚未完成交叉驗證"
                retained["market"].update({
                    "session_status":session_status,
                    "session_reason":session_reason,
                    "next_expected_session":None,
                    "brief":f"{session_status}｜{session_reason}｜最近有效收盤 {retained['data_date']}｜歷史名單僅供研究"
                })
                retained["summary"]=f"{stamp} {session_reason}；保留 {retained['data_date']} 歷史名單，暫停今日新選股。"
            retained["risk"]={**retained.get("risk",{}),"as_of":retained["data_date"],"actionable":False}
            # Keep public ticker-only tracked symbols visible in the PARTIAL
            # dated MIS sample without exposing private costs or quantities.
            tracked_codes=set(retained.get("holdings") or {})
            live_sample=[x for x in stocks if x.get("live") is True and x.get("quote_time")]
            live_sample.sort(key=lambda x:(x["code"] not in tracked_codes,x["code"]))
            retained["market"]["partial_live"]={"asof":stamp,"verified_count":live_count,"coverage_pct":round(live_coverage*100,1),"complete":False,"quotes":[{"code":x["code"],"price":x["close"],"quote_time":x.get("quote_time")} for x in live_sample[:250]]}
            retained["market"]["live_diagnostics"]={"attempted":quote_refresh_window,"market_open":market_open,"quote_refresh_window":quote_refresh_window,"updater_time_taipei":stamp,"valid_trades":live_count,"mis_stats":live_stats,"required_trades":500,"required_coverage_pct":35,"errors":list(dict.fromkeys(str(e)[:160] for e in live_errors))[:8],"reason":("官方休市，不更新即時行情" if known_closure else session_reason)}
            retained["holdings"]=refresh_public_etf_references(
                retained.get("holdings"),holdings_by_code,retained["data_date"])
            financial_snapshot=load_recent_financial_snapshot(retained["data_date"])
            for candidate_group in ("attack","next","monster","tomorrow_monster","future_monster","rotate"):
                attach_financial_context(retained.get(candidate_group) or [],financial_snapshot,retained["data_date"])
            OUT.write_text(json.dumps(retained,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps({"status":"archived_close_only",
                              "data_date":retained["data_date"],
                              "checked_at":now.strftime("%Y-%m-%d %H:%M"),
                              "no_live_signal":True},ensure_ascii=False))
            return

    # Intraday MIS quotes are not an official post-close dataset. A sufficiently
    # populated live snapshot may power intraday screens only during trading hours.
    if live_valid and market_open:
        raw_date=today_iso
        stale_source=False
    elif stale_source:
        # Safety invariant applies all day, including after close: stale official
        # daily data must never be presented as today's attack/next/monster radar.
        errors.append(f"行情來源仍為 {source_data_date or '未知日期'}，今日候選榜暫停避免誤判")
        attack=[];next_list=[];monster=[];tomorrow_monster=[];future_monster=[];rotate=[]
        priority=[x for x in priority if x.get("action") not in ("主攻#1","下一棒#1")]
    elif market_open:
        errors.append(f"盤中即時覆蓋不足 {live_count}/{len(stocks)}，候選榜暫停避免誤判")
        attack=[];next_list=[];monster=[];tomorrow_monster=[];future_monster=[];rotate=[]
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
    # Add current, already-published financial context to visible candidates.
    # This is display-only: technical scores, eligibility, archives, and backtests
    # remain unchanged until a point-in-time financial strategy is separately tested.
    financial_snapshot=load_recent_financial_snapshot(raw_date)
    for candidate_group in (attack,next_list,monster,tomorrow_monster,future_monster,rotate):
        attach_financial_context(candidate_group,financial_snapshot,raw_date)
    market_mode="資料過期" if stale_source else ("盤中即時" if live_valid else ("盤中資料不足" if market_open else ("今日收盤" if raw_date==today_iso else "最近收盤")))
    # Archive the actual verified exchange date; never fall back to today for malformed/mixed dates.
    date_key=verified_archive_date(raw_date)
    history=hist_for_heat
    official_close_verified=(date_key is not None and source_is_today and market_mode in ("今日收盤","最近收盤")
                             and not market_open and now.hour*60+now.minute>=810)
    if official_close_verified:
        # Only a verified exchange close may create or replace a backtest day.
        history=update_history(history,date_key,stocks,attack[:5]+next_list[:5],
                               {"sell_ratio":round(inst_sell_ratio*100,1),"net_lots":round(inst_total/1000),"verified":True,"data_date":today_iso} if inst_complete else None)
        HISTORY.parent.mkdir(parents=True,exist_ok=True)
        HISTORY.write_text(json.dumps(history,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        patterns=build_pattern_signals(history,by_code,stock_sector,sectors,asof=today_iso)
        # Optional, locally staged TWSE monthly files only. No new network calls
        # or invented candles during the daily market feed refresh.
        candle_dir=Path("data/twse_ohlcv")
        if candle_dir.is_dir() and patterns.get("status")=="ready":
            selected={str(row["code"]) for rows in patterns["signals"].values() for row in rows}
            files_by_code={}
            for code in selected:
                monthly=[]
                for file in sorted(candle_dir.glob(code+"-??????.json")):
                    try:
                        monthly.append(json.loads(file.read_text(encoding="utf-8")))
                    except (OSError,ValueError):
                        monthly=[]
                        break
                if monthly:files_by_code[code]=monthly
            attach_verified_ohlcv(patterns,files_by_code)
        backtest=calc_backtest(history,{x["code"]:x["close"] for x in stocks})
    else:
        patterns=build_pattern_signals([],{}, {}, [],asof=today_iso)
        patterns["status"]="not_official_close"
        # Partial intraday/stale prices cannot be scored as a new backtest result.
        backtest=calc_backtest([],{})

    old_web_recommendations=[]; old_web_updated_at=None; old_web_status={}
    try:
        if OUT.exists():
            old_out=json.loads(OUT.read_text(encoding="utf-8"))
            old_web_recommendations=old_out.get("web_recommendations") or []
            old_web_updated_at=old_out.get("web_recommendations_updated_at")
            old_web_status=old_out.get("web_recommendations_status") or {}
    except Exception:
        pass

    # A successful network consensus must have candidates; never label an empty board "ok".
    if not old_web_recommendations and old_web_status.get("ok"):
        old_web_status=dict(old_web_status)
        old_web_status["ok"]=False
        old_web_status["summary"]="網路推薦名單為空；等待下一輪外部資料交叉驗證，不提供虛構候選"

    # Recompute only public ticker-only signals from dated official closes.
    # Personal cost, quantity and P/L never enter this feed.
    try:
        price_archive=json.loads(DAILY_PRICES.read_text(encoding="utf-8"))
        price_days=price_archive.get("days",{}) if isinstance(price_archive,dict) else {}
    except (OSError,ValueError,TypeError):
        price_days={}
    prior_public_holdings=(previous_feed.get("holdings") or {}) if isinstance(previous_feed,dict) else {}
    public_signals=build_public_holding_signals(
        prior_public_holdings,price_days,raw_date,risk,
        {x["code"]:x["close"] for x in stocks} if official_close_verified else {},
        official_close_verified=official_close_verified)
    if official_close_verified:
        public_signals=refresh_public_etf_references(public_signals,holdings_by_code,raw_date)
    out={
        "selection_policy":SELECTION_POLICY,
        "schema":4,"updated_at":now.strftime("%Y-%m-%d %H:%M"),"data_date":raw_date,"source_data_date":source_data_date,
        "summary":"JEI 多因子決策：大盤風險 → 族群強弱 → 個股動能/流動性 → 市場風險與動態風控；避免只看單日漲幅。",
        "risk":{"level":("stale" if stale_source else level),"label":label,"score":risk,
                "actionable":not stale_source,"as_of":raw_date,
                "cash":("暫停判讀" if stale_source else cash),"reasons":reasons,
                "breadth":round(adv_ratio*100,1),"median_pct":round(median,2),"down5":down5,"limit_down":limit_down,
                "divergence":divergence,"institutional_sell_ratio":round(inst_sell_ratio*100,1) if inst_complete else None,"institutional_net_lots":round(inst_total/1000) if inst_complete else None,
                "institutional_3d_sell_avg":round(inst_3d_avg,1) if inst_complete and len(inst_3d)>=3 else None,"institutional_5d_sell_avg":round(inst_5d_avg,1) if inst_complete and len(inst_5d)>=5 else None,"institutional_withdrawal":inst_withdrawal if inst_complete else None},
        "market":{"status":market_status,"mode":market_mode,"last_checked_at":now.strftime("%Y-%m-%d %H:%M"),
                  "index":{"change_pct":taiex_pct,"data_date":today_iso if taiex_pct is not None else None,
                           "source":taiex_source,"date_verified":taiex_pct is not None,
                           "checked_at":now.strftime("%Y-%m-%d %H:%M")},
                  "live_count":live_count,"close_count":len(stocks),"live_coverage_pct":round(live_coverage*100,1),"live_valid":live_valid,"stale":stale_source or raw_date!=today_iso,"historical_readonly":raw_date!=today_iso,"post_close_refresh":post_close_refresh,
                  "live_diagnostics":{"attempted":quote_refresh_window,"market_open":market_open,"quote_refresh_window":quote_refresh_window,"updater_time_taipei":now.strftime("%Y-%m-%d %H:%M"),
                      "valid_trades":live_count,"mis_stats":live_stats,"required_trades":500,
                      "required_coverage_pct":35,
                      "errors":list(dict.fromkeys(str(e)[:160] for e in live_errors))[:8],
                      "reason":("非行情更新時段" if not quote_refresh_window else
                                "盤中有效成交價與覆蓋率已達標" if live_valid else
                                "交易時段外：僅供收盤資料參考" if not market_open else
                                "MIS 查詢失敗或有效成交價覆蓋率不足")},
                  "analysis_scope":{"mode":"verified_live_sample" if market_open else "official_close","count":len(analysis_stocks),"universe_count":len(stocks)},
                  "brief":(f"已驗證盤中樣本 {len(analysis_stocks)}/{len(stocks)}｜" if market_open else "")+f"{market_mode}多因子市場｜加權 {taiex_txt}｜廣度 {adv_ratio*100:.1f}%｜中位數 {median:+.2f}%｜跌逾5% {down5}｜行情時間以最近檢查時間為準",
                  "market_data_as_of":raw_date,
                  "session_status":("休市" if known_closure else "交易日資料待驗證" if stale_source else "已驗證"),
                  "no_new_picks":bool(stale_source),
                  "partial_live":({"asof":now.strftime("%Y-%m-%d %H:%M"),"verified_count":live_count,
                                   "complete":False,
                                   "quotes":[{"code":x["code"],"price":x["close"],"quote_time":x.get("quote_time")}
                                             for x in stocks if x.get("live") is True
                                             and x["code"] in (previous_feed.get("holdings") or {})]}
                                  if stale_source else None)},
        "sectors":sectors,"stock_sectors":stock_sector,
        "universe":[{"code":x["code"],"name":x["name"],"market":x["market"]} for x in stocks if re.fullmatch(r"[1-9][0-9]{3}",x["code"])],
        "institutional":institutional,
        "institutional_status":{"ok":inst_complete,"partial":bool(institutional) and not inst_complete,"data_date":today_iso if inst_complete else None,"count":len(institutional),"errors":inst_errors,"debug":inst_debug},
        "holdings":public_signals,"priority":priority,"attack":attack,"next":next_list,"monster":monster,"tomorrow_monster":tomorrow_monster,"future_monster":future_monster,"rotate":rotate,"flow":flow,
        "avoid_chase":[{"code":x["code"],"name":x["name"],"as_of":raw_date,
                        "reason":str(raw_date)+"收盤漲幅 "+str(x.get("change_pct"))+"%｜短線追高風險，等新交易日確認"}
                       for x in monster if (x.get("change_pct") or 0)>=9.5 or "過熱警戒" in x.get("reason","")][:8],
        "backtest":backtest,
        "patterns":patterns,
        "web_recommendations":old_web_recommendations,
        "web_recommendations_updated_at":old_web_updated_at,
        "web_recommendations_status":old_web_status,
        "sources":["TWSE OpenAPI STOCK_DAY_ALL","TWSE OpenAPI MI_INDEX","TPEx OpenAPI daily close quotes","TWSE MIS intraday stock/index quotes","TWSE T86 institutional investors","TPEx institutional investors OpenAPI"]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    # Public feed must never expose personal portfolio positions or valuations.
    if not is_safe_public_holdings(out.get("holdings")):
        raise RuntimeError("Privacy check failed: disallowed public holdings fields")
    forbidden={"cost","shares","pnl","pnl_pct","market_value","avg_cost"}
    for code, holding_row in (out.get("holdings") or {}).items():
        if isinstance(holding_row,dict) and forbidden.intersection(holding_row):
            raise RuntimeError("Privacy check failed: sensitive portfolio field")
    # Preserve official same-day post-close quotes across subsequent runs. No stale
    # or intraday quote is treated as an official daily close.
    if official_close_verified:
        try:
            archive=json.loads(DAILY_PRICES.read_text(encoding="utf-8")) if DAILY_PRICES.exists() else {}
            days=archive.get("days",{}) if isinstance(archive,dict) else {}
            if not isinstance(days,dict):days={}
            quotes=official_prices
            if len(quotes)>=500:
                actions={d:dict(v) for d,v in validated_actions(archive).items()}
                if official_actions:
                    actions.setdefault(today_iso,{}).update(official_actions)
                days[today_iso]=quotes
                days=dict(sorted(days.items())[-65:])
                result={"schema":1,"kind":"official_daily_close","days":days}
                actions={d:v for d,v in actions.items() if d in days}
                if actions:result['corporate_actions']=actions
                DAILY_PRICES.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        except Exception as e:
            errors.append("每日收盤存檔:"+str(e))
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"updated_at":out["updated_at"],"risk":risk,"stocks":len(stocks),"live_count":live_count,"sectors":len(sectors),"errors":errors},ensure_ascii=False))

if __name__=="__main__":main()
