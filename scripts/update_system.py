#!/usr/bin/env python3
import json, math, re, statistics, urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TWSE_STOCK="https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TWSE_INDEX="https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX"
TPEX_STOCK="https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
OUT=Path("remote/system.json")
TZ=ZoneInfo("Asia/Taipei")

def fetch_json(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 JEI-Stock-Radar-Updater/3.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.loads(r.read().decode("utf-8-sig"))

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
def stock_only(s):return bool(re.fullmatch(r"\d{4}",s.get("code",""))) and s.get("close") and s.get("pct") is not None
def score_row(s,mode):
    p=s["pct"];pos=position(s);liq=clamp((math.log10(max(s.get("value",0),1))-7.0)*8,0,20)
    if mode=="attack":score=52+clamp(p,0,10)*3.5+pos*14+liq
    elif mode=="next":score=58+clamp(p+.5,0,5)*3+pos*17+liq
    else:score=48+clamp(p,0,12)*4+pos*12+liq
    return int(round(clamp(score,0,99)))
def item(s,score,reason):
    return {"code":s["code"],"name":s["name"],"score":score,"reason":reason,"price":s["close"],
            "change_pct":round(s["pct"],2),"market":s["market"]}

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
    stocks=[x for x in rows if stock_only(x)]
    taiex_pct=None
    for x in idx_raw if isinstance(idx_raw,list) else []:
        if str(x.get("指數","")).strip()=="發行量加權股價指數":
            p=num(x.get("漲跌百分比"));sign=str(x.get("漲跌","")).strip()
            taiex_pct=(-abs(p) if sign=="-" and p is not None else p);break
    pcts=[x["pct"] for x in stocks if x["pct"] is not None]
    adv=sum(1 for p in pcts if p>0);dec=sum(1 for p in pcts if p<0);flat=max(0,len(pcts)-adv-dec)
    adv_ratio=adv/max(1,adv+dec);median=statistics.median(pcts) if pcts else 0
    down5=sum(1 for p in pcts if p<=-5);limit_down=sum(1 for p in pcts if p<=-9.4)
    risk=34
    if taiex_pct is not None:risk+=clamp(-taiex_pct,0,6)*9-clamp(taiex_pct,0,4)*5
    risk+=clamp((.48-adv_ratio)*100,0,35)*.9+clamp(-median,0,5)*7+clamp(down5/max(1,len(pcts))*100,0,20)*1.2+clamp(limit_down,0,40)*.7
    risk=int(round(clamp(risk,0,100)))
    if risk>=80:level,label,cash="red","高風險防守","70%↑"
    elif risk>=65:level,label,cash="orange","風險升高","50%–70%"
    elif risk>=45:level,label,cash="yellow","震盪警戒","30%–50%"
    else:level,label,cash="green","正常","20%–30%"
    tradable=[x for x in stocks if x["value"]>=20000000]
    attacks=sorted([x for x in tradable if 1.5<=x["pct"]<=9.7 and position(x)>=.62],key=lambda s:(score_row(s,"attack"),s["value"]),reverse=True)[:8]
    attack=[item(s,score_row(s,"attack"),f"漲幅 {s['pct']:.2f}%｜收盤位於日內高檔｜成交值 {s['value']/1e8:.1f} 億") for s in attacks]
    attack_codes={x["code"] for x in attacks}
    nexts=sorted([x for x in tradable if x["code"] not in attack_codes and -.5<=x["pct"]<=4.5 and position(x)>=.68 and (x["open"] is None or x["close"]>=x["open"])],key=lambda s:(score_row(s,"next"),s["value"]),reverse=True)[:8]
    next_list=[item(s,score_row(s,"next"),f"尚未噴出｜漲幅 {s['pct']:.2f}%｜收盤靠近高點｜成交值 {s['value']/1e8:.1f} 億") for s in nexts]
    monsters=sorted([x for x in tradable if x["pct"]>=5 and position(x)>=.72],key=lambda s:(score_row(s,"monster"),s["pct"],s["value"]),reverse=True)[:8]
    monster=[item(s,score_row(s,"monster"),f"異常強勢 {s['pct']:.2f}%｜高檔收盤｜成交值 {s['value']/1e8:.1f} 億；追價風險高") for s in monsters]
    rotate=[dict(x,reason="換股候選｜"+x["reason"]) for x in attack[:5]]
    taiex_txt="--" if taiex_pct is None else f"{taiex_pct:+.2f}%"
    market_status="偏多" if (taiex_pct or 0)>.5 and adv_ratio>.55 else ("偏空" if (taiex_pct or 0)<-.8 or adv_ratio<.4 else "震盪")
    reasons=[f"加權指數 {taiex_txt}",f"上漲 {adv} / 下跌 {dec}",f"市場中位數 {median:+.2f}%",f"跌逾5% {down5} 檔"]
    if errors:reasons.append("部分資料源降級："+"；".join(errors)[:120])
    flow=[{"icon":"↗","name":"上漲家數","note":f"{adv} 檔｜廣度 {adv_ratio*100:.1f}%","score":adv},
          {"icon":"↘","name":"下跌家數","note":f"{dec} 檔｜平盤 {flat} 檔","score":dec},
          {"icon":"⚠","name":"跌逾 5%","note":"市場急跌壓力檔數","score":down5},
          {"icon":"🔥","name":"強勢動能","note":"漲幅≥5% 且高檔收盤","score":len(monsters)}]
    priority=[{"title":"市場風控","note":"｜".join(reasons),"action":label}]
    if attack:priority.append({"title":attack[0]["code"]+" "+attack[0]["name"],"note":attack[0]["reason"],"action":"主攻#1"})
    if next_list:priority.append({"title":next_list[0]["code"]+" "+next_list[0]["name"],"note":next_list[0]["reason"],"action":"下一棒#1"})
    now=datetime.now(TZ);data_date=next((x["date"] for x in rows if x["date"]),"")
    out={"schema":3,"updated_at":now.strftime("%Y-%m-%d %H:%M"),"data_date":data_date,
         "summary":"風險優先；持股決策由手機本機成本＋即時行情計算；主攻、下一棒、妖股由 JEI 排程刷新。",
         "risk":{"level":level,"label":label,"score":risk,"cash":cash,"reasons":reasons},
         "market":{"status":market_status,"brief":f"最新市場快照｜加權 {taiex_txt}｜上漲 {adv} / 下跌 {dec}｜中位數 {median:+.2f}%｜JEI 每15分鐘更新"},
         "holdings":{},"priority":priority,"attack":attack,"next":next_list,"monster":monster,"rotate":rotate,"flow":flow,
         "backtest":{"hit3":None,"hit5":None,"hit10":None,"samples":0},
         "sources":["TWSE OpenAPI STOCK_DAY_ALL","TWSE OpenAPI MI_INDEX","TPEx OpenAPI daily close quotes"]}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"updated_at":out["updated_at"],"risk":risk,"stocks":len(stocks),"errors":errors},ensure_ascii=False))
if __name__=="__main__":main()
