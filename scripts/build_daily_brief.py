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
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo
try:
    from scripts.market_sessions import closure_reason
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    from market_sessions import closure_reason

ROOT=Path(__file__).resolve().parents[1]
TAIPEI=ZoneInfo("Asia/Taipei")
NEW_YORK=ZoneInfo("America/New_York")
FEED=ROOT/"remote/system.json"
PAPER=ROOT/"remote/strategy_performance.json"
OUTPUT=ROOT/"remote/brief.json"
ARCHIVE=ROOT/"remote/daily_prices.json"
US_SYMBOLS=(("^GSPC","S&P 500"),("^IXIC","NASDAQ"),("^DJI","道瓊"))
GLOBAL_SYMBOLS=(
    ("^SOX","費城半導體"),("^VIX","VIX 恐慌指數"),("TSM","台積電 ADR"),
    ("CL=F","WTI 原油"),("DX-Y.NYB","美元指數"),("USDTWD=X","美元／新台幣"),
    ("^N225","日經 225"),("^KS11","韓國綜合"),
)

def get_url(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 JEI-Stock-Radar/1.0"})
    with urllib.request.urlopen(req,timeout=12) as res:
        return res.read().decode("utf-8","replace")

def clean(s,n=180):
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]*>"," ",str(s or "")))).strip()[:n]

def num(v):
    if isinstance(v,bool): return None
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

def previous_archived_close(archive,now):
    """Return only the expected previous session's full dated archive."""
    previous=now.date()-timedelta(days=1)
    for _ in range(20):
        if closure_reason(previous) is None:
            break
        previous-=timedelta(days=1)
    if not isinstance(archive,dict) or archive.get("schema")!=1 or archive.get("kind")!="official_daily_close":
        return None
    days=archive.get("days")
    if not isinstance(days,dict): return None
    prices=days.get(previous.isoformat())
    if not isinstance(prices,dict) or sum((num(p) or 0)>0 for p in prices.values())<500:
        return None
    return previous.isoformat(),prices

def retained_close_verified(feed,archive,now):
    """Corroborate the retained morning baseline; never enable today's picks."""
    market=feed.get("market") or {}
    if (market.get("mode")!="最近收盤" or market.get("historical_readonly") is not True
            or market.get("no_new_picks") is not True or market.get("live_valid") is not False):
        return False
    archived=previous_archived_close(archive,now)
    if archived is None or feed.get("data_date")!=archived[0]: return False
    _,prices=archived
    count=market.get("close_count")
    if isinstance(count,bool) or num(count) is None or num(count)<500:
        return False
    # Check every publicly displayed candidate against the dated close archive.
    for row in feed.get("attack") or []:
        if not isinstance(row,dict): return False
        shown,official=num(row.get("price")),num(prices.get(str(row.get("code"))))
        if shown is None or official is None or official<=0 or abs(shown/official-1)>0.005:
            return False
    return True

def quality(feed,edition,now,archive=None):
    market=feed.get("market") or {}
    raw=str(feed.get("data_date") or "")
    try: lag=(now.date()-date.fromisoformat(raw)).days
    except ValueError: return False,"市場資料日缺失"
    if edition=="morning" and retained_close_verified(feed,archive,now):
        return True,"已核對封存收盤基準日 "+raw+"；歷史唯讀，非今日即時行情或新選股"
    if lag<0 or lag>5: return False,"市場資料日太舊或超前："+raw
    if market.get("mode")!="今日收盤" or market.get("stale") is not False or int(market.get("close_count") or 0)<500:
        return False,"官方收盤行情尚未驗證："+raw
    if edition=="close" and lag!=0: return False,"今日官方收盤尚未就緒；最新 "+raw
    if edition=="morning" and lag==0 and now.hour<9:
        return False,"早報異常：開盤前不應已有今日收盤"
    return True,"官方收盤基準日 "+raw+"；非即時行情"

def fetch_market_symbols(symbols,now):
    quotes=[]
    for code,label in symbols:
        try:
            url="https://query1.finance.yahoo.com/v8/finance/chart/"+urllib.parse.quote(code,safe="")+"?range=10d&interval=1d"
            result=json.loads(get_url(url))["chart"]["result"][0]
            meta=result.get("meta") or {}
            market_tz=ZoneInfo(str(meta.get("exchangeTimezoneName") or "America/New_York"))
            stamps=result.get("timestamp") or []
            closes=result["indicators"]["quote"][0]["close"] or []
            entries=[]
            for stamp,price in zip(stamps,closes):
                p=num(price)
                if p and p>0:
                    day=datetime.fromtimestamp(stamp,timezone.utc).astimezone(market_tz).date()
                    entries.append((day,p))
            if len(entries)<2: continue
            day,price=entries[-1]
            current_market_day=now.astimezone(market_tz).date()
            if not 0 <= (current_market_day-day).days <= 5: continue
            change=(price/entries[-2][1]-1)*100
            # Yahoo's current daily bar can still be live. Its `close` field
            # alone is not evidence of a completed exchange closing auction.
            quotes.append({"name":label,"date":day.isoformat(),"close":round(price,2),
                           "change_pct":round(change,2),"source":"Yahoo Finance",
                           "bar_interval":"1d","quote_kind":"daily_bar_reference",
                           "closing_price_verified":False,
                           "exchange_timezone":str(market_tz),
                           "report_as_of":now.isoformat(timespec="minutes")})
        except (OSError,KeyError,IndexError,TypeError,ValueError):
            continue
    return quotes

