#!/usr/bin/env python3
"""JEI public daily research briefs. Never publish personal holdings."""
import argparse
import html
import json
import math
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
TAIPEI=ZoneInfo("Asia/Taipei")
NEW_YORK=ZoneInfo("America/New_York")
FEED=ROOT/"remote/system.json"
PAPER=ROOT/"remote/strategy_performance.json"
OUTPUT=ROOT/"remote/brief.json"
US_SYMBOLS=(("^GSPC","S&P 500"),("^IXIC","NASDAQ"),("^DJI","道瓊"))

def get_url(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 JEI-Stock-Radar/1.0"})
    with urllib.request.urlopen(req,timeout=12) as res:
        return res.read().decode("utf-8","replace")

def clean(s,n=180):
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",str(s or "")))).strip()[:n]

def num(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (TypeError,ValueError):
        return None

def percent(v):
    x=num(v)
    return "--" if x is None else f"{x:+.2f}%"

def load(path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError): return {}

def quality(feed,edition,now):
    market=feed.get("market") or {}
    raw=str(feed.get("data_date") or "")
    try: lag=(now.date()-date.fromisoformat(raw)).days
    except ValueError: return False,"市場資料日缺失"
    if lag<0 or lag>5: return False,"市場資料日太舊或超前："+raw
    if market.get("mode")!="今日收盤" or market.get("stale") is not False or int(market.get("close_count") or 0)<500:
        return False,"官方收盤行情尚未驗證："+raw
    if edition=="close" and lag!=0: return False,"今日官方收盤尚未就緒；最新 "+raw
    if edition=="morning" and lag==0 and now.hour<9:
        return False,"早報異常：開盤前不應已有今日收盤"
    return True,"官方收盤基準日 "+raw+"；非即時行情"

def fetch_us(now):
    quotes=[]
    for code,label in US_SYMBOLS:
        try:
            url="https://query1.finance.yahoo.com/v8/finance/chart/"+urllib.parse.quote(code,safe="")+"?range=10d&interval=1d"
            result=json.loads(get_url(url))["chart"]["result"][0]
            stamps=result.get("timestamp") or []
            closes=result["indicators"]["quote"][0]["close"] or []
            entries=[]
            for stamp,price in zip(stamps,closes):
                p=num(price)
                if p and p>0:
                    day=datetime.fromtimestamp(stamp,timezone.utc).astimezone(NEW_YORK).date()
                    entries.append((day,p))
            if len(entries)<2: continue
            day,price=entries[-1]
            if not 0 <= (now.astimezone(NEW_YORK).date()-day).days <= 5: continue
            change=(price/entries[-2][1]-1)*100
            quotes.append({"name":label,"date":day.isoformat(),"close":round(price,2),"change_pct":round(change,2)})
        except (OSError,KeyError,IndexError,TypeError,ValueError):
            continue
    return quotes

def fetch_news(now):
    headlines={}
    for query in ("台股 美股 財經焦點 when:1d","台股 AI 半導體 航運 法人 when:1d"):
        url="https://news.google.com/rss/search?q="+urllib.parse.quote_plus(query)+"&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        try:
            root=ET.fromstring(get_url(url))
            for item in root.findall("./channel/item")[:25]:
                title=clean(item.findtext("title"),150)
                link=clean(item.findtext("link"),500)
                try: ts=parsedate_to_datetime(item.findtext("pubDate")).astimezone(TAIPEI)
                except (TypeError,ValueError): continue
                age=(now-ts).total_seconds()
                if not title or not link.startswith("https://") or not 0<=age<=36*3600: continue
                source=item.find("source")
                headlines.setdefault(title,{"title":title,"url":link,
                   "source":clean(source.text if source is not None else "Google News",50),
                   "published_at":ts.strftime("%Y-%m-%d %H:%M")})
        except (OSError,ET.ParseError): continue
    return list(headlines.values())[:6]

def market_blocks(feed):
    market,risk=feed.get("market") or {},feed.get("risk") or {}
    sectors=[]
    for s in (feed.get("sectors") or [])[:4]:
        names="、".join(clean(x.get("name"),20) for x in (s.get("leaders") or [])[:2])
        sectors.append(f"{clean(s.get('name'),24)}｜熱度 {s.get('score','--')}｜平均 {percent(s.get('avg_pct'))}｜代表 {names or '待確認'}")
    picks=[]
    for x in (feed.get("attack") or [])[:5]:
        price=num(x.get("price"))
        picks.append(f"{clean(x.get('code'),8)} {clean(x.get('name'),22)}｜評分 {x.get('score','--')}｜收盤 {price if price else '--'}｜{percent(x.get('change_pct'))}")
    return [
       {"title":"大盤風控","items":[
          f"基準日 {clean(feed.get('data_date'))}｜{clean(market.get('status'))}",
          f"市場風險 {risk.get('score','--')}/100｜{clean(risk.get('label'))}｜現金參考 {clean(risk.get('cash'))}",
          *[clean(x,160) for x in (risk.get("reasons") or [])[:3]]]},
       {"title":"族群輪動","items":sectors or ["沒有可用族群資料"]},
       {"title":"主攻候選（非下單訊號）","items":picks or ["沒有通過資料檢查的候選"]},
    ]

def paper_block(paper,day):
    stamp=paper.get("last_processed_day")
    if not stamp: return {"title":"四策略模擬復盤","items":["尚無可驗證績效資料"]}
    entries=["模擬紀錄截至 "+str(stamp)+"；只用官方收盤價估值，不是實際成交"]
    if stamp!=day: entries.append("模擬資料日期與今日行情不同，請勿視為最新績效")
    principal=num(paper.get("capital_per_strategy")) or 1000000
    for key,item in (paper.get("strategies") or {}).items():
        val=num((item.get("summary") or {}).get("estimated_liquidation_equity_ntd"))
        if val is not None:
            entries.append(f"{clean(item.get('name') or key,28)}｜估算權益 {val:,.0f} 元｜相對初始 {percent((val/principal-1)*100)}")
    return {"title":"四策略模擬復盤","items":entries[:6]}

def generate(edition,now,feed,paper,us_fn=fetch_us,news_fn=fetch_news):
    good,note=quality(feed,edition,now)
    report={
       "edition":edition,"date":now.date().isoformat(),
       "generated_at":now.isoformat(timespec="minutes"),
       "status":"ready" if good else "pending","note":note,
       "source_date":str(feed.get("data_date") or ""),
       "title":"JEI 開盤前早報" if edition=="morning" else "JEI 盤後復盤",
       "blocks":[],"us_market":[],"news":[],
       "report_url":"https://jei-stock-radar.vercel.app/remote/brief.html",
       "privacy":"只用公開市場資料，不含私人持股與成本"
    }
    if not good:
        report["blocks"]=[{"title":"資料尚未就緒","items":[note,"不把舊價當今日行情；LINE 亦不發送。"]}]
        return report
    report["blocks"]=market_blocks(feed)
    if edition=="morning":
        report["us_market"]=us_fn(now)
        us_entries=[f"{x['name']}｜美東 {x['date']} 收盤 {x['close']:,.2f}｜{percent(x['change_pct'])}" for x in report["us_market"]]
        report["blocks"].insert(0,{"title":"全球市場｜最近可驗證美股收盤","items":us_entries or ["美股報價暫無可信來源，不推測漲跌。"]})
        report["news"]=news_fn(now)
        report["blocks"].append({"title":"重要新聞","items":[f"近期新聞標題 {len(report['news'])} 則；請點連結看原文。新聞標題不等於利多利空。"]})
    else:
        report["blocks"].append(paper_block(paper,report["source_date"]))
    return report

def build(edition,now,feed_path=FEED,paper_path=PAPER,output_path=OUTPUT):
    feed,paper=load(feed_path),load(paper_path)
    prior=load(output_path)
    result={"schema":1,"privacy":"公開市場摘要，不含個人持股、成本、LINE 資料或憑證",
            "morning":prior.get("morning"),"close":prior.get("close"),
            "checks":prior.get("checks") if isinstance(prior.get("checks"),dict) else {}}
    checked=generate(edition,now,feed,paper)
    result["checks"][edition]={
        "date":now.date().isoformat(),
        "checked_at":now.isoformat(timespec="minutes"),
        "status":checked["status"],
        "note":checked["note"]
    }
    previous=result.get(edition)
    # Never overwrite a verified Friday/previous-session brief on weekends,
    # holidays, or before today's official close is available.
    if checked["status"]=="ready" or not isinstance(previous,dict) or previous.get("status")!="ready":
        result[edition]=checked
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return checked

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--edition",choices=["auto","morning","close"],default="auto")
    args=p.parse_args()
    now=datetime.now(TAIPEI)
    edition=("morning" if now.hour<12 else "close") if args.edition=="auto" else args.edition
    r=build(edition,now)
    print(f"JEI {edition} {r['date']}: {r['status']} / {r['note']}")

if __name__=="__main__": main()
