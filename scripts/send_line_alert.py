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


def live_gate_reasons(feed, now):
    """Explain every fail-closed reason that blocks intraday LINE alerts."""
    reasons = []
    if now.tzinfo is None:
        return ["系統時間缺少時區"]
    local = now.astimezone(TAIPEI)
    minute = local.hour * 60 + local.minute
    m = feed.get("market") if isinstance(feed, dict) else None
    if not isinstance(m, dict):
        return ["缺少市場診斷資料"]
    if local.weekday() > 4 or not 540 <= minute < 810:
        reasons.append("目前不在台股盤中時段")
    if feed.get("data_date") != local.date().isoformat():
        reasons.append(f"行情資料日 {feed.get('data_date') or '缺漏'} 與今天不同")
    if m.get("mode") != "盤中即時":
        reasons.append(f"行情狀態為 {m.get('mode') or '缺漏'}，不是盤中即時")
    if m.get("stale") is not False:
        reasons.append("市場資料標記為過期或未驗證")
    if m.get("live_valid") is not True:
        reasons.append("盤中行情尚未通過有效性驗證")
    count = m.get("live_count")
    if isinstance(count, bool) or not isinstance(count, (int, float)):
        reasons.append("有效成交檔數缺漏")
    elif count < 500:
        reasons.append(f"有效成交 {int(count)}/500 檔，覆蓋未達門檻")
    try:
        stamp = datetime.strptime(str(feed.get("updated_at") or ""), "%Y-%m-%d %H:%M").replace(tzinfo=TAIPEI)
    except ValueError:
        reasons.append("行情更新時間缺漏或格式錯誤")
    else:
        lag = (local - stamp).total_seconds()
        if lag < -120:
            reasons.append("行情更新時間晚於系統時間")
        elif lag > 35 * 60:
            reasons.append(f"行情更新已延遲 {int(lag // 60)} 分鐘")
    return reasons


def trusted_live(feed, now):
    """Only a broad, same-day, recent TWSE/TPEx trade-session snapshot qualifies."""
    return not live_gate_reasons(feed, now)


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
    reasons = live_gate_reasons(feed, now)
    if reasons:
        print("LINE 盤中警報未送出：" + "；".join(reasons[:6]))
        return
    report = build_alert(feed, now)
    if not report:
        print("行情已通過盤中驗證；本次未達高可信警報條件，沒有發送")
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
