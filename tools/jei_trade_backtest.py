"""Evidence-only out-of-sample trade evaluator. No quotes are downloaded or invented.

CSV columns: strategy_id,ticker,entry_date,exit_date,gross_return,regime,split.
gross_return is decimal fraction (e.g. 0.03 means +3%), not percent.
Only rows marked split=oos count toward promotion evidence.
The unleveraged simulation caps net losses at the allocated trade capital.
Portfolio compounding and drawdown are unavailable if trade holding periods overlap
without capital allocation weights; trade-level metrics remain available.
"""
import argparse
import csv
import datetime as dt
from itertools import groupby
import json
import math
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
            net = max(-1.0, gross - round_trip_cost)
            evaluated.setdefault(row["strategy_id"], []).append(
                (start, end, net, row["regime"]))
    output = {}
    for name, trades in evaluated.items():
        trades.sort(key=lambda x: x[1])
        returns = [ret for _, _, ret, _ in trades]
        # A strategy holding multiple positions requires capital allocation data
        # to derive portfolio equity. Never multiply each overlapping trade as
        # if it had the full account balance invested.
        latest_end = dt.date.min
        has_overlapping_positions = False
        for start, end, _, _ in sorted(trades, key=lambda row: (row[0], row[1])):
            if start < latest_end:
                has_overlapping_positions = True
            latest_end = max(latest_end, end)
        if has_overlapping_positions:
            max_dd = None
            compounded_return = None
            drawdown_basis = "unavailable_overlapping_positions_without_capital_weights"
        else:
            equity, peak, max_dd = 1.0, 1.0, 0.0
            for _, closed in groupby(trades, key=lambda trade: trade[1]):
                equity *= math.prod(1 + ret for _, _, ret, _ in closed)
                peak = max(peak, equity)
                max_dd = max(max_dd, (peak - equity) / peak)
            compounded_return = equity - 1
            drawdown_basis = "full_capital_reinvested_nonoverlapping_trades_by_exit_date"
        output[name] = {
            "oos_trades": len(returns),
            "market_regimes": len({regime for _, _, _, regime in trades if regime}),
            "net_expectancy": statistics.mean(returns),
            "win_rate": sum(ret > 0 for ret in returns) / len(returns),
            "max_drawdown": max_dd,
            "drawdown_basis": drawdown_basis,
            "net_compounded_return": compounded_return,
            "cost_per_round_trip": round_trip_cost,
            "note": "Trade-level OOS metrics only; overlapping positions need capital weights for portfolio performance; no proof of walk-forward, data integrity or no lookahead"}
    return output

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trades", required=True)
    parser.add_argument("--cost", required=True, type=float)
    parser.add_argument("--out", default="evolution-output/oos-metrics.json")
    args = parser.parse_args()
    try:
        with open(args.trades, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, strict=True)
            columns = reader.fieldnames or []
            if len(set(columns)) != len(columns):
                raise ValueError("duplicate_csv_columns")
            rows = []
            for row in reader:
                if None in row or None in row.values():
                    raise ValueError(f"invalid_csv_row_{reader.line_num}")
                rows.append(row)
        if not rows:
            raise ValueError("empty_trade_data")
        metrics = evaluate(rows, args.cost)
        result = {"status": "CALCULATED" if metrics else "INSUFFICIENT_EVIDENCE",
                  "metrics": metrics,
                  "source": args.trades, "lookahead_verified": False,
                  "walk_forward_verified": False}
        if not metrics:
            result["reason"] = "no_oos_trades"
    except (OSError, csv.Error, ValueError, KeyError, ZeroDivisionError) as exc:
        result = {"status": "REJECT", "reason": str(exc), "metrics": {}}
    path = pathlib.Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "CALCULATED" else 1

if __name__ == "__main__":
    sys.exit(main())
