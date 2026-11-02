#!/usr/bin/env python3
"""Fail-closed JEI feed freshness/coverage smoke test; no dependencies."""
import json
import sys
from math import isfinite
from pathlib import Path

def check(feed):
    market = feed.get("market") or {}
    if not isinstance(market, dict):
        market = {}
    diag = market.get("live_diagnostics") or {}
    if not isinstance(diag, dict):
        diag = {}
    stats = diag.get("mis_stats") or {}
    if not isinstance(stats, dict):
        stats = {}
    partial = market.get("partial_live") or {}
    if not isinstance(partial, dict):
        partial = {}
    issues = []
    def metric(values, key, default, *, whole=False, positive=False, maximum=None):
        raw = values.get(key)
        if raw is None:
            return default
        try:
            if isinstance(raw, bool):
                raise ValueError()
            value = float(raw)
            if (not isfinite(value) or value < 0 or (positive and value == 0)
                    or (maximum is not None and value > maximum)
                    or (whole and not value.is_integer())):
                raise ValueError()
            return int(value) if whole else value
        except (TypeError, ValueError, OverflowError):
            issues.append("invalid diagnostic metric: " + key)
            return default

    count = metric(partial, "verified_count", 0, whole=True)
    coverage = metric(partial, "coverage_pct", 0, maximum=100)
    required = metric(diag, "required_trades", 500, whole=True, positive=True)
    min_pct = metric(diag, "required_coverage_pct", 35, positive=True, maximum=100)
    returned = metric(stats, "returned_messages", 0, whole=True)
    missing = metric(stats, "missing_last_trade", 0, whole=True)
    if diag.get("market_open") and diag.get("quote_refresh_window"):
        if count < required or coverage < min_pct:
            issues.append(f"live coverage insufficient: {count} trades / {coverage}% (minimum {required} / {min_pct}%)")
        if market.get("live_valid") and (count < required or coverage < min_pct):
            issues.append("live_valid incorrectly true")
        if market.get("mode") == "今日收盤" and not market.get("historical_readonly"):
            issues.append("close-mode data not marked historical")
    if missing > returned:
        issues.append("MIS missing count exceeds returned messages")
    if returned and missing:
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
