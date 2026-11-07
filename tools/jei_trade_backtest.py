"""Evidence-only out-of-sample trade evaluator. No quotes are downloaded or invented.

CSV columns: strategy_id,ticker,entry_date,exit_date,gross_return,regime,split.
gross_return is decimal fraction (e.g. 0.03 means +3%), not percent.
Only rows marked split=oos count toward promotion evidence.
"""
import argparse
import csv
import datetime as dt
import json
import pathlib
import statistics
import sys

REQUIRED = {"strategy_id", "ticker", "entry_date", "exit_date", "gross_return", "regime", "split"}

def evaluate(rows, round_trip_cost):
    if not 0 <= round_trip_cost < 1:
        raise ValueError("invalid_round_trip_cost")
    seen = {}
    evaluated = {}
    for i, row in enumerate(rows, 2):
        if not REQUIRED.issubset(row):
            raise ValueError("missing_columns:" + ",".join(sorted(REQUIRED - set(row))))
        if row["split"] not in ("train", "oos"):
            raise ValueError("invalid_split_row_" + str(i))
        start, end = dt.date.fromisoformat(row["entry_date"]), dt.date.fromisoformat(row["exit_date"])
        if start >= end:
            raise ValueError("invalid_dates_row_" + str(i))
        gross = float(row["gross_return"])
        if not -1 <= gross <= 10:
            raise ValueError("implausible_return_row_" + str(i))
        key = (row["strategy_id"], row["ticker"])
        intervals = seen.setdefault(key, [])
        if any(start < prior_end and prior_start < end for prior_start, prior_end in intervals):
            raise ValueError("overlapping_trades_row_" + str(i))
        intervals.append((start, end))
        if row["split"] == "oos":
            evaluated.setdefault(row["strategy_id"], []).append(
                (end, gross - round_trip_cost, row["regime"]))
    output = {}
    for name, trades in evaluated.items():
        trades.sort(key=lambda x: x[0])
        returns = [r for _, r, _ in trades]
        equity, peak, max_dd = 1.0, 1.0, 0.0
        for ret in returns:
            equity *= (1 + ret)
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak)
        output[name] = {
            "oos_trades": len(returns),
            "market_regimes": len({regime for _, _, regime in trades if regime}),
            "net_expectancy": statistics.mean(returns),
            "win_rate": sum(ret > 0 for ret in returns) / len(returns),
            "max_drawdown": max_dd,
            "net_compounded_return": equity - 1,
            "cost_per_round_trip": round_trip_cost,
            "note": "Trade-level OOS metrics only; does not prove walk-forward, data integrity or no lookahead"}
    return output

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trades", required=True)
    parser.add_argument("--cost", required=True, type=float)
    parser.add_argument("--out", default="evolution-output/oos-metrics.json")
    args = parser.parse_args()
    try:
        with open(args.trades, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            raise ValueError("empty_trade_data")
        result = {"status": "CALCULATED", "metrics": evaluate(rows, args.cost),
                  "source": args.trades, "lookahead_verified": False,
                  "walk_forward_verified": False}
    except (OSError, ValueError, KeyError, ZeroDivisionError) as exc:
        result = {"status": "REJECT", "reason": str(exc), "metrics": {}}
    path = pathlib.Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "CALCULATED" else 1

if __name__ == "__main__":
    sys.exit(main())
