#!/usr/bin/env python3
import html, json, math, re, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

OUT = Path("remote/system.json")
TZ = ZoneInfo("Asia/Taipei")
UA = "Mozilla/5.0 JEI-Stock-Radar-WebConsensus/1.0"

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def fetch_text(url, timeout=15):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.5",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")

def clean_text(s):
    s = html.unescape(str(s or ""))
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def google_news(query):
    q = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    root = ET.fromstring(fetch_text(url))
    out = []
    for item in root.findall(".//item")[:40]:
        title = clean_text(item.findtext("title"))
        desc = clean_text(item.findtext("description"))
        link = clean_text(item.findtext("link"))
        source_el = item.find("source")
        source = clean_text(source_el.text if source_el is not None else "")
        published_at = clean_text(item.findtext("pubDate"))
        out.append({"title": title, "desc": desc, "link": link, "source": source, "published_at": published_at})
    return out

def normalize_name(name):
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff-]", "", str(name or "").replace("*", ""))

def candidate_pool(data):
    pool = {}
    for key in ("attack","next","monster","tomorrow_monster","future_monster","rotate"):
        for x in data.get(key) or []:
            code = str(x.get("code") or "").strip()
            if not re.fullmatch(r"[0-9A-Z]{4,8}", code):
                continue
            p = pool.setdefault(code, {
                "code": code, "name": x.get("name") or code, "jei_score": 0,
                "price": x.get("price"), "change_pct": x.get("change_pct"),
            })
            p["jei_score"] = max(p["jei_score"], int(x.get("score") or 0))
            if p.get("price") is None and x.get("price") is not None:
                p["price"] = x.get("price")
            if p.get("change_pct") is None and x.get("change_pct") is not None:
                p["change_pct"] = x.get("change_pct")
    # Include hot-sector leaders even when not already in JEI candidate lists.
    uni = {str(x.get("code")): x for x in data.get("universe") or [] if x.get("code")}
    for sec in (data.get("sectors") or [])[:6]:
        for x in sec.get("leaders") or []:
            code = str(x.get("code") or "")
            if not re.fullmatch(r"[0-9A-Z]{4,8}", code):
                continue
            u = uni.get(code) or {}
            pool.setdefault(code, {
                "code": code, "name": x.get("name") or u.get("name") or code,
                "jei_score": int(sec.get("score") or 0),
                "price": None, "change_pct": x.get("pct"),
            })
    # Include strongest institutional names from the current candidate universe.
    inst = data.get("institutional") or {}
    for code, p in list(pool.items()):
        v = inst.get(code) or {}
        p["fund_lots"] = round(float(v.get("total") or 0) / 1000)
        p["trust_lots"] = round(float(v.get("trust") or 0) / 1000)
        p["foreign_lots"] = round(float(v.get("foreign") or 0) / 1000)
    return pool

def matches(text, code, name):
    t = str(text or "")
    n = normalize_name(name)
    if code and code in t:
        return True
    if n and len(n) >= 2 and n in normalize_name(t):
        return True
    return False

def cmoney_sentiment(code):
    try:
        text = clean_text(fetch_text(f"https://www.cmoney.tw/forum/stock/{code}", timeout=10))
        m = re.search(r"同學風向.{0,90}?(樂觀|悲觀)", text)
        if not m:
            return None, 0
        return m.group(1), 1
    except Exception:
        return None, 0

PUBLIC_REPORT_TERMS = re.compile(r"研究報告|研究摘要|研究簡報|券商報告|投資報告|個股報告|公開分享")

PUBLIC_SHARED_REPORTS = [
    {
        "code": "3406", "name": "玉晶光",
        "title": "2026/10/16 券商個股報告整理｜退役操盤人的投研筆記",
        "source": "Vocus｜公開分享的券商報告摘要",
        "url": "https://vocus.cc/article/6ad238a4fd89780001ad2c66",
        "link": "https://vocus.cc/article/6ad238a4fd89780001ad2c66",
        "published_at": "2026-10-16",
        "evidence_level": "publicly_shared_secondary",
    },
]

def public_shared_report_hits(code, name, now=None, max_age_days=30):
    now = now or datetime.now(TZ)
    hits = []
    for item in PUBLIC_SHARED_REPORTS:
        if item.get("code") != str(code):
            continue
        try:
            published = datetime.strptime(item.get("published_at", ""), "%Y-%m-%d").date()
            age = (now.date() - published).days
        except (TypeError, ValueError):
            continue
        if 0 <= age <= max_age_days and item.get("url", "").startswith("https://"):
            hits.append(dict(item))
    return hits


def public_research_hits(items, code, name):
    """Keep public research references distinct from ordinary financial news."""
    return [
        item for item in items
        if matches(item.get("title", "") + " " + item.get("desc", ""), code, name)
        and PUBLIC_REPORT_TERMS.search(item.get("title", "") + " " + item.get("desc", ""))
        and item.get("link", "").startswith(("https://", "http://"))
    ]


