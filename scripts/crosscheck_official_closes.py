"""Read-only TWSE daily-close consistency check against dated STOCK_DAY pulls.

Both sources originate at TWSE; matching them is NOT independent market
confirmation and never upgrades stale or partial live quotes to actionable.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import date
from pathlib import Path


def compare_archive(daily: dict, snapshots: list[dict]) -> dict:
    if not isinstance(daily, dict) or daily.get("schema") != 1 or daily.get("kind") != "official_daily_close":
        raise ValueError("invalid official daily close archive")
    days = daily.get("days")
    if not isinstance(days, dict):
        raise ValueError("missing dated archive")
    for day, prices in days.items():
        if date.fromisoformat(day).isoformat() != day or not isinstance(prices, dict):
            raise ValueError("invalid archive day or prices")
    checked, missing, conflicts, observed = 0, 0, [], {}
    for snap in snapshots:
        if not isinstance(snap, dict) or snap.get("market") != "TWSE":
            raise ValueError("snapshot is not TWSE")
        if snap.get("source") != "TWSE STOCK_DAY fetched via HTTPS; corporate actions not adjusted":
            raise ValueError("unrecognized source provenance")
        if snap.get("adjusted_for_corporate_actions") is not False:
            raise ValueError("incompatible adjusted/unadjusted prices")
        code = snap.get("code")
        if not isinstance(code, str) or not re.fullmatch(r"[0-9]{4,6}", code):
            raise ValueError("invalid TWSE stock code")
        prices = snap.get("prices")
        if not isinstance(prices, list) or not prices:
            raise ValueError("missing dated STOCK_DAY prices")
        for row in prices:
            if not isinstance(row, dict) or not isinstance(row.get("date"), str):
                raise ValueError("invalid dated price row")
            day = row["date"]
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError("invalid STOCK_DAY date")
            price = row.get("close")
            if type(price) not in (int, float) or not math.isfinite(price) or price <= 0:
                raise ValueError("invalid STOCK_DAY close")
            key = (code, day)
            if key in observed:
                if abs(observed[key] - price) > 0.00001:
                    raise ValueError("conflicting duplicate STOCK_DAY observation")
                continue
            observed[key] = price
            if day not in days:
                continue  # different session; never compare across dates
            saved = days[day].get(code)
            if saved is None:
                missing += 1
                continue
            if type(saved) not in (int, float) or not math.isfinite(saved) or saved <= 0:
                raise ValueError("invalid stored official close")
            checked += 1
            if abs(float(saved) - float(price)) > 0.005:
                conflicts.append({"code": code, "date": day,
                                  "archive_close": saved, "stock_day_close": price})
    return {
        "ok": checked > 0 and not conflicts,
        "status": ("conflict" if conflicts else "no_overlap" if checked == 0 else "consistent"),
        "checked_count": checked,
        "missing_in_archive": missing,
        "conflicts": conflicts,
        "read_only": True,
        "same_exchange_not_independent": True,
        "live_trading_verified": False,
        "upgrades_live_valid": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare saved TWSE dates; no network, no ledger writes")
    parser.add_argument("--daily", type=Path, default=Path("remote/daily_prices.json"))
    parser.add_argument("--snapshots", type=Path, nargs="+", required=True)
    args = parser.parse_args()
    try:
        daily = json.loads(args.daily.read_text(encoding="utf-8"))
        snaps = [json.loads(path.read_text(encoding="utf-8")) for path in args.snapshots]
        result = compare_archive(daily, snaps)
    except (ValueError, TypeError, OSError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "status": "invalid_input",
                          "error": type(exc).__name__}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
