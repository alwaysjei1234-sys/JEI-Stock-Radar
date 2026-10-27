"""Fail closed when a market-feed refresh carries yesterday's holiday label.

This checks status semantics only; it never treats a partial MIS sample as an
official TWSE/TPEx close or manufactures trading signals.
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from scripts.market_sessions import closure_reason
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    from market_sessions import closure_reason


def validate_session(feed, today):
    if not isinstance(feed, dict):
        raise ValueError("Feed must be a JSON object")
    market = feed.get("market")
    if not isinstance(market, dict):
        raise ValueError("Missing market status")
    summary = str(feed.get("summary") or "")
    brief = str(market.get("brief") or "")
    data_date = str(feed.get("data_date") or "")
    if not data_date or not feed.get("updated_at"):
        raise ValueError("Missing feed dates")
    closure = closure_reason(today)
    if closure:
        if market.get("session_status") != "休市":
            raise ValueError("Official closure must be labeled 休市")
    else:
        if market.get("session_status") == "休市" or "今日休市" in summary or "今日休市" in brief:
            raise ValueError("Stale holiday label carried into an open trading date")
        if market.get("next_expected_session") == today.isoformat():
            raise ValueError("Today's session cannot still be labeled as the next session")
    if data_date != today.isoformat():
        if market.get("stale") is not True or market.get("historical_readonly") is not True:
            raise ValueError("Historical prices must be marked stale and read-only")
        if market.get("mode") == "今日收盤":
            raise ValueError("Historical prices cannot be today's close")
        if (feed.get("risk") or {}).get("actionable") is True:
            raise ValueError("Historical market risk cannot be actionable")
    return True


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "remote/system.json")
    feed = json.loads(path.read_text(encoding="utf-8"))
    today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    validate_session(feed, today)
    print(f"Session validation OK: {today.isoformat()}, data_date={feed['data_date']}")


if __name__ == "__main__":
    main()
