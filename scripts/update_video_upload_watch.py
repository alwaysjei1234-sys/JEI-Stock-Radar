#!/usr/bin/env python3
"""Read official public YouTube channel RSS feeds for a new-video review queue.

This stores upload titles, timestamps and video links only. It does not fetch
video streams, audio, captions or transcripts. Titles are a review queue, not a
summary or a recommendation.
"""
from __future__ import annotations

import concurrent.futures
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "remote" / "video_research_sources.json"
OUTPUT = ROOT / "remote" / "video_upload_watch.json"
USER_AGENT = "JEI-Stock-Radar/1.0 (public YouTube RSS metadata review queue)"
NS = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


def _fetch_channel(channel: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    url = channel.get("rssUrl")
    if not isinstance(url, str) or not url.startswith("https://www.youtube.com/feeds/videos.xml?channel_id="):
        raise ValueError("channel RSS URL is not an official YouTube feed")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    error: Exception | None = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                root = ET.fromstring(response.read())
            feed_id = root.findtext("atom:id", namespaces=NS) or ""
            expected = channel["channelId"]
            if feed_id and not feed_id.endswith(expected):
                raise ValueError(f"RSS channel id mismatch: expected yt:channel:{expected}, received {feed_id or '(missing)'}")
            videos: list[dict[str, str]] = []
            for entry in root.findall("atom:entry", NS)[:3]:
                video_id = entry.findtext("yt:videoId", namespaces=NS) or ""
                title = entry.findtext("atom:title", namespaces=NS) or ""
                published = entry.findtext("atom:published", namespaces=NS) or ""
                if not video_id or not title or not published:
                    continue
                videos.append({
                    "channelId": expected,
                    "channel": str(channel.get("name", "")),
                    "level": str(channel.get("level", "")),
                    "focus": str(channel.get("focus", "")),
                    "title": title.strip()[:240],
                    "publishedAt": published,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                })
            if not videos:
                raise ValueError("RSS returned no valid recent uploads")
            return channel, videos
        except Exception as exc:  # retry temporary feed/network errors
            error = exc
            if attempt < 1:
                time.sleep(1)
    raise RuntimeError(f"{channel.get('name', 'channel')}: {error}") from error


def refresh() -> dict[str, Any]:
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    channels = [c for c in sources.get("channels", []) if c.get("rssEnabled") and c.get("channelId")]
    if not channels:
        raise ValueError("no verified YouTube RSS channels configured")
    prior = {}
    if OUTPUT.exists():
        try:
            prior = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prior = {}
    results: list[tuple[dict[str, Any], list[dict[str, str]]]] = []
    failures: list[dict[str, str]] = []
    # Low concurrency keeps this a polite, once-a-day read of public RSS.
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_channel = {executor.submit(_fetch_channel, channel): channel for channel in channels}
        for future in concurrent.futures.as_completed(future_to_channel):
            channel = future_to_channel[future]
            try:
                results.append(future.result())
            except Exception as exc:
                failures.append({"channel": str(channel.get("name", "")), "error": str(exc)[:220]})
    successful = {channel["id"] for channel, _ in results}
    previous_rows = prior.get("videos", []) if isinstance(prior.get("videos"), list) else []
    previous_by_channel: dict[str, list[dict[str, Any]]] = {}
    for row in previous_rows:
        if isinstance(row, dict) and isinstance(row.get("channelId"), str):
            previous_by_channel.setdefault(row["channelId"], []).append(row)
    videos: list[dict[str, Any]] = []
    for channel, rows in results:
        videos.extend(rows)
    # If one public channel feed is temporarily unavailable, keep its last good metadata.
    for channel in channels:
        if channel["id"] not in successful:
            videos.extend(previous_by_channel.get(channel["id"], [])[:3])
    unique = {(item["channelId"], item["url"]): item for item in videos}
    ordered = sorted(unique.values(), key=lambda item: item.get("publishedAt", ""), reverse=True)
    return {
        "schemaVersion": 1,
        "checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sourceCount": len(channels),
        "successfulSourceCount": len(results),
        "failedSources": failures,
        "videos": ordered[:40],
        "policy": "公開 RSS metadata 索引；標題和發布時間只供找片，不是影片重點、已驗證事實或個股推薦。沒有抓取影片、音訊或字幕。",
    }


def main() -> None:
    data = refresh()
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "updated", "sources": data["sourceCount"], "successful": data["successfulSourceCount"], "videos": len(data["videos"]), "failed": len(data["failedSources"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
