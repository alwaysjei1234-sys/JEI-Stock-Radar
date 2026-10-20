#!/usr/bin/env python3
"""Collect public Taiwan-market RSS headlines for research, not trading signals."""
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

FEEDS = {
    "tw_market": "https://tw.stock.yahoo.com/rss?category=tw-market",
    "research": "https://tw.stock.yahoo.com/rss?category=research",
    "international": "https://tw.stock.yahoo.com/rss?category=intl-markets",
}
OUT = Path("remote/news_intelligence.json")
CODE = re.compile(r"(?<![0-9])(?:[0-9]{4})(?![0-9])")

def collect(categories=("tw_market",), opener=None):
    opener = opener or urllib.request.urlopen
    items, errors, seen = [], [], set()
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
                items.append({
                    "category": category, "title": title[:300],
                    "url": link, "published": (entry.findtext("pubDate") or "").strip(),
                    "mentioned_codes": sorted(set(CODE.findall(title))),
                    "source": "Yahoo Finance RSS",
                })
        except Exception as exc:
            errors.append({"category": category, "error": str(exc)[:200]})
    return {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "research_only": True, "items": items[:250], "errors": errors}

def main():
    # Start with Taiwan headlines; research and international are opt-in phases.
    data = collect(("tw_market",))
    if data["errors"] and not data["items"]:
        raise SystemExit("No usable Taiwan RSS items: " + str(data["errors"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Collected {len(data['items'])} Taiwan headlines; errors={len(data['errors'])}")

if __name__ == "__main__":
    main()
