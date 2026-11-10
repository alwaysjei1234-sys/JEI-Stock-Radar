"""Explicit, dated LINE test using existing opt-in, free quota and retry guards."""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from scripts import send_line_brief as line


def verify(expected_day, now, enabled, token, recipient):
    now = now.astimezone(line.TAIPEI)
    receipt = {"date": now.date().isoformat(), "edition": "test",
               "checked_at": now.isoformat(timespec="seconds"),
               "status": "blocked", "api_accepted": False,
               "delivery_confirmed": False}
    if expected_day != receipt["date"]:
        receipt["reason"] = "test_date_mismatch"
        return receipt
    report = {"date": receipt["date"], "edition": "test", "status": "ready",
              "title": "【JEI｜LINE 連線測試】",
              "note": "這是一次連線測試，不含行情、持股或交易建議。",
              "blocks": [{"title": "驗證範圍", "items": [
                  "API 接受請求不等於手機已收到；系統仍保留實收未確認。"]}],
              "report_url": "https://jei-stock-radar.vercel.app/remote/brief.html"}
    allowed, _ = line.can_send(report, "test", now, enabled, token, recipient)
    if not allowed:
        receipt["reason"] = "configuration_disabled_or_invalid"
        return receipt
    internal = {}
    try:
        line.push(report, "test", token, recipient, receipt=internal)
    except (OSError, ValueError, RuntimeError) as error:
        receipt["error_type"] = type(error).__name__
        internal.setdefault("status", "failed")
    # Never retain request identifiers, response bodies, profiles or credentials.
    for key in ("status", "stage", "http_status", "attempts"):
        if key in internal:
            receipt[key] = internal[key]
    receipt["api_accepted"] = receipt["status"] in ("accepted", "already_accepted")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-day", required=True)
    parser.add_argument("--result-path", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.expected_day, datetime.now(line.TAIPEI),
                    os.getenv("JEI_LINE_ENABLED", ""),
                    os.getenv("JEI_LINE_CHANNEL_ACCESS_TOKEN", ""),
                    os.getenv("JEI_LINE_USER_ID", ""))
    args.result_path.parent.mkdir(parents=True, exist_ok=True)
    args.result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["api_accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
