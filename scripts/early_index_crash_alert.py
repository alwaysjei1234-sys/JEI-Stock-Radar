#!/usr/bin/env python3
"""Fast, independent TWSE index crash siren (not a broad-market risk score).

Reuses JEI's dated, execution-price-only MIS TAIEX identity validator.
Never infer today's index move from yesterday's close or bid/ask quotations.
This early warning does not verify market breadth or individual holdings.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path

from scripts.market_sessions import closure_reason
from scripts.send_line_brief import TAIPEI, can_send, push
from scripts.update_system import fetch_mis_channels, mis_index_change

# One independently verified TAIEX value is enough for an EARLY INDEX warning;
# the broad-market red score still requires >=500 current stock trades and 35%.
INDEX_CRASH_THRESHOLD_PCT = -2.0
# Separate LINE retry-key buckets allow one additional notification at each
# *worsening* crash threshold. No more than three tiers per trading date.
INDEX_ESCALATION_THRESHOLD_PCT = -4.0
INDEX_EXTREME_THRESHOLD_PCT = -6.0
INDEX_CHANNEL = "tse_t00.tw"


def report_for_index(messages, now):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timestamp must have timezone")
    local = now.astimezone(TAIPEI)
    minute = local.hour * 60 + local.minute
    if local.weekday() > 4 or closure_reason(local.date()) is not None or not 540 <= minute < 810:
        return None, "market_closed_or_outside_window"
    pct, status = mis_index_change(messages, local)
    if status != "verified" or pct is None:
        return None, "index_" + status
    if pct > INDEX_CRASH_THRESHOLD_PCT:
        return None, "decline_below_threshold"
    day = local.date().isoformat()
    # The LINE sender deduplicates by date and edition. With a single fixed
    # edition, an accepted -2% notice silently suppresses a later -4%/-6%
    # escalation. The threshold tier is therefore part of the edition.
    # Never invent broader market confirmation from this single-index signal.
    if pct <= INDEX_EXTREME_THRESHOLD_PCT:
        edition, threshold = "intraday_index_crash_6pct", 6
    elif pct <= INDEX_ESCALATION_THRESHOLD_PCT:
        edition, threshold = "intraday_index_crash_4pct", 4
    else:
        edition, threshold = "intraday_index_crash", 2
    return {
        "date": day, "edition": edition, "status": "ready",
        "title": "🚨 JEI 台股加權指數快速急跌預警",
        "note": "獨立 TWSE MIS 加權指數即時報價已驗證；全市場廣度和個股尚未獨立驗證，不代表實際下單指令。",
        "blocks": [
            {"title": "加權指數快速警示", "items": [
                f"已驗證加權指數相對昨收 {pct:.2f}%",
                f"盤中已達 -{threshold}% 急跌門檻；留意槓桿、持股風險與快速擴大的賣壓。"]},
            {"title": "驗證邊界", "items": [
                "僅加權指數單一獨立來源，尚非全市場股票廣度紅燈。",
                "請查看 JEI 系統更新後的廣度、流動性與持股防守分級。"]},
        ],
        "report_url": "https://jei-stock-radar.vercel.app/",
    }, "verified_index_decline"


def dispatch(now, receipt):
    """Send only an eligible, dated, confirmed index warning; record skip reason."""
    if os.getenv("JEI_LINE_ALERTS_ENABLED", "").lower() != "true":
        receipt.update(status="disabled", reason_code="alerts_disabled")
        return
    token = os.getenv("JEI_LINE_CHANNEL_ACCESS_TOKEN", "")
    recipient = os.getenv("JEI_LINE_USER_ID", "")
    if os.getenv("JEI_LINE_ENABLED", "").lower() != "true" or not token or not recipient:
        receipt.update(status="blocked", reason_code="master_switch_or_credentials")
        return
    try:
        messages = fetch_mis_channels([INDEX_CHANNEL])
    except (OSError, ValueError, TimeoutError):
        receipt.update(status="unverified", reason_code="index_source_unavailable")
        return
    report, reason = report_for_index(messages, now)
    if report is None:
        receipt.update(status="no_alert", reason_code=reason)
        return
    receipt["edition"] = report["edition"]
    ok, why = can_send(report, report["edition"], now, "true", token, recipient)
    if not ok:
        receipt.update(status="blocked", reason_code="dispatch_gate")
        return
    result = push(report, report["edition"], token, recipient, receipt=receipt)
    if receipt.get("status") not in ("accepted", "already_accepted"):
        raise RuntimeError("LINE index warning acceptance not verified")
    print(result)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-path", type=Path)
    args = parser.parse_args(argv)
    now = datetime.now(TAIPEI)
    receipt = {
        "date": now.date().isoformat(), "edition": "intraday_index",
        "checked_at": now.isoformat(timespec="seconds"),
        "status": "failed", "delivery_confirmed": False,
    }
    try:
        dispatch(now, receipt)
        print(json.dumps({k: receipt.get(k) for k in
                          ("date", "edition", "status", "reason_code")},
                         ensure_ascii=False))
    except (ValueError, TypeError, AttributeError, OSError, RuntimeError) as error:
        receipt["status"] = "failed"
        receipt["error_type"] = type(error).__name__
        raise SystemExit("快速指數警報未確認被接受（" + type(error).__name__ + "）") from None
    finally:
        if args.result_path:
            args.result_path.parent.mkdir(parents=True, exist_ok=True)
            args.result_path.write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")


if __name__ == "__main__":
    main()
