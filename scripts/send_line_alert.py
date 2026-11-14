#!/usr/bin/env python3
"""Optional public-market LINE intraday alerts; no private holdings or orders.

Runs only after the regular market feed refresh. Defaults OFF until a separate
repository variable explicitly enables these extra notifications.
"""
import argparse
import math
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from scripts.send_line_brief import TAIPEI, can_send, push

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "remote" / "system.json"


def is_whole_count(value):
    # Match the dashboard's safe-integer checks for JSON numbers.
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and 0 <= value <= 2**53 - 1 and value == int(value))


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
    if m.get("stale") is not False or m.get("historical_readonly") is True:
        reasons.append("市場資料標記為過期、唯讀或未驗證")
    if m.get("session_status") == "休市":
        reasons.append("交易所休市")
    if m.get("live_valid") is not True:
        reasons.append("盤中行情尚未通過有效性驗證")
    risk = feed.get("risk")
    if not isinstance(risk, dict):
        reasons.append("風控資料缺漏或格式錯誤")
    else:
        if risk.get("actionable") is False:
            reasons.append("行情風控明確暫停新判讀")
        if "as_of" in risk and risk["as_of"] != local.date().isoformat():
            reasons.append("風控資料日期與今天不同")
    if m.get("no_new_picks") is True or m.get("actionable") is False:
        reasons.append("市場明確暫停新判讀")
    count = m.get("live_count")
    total = m.get("close_count")
    if not is_whole_count(count):
        reasons.append("有效成交檔數缺漏")
    elif count < 500:
        reasons.append(f"有效成交 {int(count)}/500 檔，覆蓋未達門檻")
    elif not is_whole_count(total) or total < 500 or count > total:
        reasons.append("行情總檔數缺漏或與有效成交檔數矛盾")
    elif count * 100 < total * 35:
        reasons.append(f"有效成交 {int(count)}/{int(total)} 檔，覆蓋率低於 35%")
    try:
        stamp = datetime.strptime(str(feed.get("updated_at") or ""), "%Y-%m-%d %H:%M").replace(tzinfo=TAIPEI)
    except ValueError:
        reasons.append("行情更新時間缺漏或格式錯誤")
    else:
        if not 540 <= stamp.hour * 60 + stamp.minute < 810:
            reasons.append("行情快照時間不在台股盤中時段")
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
                any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (grade, change, price))):
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


def dispatch(now, receipt):
    """Keep every skip distinct from an API rejection or confirmed acceptance."""
    if os.getenv("JEI_LINE_ALERTS_ENABLED", "").lower() != "true":
        receipt.update(status="disabled", reason_code="alerts_disabled")
        print("JEI 盤中 LINE 額外警報尚未啟用；沒有發送")
        return
    token, recipient = os.getenv("JEI_LINE_CHANNEL_ACCESS_TOKEN", ""), os.getenv("JEI_LINE_USER_ID", "")
    if os.getenv("JEI_LINE_ENABLED", "").lower() != "true" or not token or not recipient:
        receipt.update(status="blocked", reason_code="master_switch_or_credentials")
        print("JEI LINE 總開關或憑證尚未設定；沒有發送")
        return
    try:
        feed = json.loads(FEED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        receipt.update(status="blocked", reason_code="feed_unreadable")
        print("JEI 行情快照不可讀；沒有發送")
        return
    reasons = live_gate_reasons(feed, now)
    if reasons:
        receipt.update(status="blocked", reason_code="live_gate")
        print("LINE 盤中警報未送出：" + "；".join(reasons[:6]))
        return
    report = build_alert(feed, now)
    if not report:
        receipt.update(status="no_alert", reason_code="conditions_not_met")
        print("行情已通過盤中驗證；本次未達高可信警報條件，沒有發送")
        return
    edition = report["edition"]
    receipt["edition"] = edition
    ok, msg = can_send(report, edition, now, "true", token, recipient)
    if not ok:
        receipt.update(status="blocked", reason_code="dispatch_gate")
        print("發送條件不合格："+msg)
        return
    # Keep independent daily de-duplication buckets: a momentum watch must NOT
    # silence a later crash warning. At most one of each edition per day.
    result = push(report, edition, token, recipient, receipt=receipt)
    print(result)
    if receipt.get("status") not in ("accepted", "already_accepted"):
        raise SystemExit("盤中 LINE 未確認接受；請查看結果紀錄")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-path", help="Write a credential-free API acceptance receipt")
    args = parser.parse_args(argv)
    now = datetime.now(TAIPEI)
    receipt = {"date": now.date().isoformat(), "edition": "intraday",
               "checked_at": now.isoformat(timespec="seconds"), "status": "failed",
               "delivery_confirmed": False}
    try:
        dispatch(now, receipt)
    except (OSError, ValueError, RuntimeError, TypeError, AttributeError) as error:
        # Never copy exception text, headers, payloads, environment or recipient.
        receipt["status"] = "failed"
        receipt["error_type"] = type(error).__name__
        raise SystemExit("盤中 LINE 失敗；請查看結果紀錄（" + type(error).__name__ + "）") from None
    finally:
        if args.result_path:
            output = Path(args.result_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
