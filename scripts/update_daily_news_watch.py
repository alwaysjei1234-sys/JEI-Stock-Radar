#!/usr/bin/env python3
"""Read the public Daily TW news board and publish derived, linked market signals.

The checked-in feed intentionally omits headlines, article excerpts and broker
report text. It records only dates, counts, derived topic tags, publisher labels
and source URLs so the private research page can use the board as a discovery
and cross-check aid without republishing its editorial summaries.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SOURCE_URL = "https://daily-tw.up.railway.app/"
USER_AGENT = "JEI-Stock-Radar/1.0 (daily public market-news index; contact repository owner)"
OUTPUT = Path(__file__).resolve().parents[1] / "remote" / "daily_news_watch.json"
TAIPEI = ZoneInfo("Asia/Taipei")
TOPICS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("us_semiconductors", "美股／半導體連動", ("美股", "費半", "台積電 adr", "nasdaq", "標普", "道瓊", "輝達", "半導體", "ai")),
    ("geopolitics_energy", "地緣政治／能源", ("伊朗", "中東", "戰爭", "軍事", "原油", "油價", "能源", "封鎖", "制裁")),
    ("rates_fx_macro", "利率／匯率／總經", ("fed", "聯準會", "利率", "殖利率", "通膨", "cpi", "美元", "匯率", "新台幣", "央行")),
    ("taiwan_market_flow", "台股／法人資金", ("台股", "加權", "外資", "投信", "自營商", "三大法人", "融資", "期貨", "櫃買")),
    ("industry_fundamentals", "產業／公司基本面", ("營收", "財報", "eps", "毛利", "訂單", "出貨", "產能", "資本支出", "庫存")),
)


def fetch_page(url: str = SOURCE_URL, timeout: int = 25) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f"source returned HTTP {response.status}")
                return response.read().decode("utf-8", "replace")
        except Exception as exc:  # retry transient upstream/network failures
            error = exc
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError(f"could not read Daily TW news board: {error}") from error


def _text(parts: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


class BoardParser(HTMLParser):
    """Extract topic inputs and outbound article references from the focus board."""

    def __init__(self, sources: dict[str, dict[str, str]] | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.in_focus = False
        self.focus_seen = False
        self.focus_closed = False
        self.focus_depth = 0
        self.in_card = False
        self.card_depth = 0
        self.card: dict[str, Any] | None = None
        self.capture: str | None = None
        self.capture_depth = 0
        self.parts: list[str] = []
        self.anchor_href: str | None = None
        self.anchor_parts: list[str] = []
        self.sources = sources or {}
        self.source_id: str | None = None
        self.source_href: str | None = None
        self.source_parts: list[str] = []
        self.stories: list[dict[str, str]] = []
        self.report_hint = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        classes = set((a.get("class") or "").split())
        if self.in_focus and tag == "h2" and a.get("id") != "focus":
            self.in_focus = False
            self.focus_closed = True
        if tag == "h2" and a.get("id") == "focus":
            self.focus_seen = True
            self.in_focus = True
        if self.in_focus:
            if tag == "h2" and a.get("id") == "focus":
                self.capture, self.parts = "hint", []
                self.capture_depth = 1
            elif tag == "div" and "card" in classes and not self.in_card:
                self.in_card = True
                self.card_depth = 1
                self.card = {"category": "", "publishedAt": "", "publisher": "", "sourceUrl": "", "text": ""}
            elif self.in_card:
                if tag == "div":
                    self.card_depth += 1
                if "cat" in classes:
                    self.capture, self.parts = "category", []
                    self.capture_depth = 0
                elif "ntime" in classes:
                    self.capture, self.parts = "publishedAt", []
                    self.capture_depth = 0
                if tag == "a" and "ref" in classes:
                    self.anchor_href = a.get("href")
                    self.anchor_parts = []
            if tag == "div" and self.in_card and ("news-title" in classes or "news-body" in classes):
                self.capture = "title" if "news-title" in classes else "text"
                self.parts = []
                self.capture_depth = 1
        if tag == "li" and a.get("id", "").startswith("src-"):
            self.source_id = a["id"][4:]
            self.source_href = None
            self.source_parts = []
        elif tag == "a" and self.source_id:
            self.source_href = a.get("href")
            self.source_parts = []
        if tag == "a" and self.anchor_href and self.in_card:
            self.anchor_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.source_id:
            label = _text(self.source_parts)
            href = self.source_href or ""
            if href.startswith("https://"):
                publisher = label.split("｜", 1)[0].strip() if "｜" in label else label.split("｜", 1)[0].split("：", 1)[0].strip()
                self.sources[self.source_id] = {"url": href, "publisher": publisher[:50] or "新聞來源"}
            self.source_href = None
            self.source_parts = []
        if tag == "li" and self.source_id:
            self.source_id = None
        if tag == "a" and self.in_card and self.anchor_href and self.card:
            ref = re.search(r"#src-(\d+)", self.anchor_href)
            if ref:
                source = self.sources.get(ref.group(1))
                if source:
                    self.card["sourceUrl"] = source["url"]
                    self.card["publisher"] = source["publisher"]
            self.anchor_href = None
        if self.capture == "hint" and tag == "h2":
            self.report_hint = _text(self.parts)
            self.capture = None
        elif self.capture:
            if self.capture in {"category", "publishedAt"}:
                value = _text(self.parts)
                if self.in_card and self.card:
                    self.card[self.capture] = value
                elif self.capture == "hint":
                    self.report_hint = value
                self.capture = None
            elif tag == "div" and self.capture in {"title", "text"}:
                value = _text(self.parts)
                if self.capture == "text" and self.card:
                    self.card["text"] = (self.card.get("text", "") + " " + value).strip()
                elif self.capture == "title" and self.card:
                    self.card["text"] = (self.card.get("text", "") + " " + value).strip()
                self.capture = None
        if self.in_focus and tag == "div" and self.in_card:
            self.card_depth -= 1
            if self.card_depth <= 0:
                if self.card and self.card.get("text"):
                    self.stories.append(self.card)
                self.card = None
                self.in_card = False

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.parts.append(data)
        if self.source_id and self.source_href is not None:
            self.source_parts.append(data)


class SourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.current: str | None = None
        self.href = ""
        self.parts: list[str] = []
        self.capture = False
        self.sources: dict[str, dict[str, str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "li" and (a.get("id") or "").startswith("src-"):
            self.current = a["id"][4:]
        elif tag == "a" and self.current:
            self.href = a.get("href") or ""
            self.parts = []
            self.capture = True

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.capture and self.current:
            label = _text(self.parts)
            if self.href.startswith("https://"):
                publisher = label.split("｜", 1)[0].split("：", 1)[0].strip()
                self.sources[self.current] = {"url": self.href, "publisher": publisher[:50] or "新聞來源"}
            self.capture = False
            self.href = ""
            self.parts = []
        elif tag == "li":
            self.current = None


def analyze_html(html: str, checked_at: datetime | None = None) -> dict[str, Any]:
    source_parser = SourceParser()
    source_parser.feed(html)
    parser = BoardParser(source_parser.sources)
    parser.feed(html)
    if not parser.focus_seen or not parser.stories:
        raise ValueError("Daily TW page has no parseable 今日焦點 cards")
    now = checked_at or datetime.now(TAIPEI)
    groups: dict[str, dict[str, Any]] = {
        key: {"id": key, "label": label, "articleCount": 0, "references": []}
        for key, label, _ in TOPICS
    }
    categories: dict[str, int] = {}
    refs: list[dict[str, str]] = []
    story_ids: set[str] = set()
    for story in parser.stories:
        category = story.get("category", "").strip() or "其他"
        categories[category] = categories.get(category, 0) + 1
        body = story.get("text", "").casefold()
        matching = [
            (key, label) for key, label, terms in TOPICS
            if any(term.casefold() in body for term in terms)
        ]
        url = story.get("sourceUrl", "")
        if not url.startswith("https://"):
            url = SOURCE_URL + "#focus"
        stable = hashlib.sha256((story.get("publishedAt", "") + "|" + url + "|" + category).encode()).hexdigest()[:14]
        if stable in story_ids:
            continue
        story_ids.add(stable)
        published = story.get("publishedAt", "")
        reference = {"id": stable, "publishedAt": published[:32], "category": category, "publisher": story.get("publisher", "新聞來源"), "url": url}
        refs.append(reference)
        for key, _ in matching:
            group = groups[key]
            group["articleCount"] += 1
            if len(group["references"]) < 4:
                group["references"].append(reference)
    themes = [group for group in groups.values() if group["articleCount"]]
    themes.sort(key=lambda item: (-item["articleCount"], item["label"]))
    report_date = ""
    dm = re.search(r"(\d{1,2}/\d{1,2})[^\n]{0,80}(?:更新|場|今日|台股)", parser.report_hint)
    if dm:
        try:
            month, day = map(int, dm.group(1).split("/"))
            year = now.year
            report_date = datetime(year, month, day, tzinfo=TAIPEI).date().isoformat()
            if datetime.fromisoformat(report_date).date() > now.date() + timedelta(days=2):
                report_date = datetime(year - 1, month, day, tzinfo=TAIPEI).date().isoformat()
        except ValueError:
            report_date = ""
    return {
        "schemaVersion": 1,
        "source": {"name": "旺來台股情報站", "url": SOURCE_URL, "method": "daily_public_page_topics_and_original_links"},
        "checkedAt": now.isoformat(timespec="seconds"),
        "reportDate": report_date,
        "storyCount": len(refs),
        "categoryCounts": categories,
        "themes": themes,
        "references": refs[:24],
        "interpretation": "JEI 自行依新聞分類與關鍵字整理的市場觀察入口；非該站原文摘要、非個股推薦。需回到原始報導及官方行情查證。",
    }


def main() -> None:
    data = analyze_html(fetch_page())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "updated", "reportDate": data["reportDate"], "stories": data["storyCount"], "themes": [x["id"] for x in data["themes"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
