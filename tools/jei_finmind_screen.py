"""Fail-closed JEI screen for independently sourced Taiwan market CSV exports.

CSV schema:
ticker,sector,trade_date,close,ma60,trust_buy_shares_20d,revenue_yoy_pct,revenue_publish_date
All figures are explicit: trust shares are shares, not lots; revenue growth is percent.
Only source records already published as of trade_date are eligible.
"""
import argparse
import csv
import datetime as dt
import json
import pathlib
import sys

FIELDS = {"ticker", "sector", "trade_date", "close", "ma60",
          "trust_buy_shares_20d", "revenue_yoy_pct", "revenue_publish_date"}

def screen(rows, as_of):
    cutoff = dt.date.fromisoformat(as_of)
    accepted, rejected = [], []
    for index, row in enumerate(rows, 2):
        ticker = str(row.get("ticker", "")).strip()
        try:
            if not FIELDS.issubset(row):
                raise ValueError("missing_columns")
            date = dt.date.fromisoformat(row["trade_date"])
            publish = dt.date.fromisoformat(row["revenue_publish_date"])
            if date > cutoff or publish > date:
                raise ValueError("future_or_unpublished_data")
            close = float(row["close"])
            ma60 = float(row["ma60"])
            shares = float(row["trust_buy_shares_20d"])
            yoy = float(row["revenue_yoy_pct"])
            if not all(map(__import__("math").isfinite, [close, ma60, shares, yoy])):
                raise ValueError("non_finite_values")
            if close <= 0 or ma60 <= 0:
                raise ValueError("invalid_price")
            if row["sector"].strip() not in {"金融", "金融保險", "Financials"}:
                continue
            if shares > 5_000_000 and yoy > 20 and close < ma60:
                accepted.append({"ticker": ticker, "trade_date": row["trade_date"],
                                 "trust_buy_lots_20d": shares / 1000,
                                 "revenue_yoy_pct": yoy, "close": close, "ma60": ma60})
        except (ValueError, TypeError, KeyError) as exc:
            rejected.append({"row": index, "ticker": ticker, "reason": str(exc)})
    return {"status": "REVIEW_REQUIRED", "as_of": as_of, "matches": accepted,
            "rejected_rows": rejected, "notes": [
                "Requires externally validated 20-trading-day trust flows and 60-session MA",
                "Inputs are not independently verified and no live recommendation is implied",
                "Strict >5000 lots, >20 percent and close < MA60"]}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True)
    p.add_argument("--as-of", required=True)
    p.add_argument("--output", default="evolution-output/finmind-screen.json")
    args = p.parse_args()
    try:
        with open(args.csv, newline="", encoding="utf-8-sig") as f:
            result = screen(list(csv.DictReader(f)), args.as_of)
    except (OSError, ValueError) as exc:
        result = {"status": "REJECT", "reason": str(exc), "matches": []}
    path = pathlib.Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] != "REJECT" else 1

if __name__ == "__main__":
    sys.exit(main())
