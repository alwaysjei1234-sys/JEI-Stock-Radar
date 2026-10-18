#!/usr/bin/env python3
"""Reviewable public industry research, not scraped broker recommendations.

Curated source metadata is versioned with exact public source URLs. One institution
counts once even if dozens of headlines quote the same research. This evidence
is about industry conditions, NEVER proof of earnings or a buy-rating for a ticker.
"""
import json
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"remote/research_sources.json"
OUT=ROOT/"remote/industry_research.json"
TZ=ZoneInfo("Asia/Taipei")
AGE_LIMIT_DAYS=365
OFFICIAL_DOMAINS={"TrendForce":("trendforce.com","trendforce.com.tw"),
                  "SEMI":("semi.org",)}

def official_publisher_host(organization,hostname):
    hosts=OFFICIAL_DOMAINS.get(organization,())
    name=(hostname or "").lower()
    return bool(hosts and any(name==domain or name.endswith("."+domain)
                              for domain in hosts))

def validate_registry(data):
    if not isinstance(data,dict) or data.get("schema")!=1:
        raise ValueError("研究來源登錄表格式不正確")
    themes=data.get("themes")
    sources=data.get("sources")
    if not isinstance(themes,list) or not isinstance(sources,list):
        raise ValueError("缺少產業/來源列表")
    sector_names=[x.get("sector") for x in themes if isinstance(x,dict)]
    if len(sector_names)!=len(set(sector_names)) or any(not s for s in sector_names):
        raise ValueError("產業名稱不可重複或為空")
    seen=set()
    for row in sources:
        if not isinstance(row,dict):
            raise ValueError("研究條目必須是物件")
        sid=row.get("id")
        if not sid or sid in seen:
            raise ValueError("研究來源 ID 重複")
        seen.add(sid)
        if not all(isinstance(row.get(key),str) and row[key].strip()
                   for key in ("organization","date","title","url","evidence","caveat","type")):
            raise ValueError("研究來源缺少機構/日期/研究結論/風險")
        try:
            day=date.fromisoformat(row["date"])
        except (ValueError,TypeError) as exc:
            raise ValueError("研究日期格式錯誤") from exc
        if day.isoformat()!=row["date"]:
            raise ValueError("日期必須標準 ISO 格式")
        url=urlsplit(row["url"])
        if (url.scheme!="https" or not url.hostname or url.username or url.password
                or not official_publisher_host(row["organization"],url.hostname)):
            raise ValueError("研究來源必須使用可核對之研究機構官方 HTTPS 網址")
        if not isinstance(row.get("sectors"),list) or not row["sectors"]:
            raise ValueError("研究必須有產業對應")
        if any(s not in sector_names for s in row["sectors"]):
            raise ValueError("研究引用未登錄的產業")
    return True


def build(data,asof):
    validate_registry(data)
    if isinstance(asof,datetime):
        asof=asof.date()
    if not isinstance(asof,date):
        raise TypeError("asof 必須是日期")
    by_sector={}
    for row in data["themes"]:
        sec=row["sector"]
        accepted=[]
        old=[]
        for src in data["sources"]:
            if sec not in src["sectors"]:
                continue
            published=date.fromisoformat(src["date"])
            age=(asof-published).days
            if 0<=age<=AGE_LIMIT_DAYS:
                accepted.append({**src,"days_old":age})
            else:
                old.append({"id":src["id"],"organization":src["organization"],
                            "published":src["date"],"reason":"日期尚未到或超過研究新鮮度期限"})
        institutions=sorted({x["organization"] for x in accepted})
        n=len(institutions)
        level=("多機構產業研究佐證" if n>=2 else
               "單一研究機構佐證" if n==1 else
               "研究證據不足")
        by_sector[sec]={
            "focus":row.get("focus",""),
            "risks_to_verify":row.get("watch",""),
            "evidence_level":level,
            "independent_institutions":n,
            "institutions":institutions,
            "source_articles":len(accepted),
            "sources":sorted(accepted,key=lambda x:x["date"],reverse=True),
            "excluded_sources":old,
            "company_fundamentals_verified":False,
            "actionable_buy_signal":False,
            "caution":"產業報告只能驗證發展方向；缺少個別公司營收、訂單、獲利、估值及相對股價時，不得升級成個股買進訊號"
        }
    return {
        "schema":1,
        "mode":"dated_industry_primary_source_evidence",
        "as_of":asof.isoformat(),
        "freshness_days":AGE_LIMIT_DAYS,
        "research_evidence_only":True,
        "not_broker_rating":True,
        "method":"逐篇人工核對公開原始研究摘要與發表日期，同機構文章不重複計為獨立機構；非自動購買或下載付費報告。",
        "themes":by_sector,
        "sector_order":sorted(by_sector,key=lambda k:
                              (-by_sector[k]["independent_institutions"],
                               -by_sector[k]["source_articles"],k)),
        "source_registry":"research_sources.json",
        "updated_at":datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    }


def main():
    data=json.loads(REGISTRY.read_text(encoding="utf-8"))
    current=datetime.now(TZ)
    result=build(data,current.date())
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"as_of":result["as_of"],"themes":{s:v["independent_institutions"]
          for s,v in result["themes"].items()}},ensure_ascii=False))


if __name__=="__main__":
    main()
