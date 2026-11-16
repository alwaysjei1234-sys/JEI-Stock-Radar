"""Independent fail-closed watchdog for missed JEI feed refresh jobs.

The scheduled primary 5-minute workflow is best effort on GitHub Actions.
This watchdog only decides whether a second workflow should actually rebuild.
A fresh *check timestamp* is not proof of valid live trades.
"""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.market_sessions import closure_reason

TAIPEI = ZoneInfo("Asia/Taipei")
MAX_CHECK_LAG = timedelta(minutes=16)
MAX_CLOCK_LEAD = timedelta(minutes=2)


def assess(feed, now, max_lag=MAX_CHECK_LAG):
    """Return (recover, reason). Outside expected monitoring hours is NO-OP."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("watchdog clock requires timezone")
    local = now.astimezone(TAIPEI)
    minute = local.hour * 60 + local.minute
    if closure_reason(local.date()) is not None:
        return False, "verified_exchange_closure"
    if not 510 <= minute < 1200:  # 08:30–19:59, before first scheduled build through close
        return False, "outside_refresh_window"
    if not isinstance(feed, dict):
        return True, "invalid_system_json"
    market = feed.get("market")
    if not isinstance(market, dict):
        return True, "missing_market_metadata"
    stamp = market.get("status_updated_at") or market.get("last_checked_at")
    if not isinstance(stamp, str):
        return True, "missing_verified_feed_check_timestamp"
    try:
        checked = datetime.strptime(stamp, "%Y-%m-%d %H:%M").replace(tzinfo=TAIPEI)
    except ValueError:
        return True, "invalid_verified_feed_check_timestamp"
    age = local - checked
    if age < -MAX_CLOCK_LEAD:
        return True, "future_dated_feed_check_timestamp"
    if checked.date() != local.date():
        return True, "feed_last_checked_on_previous_day"
    if age > max_lag:
        return True, f"feed_check_stalled_{int(age.total_seconds()//60)}m"
    return False, f"feed_check_recent_{max(0,int(age.total_seconds()//60))}m"


def load_feed(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("remote/system.json"))
    parser.add_argument("--output", type=Path, help="GitHub Actions GITHUB_OUTPUT")
    parser.add_argument("--expect-fresh", action="store_true",
                        help="Fail after attempted recovery if even its check time is stale")
    parser.add_argument("--at", type=str, help="ISO 8601 test clock, never used by Actions")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.at) if args.at else datetime.now(TAIPEI)
    needed, reason = assess(load_feed(args.input), now)
    print(f"JEI market-feed watchdog: recover={str(needed).lower()}, reason={reason}")
    if args.output:
        with args.output.open("a", encoding="utf-8") as f:
            f.write(f"recover={str(needed).lower()}\nreason={reason}\n")
    return 1 if args.expect_fresh and needed else 0


if __name__ == "__main__":
    raise SystemExit(main())
