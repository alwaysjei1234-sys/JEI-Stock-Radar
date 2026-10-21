#!/usr/bin/env python3
"""Collect Taiwan, research and international RSS headlines for research only."""
import json
import hashlib
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from pathlib import Path

FEEDS = {
    "tw_market": "https://tw.stock.yahoo.com/rss?category=tw-market",
    "research": "https://tw.stock.yahoo.com/rss?category=research",
    "international": "https://tw.stock.yahoo.com/rss?category=intl-markets",
}
OUT = Path("remote/news_intelligence.json")
SECTOR_TERMS = {
    "光通訊/CPO": ("CPO", "矽光子", "光通訊", "光模組", "800G", "1.6T"),
    "記憶體/儲存": ("DRAM", "HBM", "記憶體", "NAND"),
    "半導體設備/測試": ("半導體設備", "先進封裝", "探針卡", "晶圓測試"),
    "AI伺服器/散熱": ("AI伺服器", "液冷", "散熱", "AI server"),
    "電力/電網/基建": ("電網", "變壓器", "資料中心供電"),
    "PCB/載板": ("PCB", "載板", "CCL", "銅箔基板"),
    "航運": ("貨櫃航運", "運價", "SCFI", "航運"),
}

def classify_sectors(title):
    text = title.casefold()
    return [sector for sector, terms in SECTOR_TERMS.items()
            if any(term.casefold() in text for term in terms)]

def headline_fingerprint(title):
    """Group exact normalized headline repeats; not a claim of semantic equivalence."""
    normalized = re.sub(r"[^\w]+", "", title.casefold(), flags=re.UNICODE)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]

def publication_utc(raw):
    try:
        parsed = parsedate_to_datetime(raw)
        return parsed.astimezone(timezone.utc).isoformat() if parsed.tzinfo else None
    except (TypeError, ValueError, IndexError):
        return None

CODE = re.compile(r"(?<![0-9])(?:[0-9]{4})(?![0-9])")

def collect(categories=("tw_market",), opener=None):
    opener = opener or urllib.request.urlopen
    items, errors, seen, headlines = [], [], set(), set()
    for category in categories:
        if category not in FEEDS:
            raise ValueError("Unknown category: " + category)
        try:
            req = urllib.request.Request(FEEDS[category], headers={
                "User-Agent": "JEI-Stock-Radar/1.0 (RSS research)",
                "Accept": "application/rss+xml,application/xml,text/xml",
            })
            with opener(req, timeout=15) as response:
                root = ET.fromstring(response.read(2_000_000))
            for entry in root.findall(".//item"):
                title = (entry.findtext("title") or "").strip()
                link = (entry.findtext("link") or "").strip()
                if not title or not link.startswith(("https://", "http://")):
                    continue
                key = link.split("#")[0].split("?")[0]
                if key in seen:
                    continue
                seen.add(key)
                fingerprint = headline_fingerprint(title)
                if fingerprint in headlines:
                    continue
                headlines.add(fingerprint)
                items.append({
                    "category": category, "title": title[:300],
                    "headline_fingerprint": fingerprint,
                    "url": link, "published": (entry.findtext("pubDate") or "").strip(),
                    "mentioned_codes": sorted(set(CODE.findall(title))),
                    "source": "Yahoo Finance RSS",
                    "publisher_host": (urlsplit(link).hostname or "").lower(),
                    "published_utc": publication_utc(entry.findtext("pubDate")),
                    "sectors": classify_sectors(title),
                    "evidence_level": "news_headline_unverified",
                })
        except Exception as exc:
            errors.append({"category": category, "error": str(exc)[:200]})
    return {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "research_only": True, "institutional_research_verified": False,
            "independent_research_institutions": 0,
            "news_is_not_institutional_evidence": True,
            "items": items[:250], "errors": errors}

def main():
    # Taiwan first, followed by research and international context.
    data = collect(("tw_market", "research", "international"))
    if data["errors"] and not data["items"]:
        raise SystemExit("No usable RSS items: " + str(data["errors"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Collected {len(data['items'])} RSS headlines; errors={len(data['errors'])}")

if __name__ == "__main__":
    main()