def fetch_us(now):
    return fetch_market_symbols(US_SYMBOLS,now)

def fetch_global(now):
    return fetch_market_symbols(GLOBAL_SYMBOLS,now)

def market_quote_line(quote,date_prefix):
    # Safe for legacy records that have no session-completion metadata too.
    return (f"{quote['name']}｜{date_prefix} {quote['date']} 日線參考價 {quote['close']:,.2f}｜"
            f"{percent(quote['change_pct'])}｜{quote.get('source','來源待確認')}；未獨立驗證收盤")

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
    for key,item in list((paper.get("strategies") or {}).items())[:4]:
        summary=item.get("summary") or {}
        val=num(summary.get("estimated_liquidation_equity_ntd"))
        if val is not None:
            closed,wins=summary.get("closed"),summary.get("wins")
            valid_counts=(type(closed) is int and type(wins) is int and 0<=wins<=closed)
            rate=(f"已平倉 {closed} 筆｜勝率 {wins/closed*100:.2f}%" if closed else "已平倉 0 筆｜勝率待累積") if valid_counts else "已平倉勝率待驗證"
            entries.append(f"{clean(item.get('name') or key,28)}｜估算權益 {val:,.0f} 元｜相對初始 {percent((val/principal-1)*100)}｜{rate}")
    entries.append("收盤價紙上模擬；滑價與無法成交限制尚未納入；未完成完整樣本外驗證。")
    return {"kind":"paper_performance","title":"四策略模擬復盤","items":entries}

def generate(edition,now,feed,paper,us_fn=fetch_us,global_fn=fetch_global,news_fn=fetch_news,archive=None):
    good,note=quality(feed,edition,now,archive)
    if not good and edition=="morning":
        archived=previous_archived_close(archive,now)
        if archived is not None:
            # An intraday/degraded feed can mix prices and derived indicators.
            # Use only the immutable price archive, never copy its risk or picks.
            day,prices=archived
            feed={"data_date":day,
                  "market":{"status":"封存收盤參考；即時行情未驗證","historical_readonly":True},
                  "risk":{"label":"未驗證，暫停判讀","reasons":["封存有效收盤價 "+str(sum((num(p) or 0)>0 for p in prices.values()))+" 檔；不沿用未驗證評分"]},
                  "sectors":[],"attack":[]}
            good=True
            note="封存收盤基準日 "+day+"；台股行情驗證未通過，評分與選股暫停；非即時行情"
    report={
       "edition":edition,"date":now.date().isoformat(),
       "generated_at":now.isoformat(timespec="minutes"),
       "status":"ready" if good else "pending","note":note,
       "source_date":str(feed.get("data_date") or ""),
       "title":"JEI 開盤前早報" if edition=="morning" else "JEI 盤後復盤",
       "blocks":[],"us_market":[],"global_market":[],"news":[],
       "report_url":"https://jei-stock-radar.vercel.app/remote/brief.html",
       "privacy":"只用公開市場資料，不含私人持股與成本"
    }
    if not good:
        report["blocks"]=[{"title":"資料尚未就緒","items":[note,"不把舊價當今日行情；LINE 僅通知資料異常，不發布選股。"]}]
        return report
    report["blocks"]=market_blocks(feed)
    if (feed.get("market") or {}).get("historical_readonly") is True:
        report["blocks"][0]["title"]="歷史收盤風控參考（非今日訊號）"
        report["blocks"][2]["title"]="歷史主攻候選（非今日選股）"
    if edition=="morning":
        report["us_market"]=us_fn(now)
        us_entries=[market_quote_line(x,"美東") for x in report["us_market"]]
        report["blocks"].insert(0,{"title":"全球市場｜美股核心指數","items":us_entries or ["美股報價暫無可信來源，不推測漲跌。"]})
        report["global_market"]=global_fn(now)
        global_entries=[market_quote_line(x,"市場日") for x in report["global_market"]]
        report["blocks"].insert(1,{"title":"跨市場風險指標｜各市場日期分開","items":global_entries or ["跨市場報價暫無可信來源，不以舊值補足。"]})
        report["news"]=news_fn(now)
        report["blocks"].append({"title":"重要新聞","items":[f"近期新聞標題 {len(report['news'])} 則；請點連結看原文。新聞標題不等於利多利空。"]})
    else:
        report["blocks"].append(paper_block(paper,report["source_date"]))
    return report

def build(edition,now,feed_path=FEED,paper_path=PAPER,output_path=OUTPUT,archive_path=ARCHIVE):
    feed,paper=load(feed_path),load(paper_path)
    prior=load(output_path)
    result={"schema":1,"privacy":"公開市場摘要，不含個人持股、成本、LINE 資料或憑證",
            "morning":prior.get("morning"),"close":prior.get("close"),
            "checks":prior.get("checks") if isinstance(prior.get("checks"),dict) else {}}
    checked=generate(edition,now,feed,paper,archive=load(archive_path))
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
