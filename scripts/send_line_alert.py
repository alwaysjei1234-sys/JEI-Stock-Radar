#!/usr/bin/env python3
"""Optional public-market LINE intraday alerts; no private holdings or orders.

Runs only after the regular market feed refresh. Defaults OFF until a separate
repository variable explicitly enables these extra notifications.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from scripts.send_line_brief import TAIPEI, can_send, push

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "remote" / "system.json"


def trusted_live(feed, now):
    """Only a broad, same-day, recent TWSE/TPEx trade-session snapshot qualifies."""
    if now.tzinfo is None:
        return False
    local = now.astimezone(TAIPEI)
    minute = local.hour * 60 + local.minute
    m = feed.get("market") if isinstance(feed, dict) else None
    if not isinstance(m, dict) or local.weekday() > 4 or not 540 <= minute < 810:
        return False
    if (feed.get("data_date") != local.date().isoformat()
            or m.get("mode") != "盤中即時"
            or m.get("stale") is not False
            or m.get("live_valid") is not True):
        return False
    count = m.get("live_count")
    if isinstance(count, bool) or not isinstance(count, (int, float)) or count < 500:
        return False
    try:
        stamp = datetime.strptime(str(feed.get("updated_at") or ""), "%Y-%m-%d %H:%M").replace(tzinfo=TAIPEI)
    except ValueError:
        return False
    lag = (local - stamp).total_seconds()
    return -120 <= lag <= 35 * 60


def build_alert(feed, now):
    """Return one verified, dated watch alert; never label it a trade signal."""
    if not trusted_live(feed, now):
        return None
    risk = feed.get("risk") or {}
    score = risk.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 100:
        return None
    day = now.astimezone(TAIPEI).date().isoformat()
    note = "交易所盤中行情已驗證；提醒非即時下單指示，勿憑此訊息追價。"
    reasons = [str(v)[:125] for v in (risk.get("reasons") or [])[:3] if isinstance(v, str)]
    if risk.get("level") == "red" and score >= 75:
        return {
            "date": day, "edition": "intraday_risk", "status": "ready",
            "title": "🔴 JEI 台股盤中高風險警報",
            "note": note,
            "blocks": [
                {"title": "大盤風險", "items": [f"警戒分數 {score}/100｜{str(risk.get('label') or '高風險')[:30]}", *reasons]},
                {"title": "應對方式", "items": ["優先檢查持股曝險與價格；這不是自動賣出指令。"]},
            ],
            "report_url": "https://jei-stock-radar.vercel.app/",
        }
    # The momentum watch is informational, not proof of an imminent limit-up.
    if score >= 60:
        return None
    picks = []
    for x in feed.get("monster") or []:
        if not isinstance(x, dict):
            continue
        code, name = str(x.get("code") or ""), str(x.get("name") or "")
        grade, change, price = x.get("score"), x.get("change_pct"), x.get("price")
        if (not re.fullmatch(r"[0-9]{4,6}", code) or
                any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (grade, change, price))):
            continue
        if grade >= 95 and 4 <= change <= 10 and price > 0:
            picks.append(f"{code} {name[:20]}｜動能評分 {grade}｜盤中 {change:+.2f}%｜價格 {price:.2f}")
    if not picks:
        return None
    return {
        "date": day, "edition": "intraday_momentum", "status": "ready",
        "title": "🔥 JEI 盤中強勢股觀察",
        "note": note,
        "blocks": [
            {"title": "異動觀察（非漲停預測）", "items": picks[:3]},
            {"title": "風險提醒", "items": ["僅代表有足夠行情覆蓋下的動能篩選，不保證成交、上漲或漲停。"]},
        ],
        "report_url": "https://jei-stock-radar.vercel.app/",
    }


def main():
    now = datetime.now(TAIPEI)
    if os.getenv("JEI_LINE_ALERTS_ENABLED", "").lower() != "true":
        print("JEI 盤中 LINE 額外警報尚未啟用；沒有發送")
        return
    token, recipient = os.getenv("JEI_LINE_CHANNEL_ACCESS_TOKEN", ""), os.getenv("JEI_LINE_USER_ID", "")
    if os.getenv("JEI_LINE_ENABLED", "").lower() != "true" or not token or not recipient:
        print("JEI LINE 總開關或憑證尚未設定；沒有發送")
        return
    try:
        feed = json.loads(FEED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("JEI 行情快照不可讀；沒有發送")
        return
    report = build_alert(feed, now)
    if not report:
        print("盤中異動未達高可信警戒門檻，或有效盤中行情不足；沒有發送")
        return
    edition = report["edition"]
    ok, msg = can_send(report, edition, now, "true", token, recipient)
    if not ok:
        print("發送條件不合格："+msg)
        return
    # Keep independent daily de-duplication buckets: a momentum watch must NOT
    # silence a later crash warning. At most one of each edition per day.
    print(push(report, edition, token, recipient))


if __name__ == "__main__":
    main()
