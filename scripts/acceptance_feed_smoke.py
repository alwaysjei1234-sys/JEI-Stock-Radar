#!/usr/bin/env python3
"""Read-only JEI remote feed acceptance smoke test. Python standard library only."""
import json
import pathlib
import re
import sys
from datetime import date, datetime
ROOT = pathlib.Path(__file__).resolve().parents[1]
ERRORS = []
def check(ok, msg):
    print(("PASS" if ok else "FAIL") + " " + msg)
    if not ok:
        ERRORS.append(msg)
def load(path):
    try:
        return json.loads((ROOT / path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        ERRORS.append(f"{path}: {exc}")
        return {}
feed = load("remote/system.json")
update = load("remote/update.json")
ui = ROOT / "remote/index.html"
check(ui.is_file() and ui.stat().st_size > 1000, "Remote UI exists and is nonempty")
data_date = feed.get("data_date", "")
try:
    observed = date.fromisoformat(data_date)
    check(observed <= date.today(), "Market data date is not in the future")
except (ValueError, TypeError):
    check(False, "Market data date parses as ISO date")
market = feed.get("market", {})
check(isinstance(market, dict), "Market block exists")
check(market.get("last_checked_at") is not None, "Feed carries separate last checked time")
if data_date and market.get("last_checked_at"):
    try:
        checked = datetime.strptime(market["last_checked_at"], "%Y-%m-%d %H:%M")
        check(checked.date() >= date.fromisoformat(data_date), "Last check is not older than market data")
    except (ValueError, TypeError):
        check(False, "Last checked timestamp is parseable")
check(isinstance(feed.get("risk", {}).get("score"), (int, float)), "Risk score numeric")
check(isinstance(update.get("versionCode"), int) and update["versionCode"] > 0, "Android versionCode valid")
check(bool(re.fullmatch(r"https://[^\s]+\.apk", str(update.get("url", "")))), "APK update URL is HTTPS APK")
check("github.com/alwaysjei1234-sys/JEI-Stock-Radar/" in str(update.get("url", "")), "APK points to official repository")
check(not any(k in feed for k in ("api_key", "access_token", "line_token", "holdings_cost")), "No obvious top-level secrets/private holdings in public feed")
print(f"Acceptance smoke test: {len(ERRORS)} failure(s).")
sys.exit(1 if ERRORS else 0)