def main():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    pool = candidate_pool(data)
    if not pool:
        return

    query_groups = {
        "public_reports": [
            "台股 個股研究報告 公開摘要 分析師 when:2d",
            "台股 公開分享 券商研究報告 個股 目標價 when:2d",
        ],
        "market": [
            "台股 強勢股 熱門股 資金 法人 when:1d",
            "台股 AI PCB CPO 半導體 個股 when:1d",
        ],
    }
    news = {"public_reports": [], "market": []}
    errors = []
    for kind, queries in query_groups.items():
        for q in queries:
            try:
                news[kind].extend(google_news(q))
            except Exception as e:
                errors.append(f"{kind}:{type(e).__name__}")

    # Deduplicate by title.
    for kind in news:
        seen = set()
        uniq = []
        for x in news[kind]:
            k = x.get("title")
            if not k or k in seen:
                continue
            seen.add(k)
            uniq.append(x)
        news[kind] = uniq

    # Only probe community pages for the strongest 24 JEI/fund candidates.
    ranked_codes = sorted(pool, key=lambda c: (pool[c].get("jei_score",0), abs(pool[c].get("fund_lots",0))), reverse=True)[:24]
    community = {}
    for code in ranked_codes:
        community[code] = cmoney_sentiment(code)

    recs = []
    for code, p in pool.items():
        name = p.get("name") or code
        report_hits = public_research_hits(news["public_reports"], code, name) + public_shared_report_hits(code, name)
        market_hits = [x for x in news["market"] if matches(x["title"]+" "+x["desc"], code, name)]
        sentiment, community_mentions = community.get(code, (None, 0))
        if not report_hits and not market_hits and not community_mentions:
            continue

        fund = float(p.get("fund_lots") or 0)
        jei = float(p.get("jei_score") or 0)
        chg = p.get("change_pct")
        try: chg = float(chg)
        except Exception: chg = None

        analyst_score = min(35, len(report_hits)*6 + len(market_hits)*4)
        community_score = 16 if sentiment == "樂觀" else (2 if sentiment == "悲觀" else (6 if community_mentions else 0))
        fund_score = clamp(9 + (math.log10(abs(fund)+1)*3.3 if fund >= 0 else -math.log10(abs(fund)+1)*4.0), 0, 20)
        jei_score = clamp(jei/10, 0, 10)
        penalty = 0
        caution = []
        if chg is not None and chg >= 8:
            penalty += 11
            caution.append("單日漲幅已高，避免追價")
        elif chg is not None and chg >= 5.5:
            penalty += 5
            caution.append("短線漲幅偏大")
        if fund < 0:
            penalty += min(12, math.log10(abs(fund)+1)*3.5)
            caution.append("法人合計偏賣")
        if p.get("foreign_lots",0) < 0 < p.get("trust_lots",0):
            caution.append("投信買、外資賣，籌碼分歧")

        score = int(round(clamp(28 + analyst_score + community_score + fund_score + jei_score - penalty, 0, 99)))
        sources = []
        for x in report_hits + market_hits:
            label = x.get("source") or "Google News"
            if label and label not in sources:
                sources.append(label)
        if community_mentions:
            sources.append("CMoney股市爆料同學會")

        parts = []
        if report_hits: parts.append(f"公開研究線索 {len(report_hits)}項")
        if market_hits: parts.append(f"財經媒體 {len(market_hits)}項")
        if sentiment: parts.append(f"網友風向{sentiment}")
        parts.append(f"法人 {fund:+,.0f}張")
        if jei: parts.append(f"JEI {int(jei)}分")

        recs.append({
            "code": code, "name": name, "score": score,
            "price": p.get("price"), "change_pct": chg,
            "public_report_mentions": len(report_hits),
            "public_report_sources": [
                {
                    "title": x.get("title", ""),
                    "source": x.get("source", ""),
                    "url": x.get("link") or x.get("url", ""),
                    "published_at": x.get("published_at", ""),
                    "evidence_level": x.get("evidence_level", "public_research_link"),
                }
                for x in report_hits[:4] if x.get("link") or x.get("url")
            ],
            "public_report_search_url": "https://www.google.com/search?" + urllib.parse.urlencode({
                "q": f'"{code}" "{name}" 台股 研究報告 公開分享 摘要'
            }),
            "analyst_mentions": sum(1 for x in report_hits if x.get("primary_source") is True),
            "community_mentions": community_mentions,
            "fund_lots": round(fund), "jei_score": int(jei) if jei else None,
            "reason": "｜".join(parts),
            "source_labels": sources[:5],
            "caution": "；".join(caution),
        })

    recs.sort(key=lambda x: (x["score"], x.get("fund_lots") or 0), reverse=True)
    recs = recs[:12]

    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    if len(recs) >= 3:
        data["web_recommendations"] = recs
        data["web_recommendations_updated_at"] = now
        data["web_recommendations_status"] = {
            "ok": True,
            "summary": "自動彙整公開網路研究摘要／分享線索、財經媒體、CMoney公開討論與TWSE/TPEx法人資金；每筆研究線索附原文與日期，樣本式共識不等於全網篇數",
            "method": "外部聲量為主、法人資金與JEI交叉驗證；過熱/法人背離自動扣分",
            "errors": errors[:4],
        }
    else:
        status = data.get("web_recommendations_status") or {}
        status.update({
            "ok": False,
            "summary": "本輪網路樣本不足，保留上一版推薦，不用空資料覆蓋",
            "errors": errors[:4],
            "last_attempt": now,
        })
        data["web_recommendations_status"] = status

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({
        "updated": data.get("web_recommendations_updated_at"),
        "count": len(data.get("web_recommendations") or []),
        "errors": errors[:4],
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
