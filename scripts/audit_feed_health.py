#!/usr/bin/env python3
"""Fail-closed JEI feed freshness/coverage smoke test; no dependencies."""
import json
import sys
from datetime import datetime
from pathlib import Path

def check(feed):
    market = feed.get("market", {})
    diag = market.get("live_diagnostics", {})
    stats = diag.get("mis_stats", {})
    partial = market.get("partial_live", {})
    count = int(partial.get("verified_count") or 0)
    coverage = float(partial.get("coverage_pct") or 0)
    required = int(diag.get("required_trades") or 500)
    min_pct = float(diag.get("required_coverage_pct") or 35)
    issues = []
    if diag.get("market_open") and diag.get("quote_refresh_window"):
        if count < required or coverage < min_pct:
            issues.append(f"live coverage insufficient: {count} trades / {coverage}% (minimum {required} / {min_pct}%)")
        if market.get("live_valid") and (count < required or coverage < min_pct):
            issues.append("live_valid incorrectly true")
        if market.get("mode") == "今日收盤" and not market.get("historical_readonly"):
            issues.append("close-mode data not marked historical")
    if int(stats.get("returned_messages") or 0) and int(stats.get("missing_last_trade") or 0):
        issues.append(f"MIS missing last trade: {stats['missing_last_trade']} messages")
    return issues

def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "remote/system.json")
    feed = json.loads(path.read_text(encoding="utf-8"))
    issues = check(feed)
    print("JEI market feed audit:", "PASS" if not issues else "DEGRADED")
    for issue in issues:
        print(" -", issue)
    return 1 if issues else 0

if __name__ == "__main__":
    raise SystemExit(main())
