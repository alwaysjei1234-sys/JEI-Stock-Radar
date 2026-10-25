#!/usr/bin/env python3
"""Refresh Gooaye source metadata only; do not copy podcast summaries or notes."""
from __future__ import annotations

import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any


RSS_URL = "https://feeds.soundon.fm/podcasts/954689a5-3096-43a4-a80b-7810b219cef3.xml"
APPLE_LOOKUP_URL = "https://itunes.apple.com/lookup?id=1500839292&entity=podcastEpisode&limit=20&country=TW"
SUMMARY_URL = "https://cocoboomboom.com/gooaye.html"
OUTPUT = Path(__file__).resolve().parents[1] / "remote" / "gooaye_watch.json"
USER_AGENT = "JEI-Stock-Radar/1.0 (public podcast feed metadata; contact: repository owner)"


def fetch(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as error:  # noqa: BLE001 - network failures are retried uniformly
            last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError(f"Could not fetch public source after retries: {url}: {last_error}") from last_error


def parse_summary_date(html: str) -> str | None:
    match = re.search(r"頁面更新\s*[：:]\s*(\d{4}-\d{2}-\d{2})", html)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1)).isoformat()
    except ValueError:
        return None


def parse_pub_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def parse_rss(payload: bytes, limit: int = 8) -> list[dict[str, Any]]:
    root = ET.fromstring(payload)
    channel = root.find("channel")
    if channel is None:
        raise ValueError("RSS channel is missing")
    episodes: list[dict[str, Any]] = []
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        published = parse_pub_date(item.findtext("pubDate"))
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link).strip()
        if not title or not published or not link.startswith("https://"):
            continue
        number = re.search(r"\bEP\s*(\d+)\b", title, re.IGNORECASE)
        episodes.append({
            "episode": f"EP{number.group(1)}" if number else "",
            "title": title[:240],
            "publishedAt": published,
            "url": link,
            "id": guid[:300],
        })
        if len(episodes) >= limit:
            break
    if not episodes:
        raise ValueError("RSS contains no valid episode metadata")
    return episodes


def enrich_episode_titles(episodes: list[dict[str, Any]], payload: bytes | None) -> list[dict[str, Any]]:
    """Use Apple's public catalog title field only; ignore descriptions and all promo text."""
    if not payload:
        return episodes
    try:
        catalog = json.loads(payload.decode("utf-8"))
        results = catalog.get("results", [])
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return episodes
    by_episode: dict[str, dict[str, Any]] = {}
    for row in results:
        if not isinstance(row, dict):
            continue
        name = str(row.get("trackName", "")).strip()
        match = re.search(r"\bEP\s*(\d+)\b", name, re.IGNORECASE)
        if not match:
            continue
        apple_url = str(row.get("trackViewUrl", ""))
        release_date = str(row.get("releaseDate", ""))[:10]
        by_episode[f"EP{match.group(1)}"] = {
            "title": name[:160],
            "appleUrl": apple_url if apple_url.startswith("https://") else None,
            "publishedAt": release_date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", release_date) else None,
        }
    result = []
    for episode in episodes:
        merged = dict(episode)
        apple = by_episode.get(str(episode.get("episode", "")))
        if apple:
            merged["title"] = apple["title"]
            if apple["appleUrl"]:
                merged["appleUrl"] = apple["appleUrl"]
            if apple["publishedAt"]:
                merged["publishedAt"] = apple["publishedAt"]
        result.append(merged)
    return result


def build_watch(rss_payload: bytes, page_payload: bytes, checked_at: datetime | None = None, apple_payload: bytes | None = None) -> dict[str, Any]:
    episodes = parse_rss(rss_payload)
    episodes = enrich_episode_titles(episodes, apple_payload)
    checked = (checked_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    page_date = parse_summary_date(page_payload.decode("utf-8", errors="replace"))
    return {
        "schemaVersion": 1,
        "checkedAt": checked.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "latestPublishedAt": episodes[0]["publishedAt"],
        "episodes": episodes,
        "summaryPage": {
            "url": SUMMARY_URL,
            "lastUpdated": page_date,
            "checked": page_date is not None,
            "termsUrl": "https://cocoboomboom.com/terms.html",
            "contentCopied": False,
        },
        "podcast": {
            "rssUrl": RSS_URL,
            "catalogUrl": APPLE_LOOKUP_URL,
            "publisher": "SoundOn RSS",
            "metadataOnly": True,
            "descriptionsStored": False,
            "transcriptsStored": False,
        },
        "notice": "僅索引公開集數標題、日期與原始連結；不儲存節目描述、逐字稿或第三方摘要，不代表主持人推薦個股。",
    }


def main() -> None:
    rss_payload = fetch(RSS_URL)
    page_payload = fetch(SUMMARY_URL)
    try:
        apple_payload = fetch(APPLE_LOOKUP_URL)
    except RuntimeError:
        apple_payload = None
    data = build_watch(rss_payload, page_payload, apple_payload=apple_payload)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated public podcast metadata: {len(data['episodes'])} episodes; summary date {data['summaryPage']['lastUpdated'] or 'unavailable'}")


if __name__ == "__main__":
    main()
