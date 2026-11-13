"""Research replay. Run from JEI root with Oct and Nov TWSE FMTQIK JSON paths."""
import argparse
from collections import Counter
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
import sys

sys.path.insert(0, str(Path.cwd()))
from scripts.corporate_actions import actions_between, validated_actions
from scripts.paper_evidence import wilson_interval

HORIZONS = (3, 7, 15, 30, 60)
FEE, TAX, SLIP = .001425, .003, .001


def index_closes(paths):
    closes = {}
    sources = []
    for path in paths:
        payload = path.read_bytes()
        data = json.loads(payload)
        assert data["stat"] == "OK"
        position = data["fields"].index("發行量加權股價指數")
        for row in data["data"]:
            year, month, day = map(int, row[0].split("/"))
            key = date(year + 1911, month, day).isoformat()
            assert key not in closes
            closes[key] = float(row[position].replace(",", ""))
        sources.append({
            "url": "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK"
                   f"?date={data['date'][:6]}01&response=json",
            "sha256": sha256(payload).hexdigest(), "rows": len(data["data"]),
        })
    return closes, sources


def measure(series, index_entry, index_exit):
    entry, exit_price = series[0], series[-1]
    denominator = entry * (1 + SLIP) * (1 + FEE)
    liquidated = [px * (1 - SLIP) * (1 - FEE - TAX) / denominator for px in series]
    peak, drawdown = 1.0, 0.0
    for value in liquidated:
        peak = max(peak, value)
        drawdown = max(drawdown, (peak - value) / peak)
    return {
        "gross": 100 * (exit_price / entry - 1),
        "net": 100 * (liquidated[-1] - 1),
        "benchmark": 100 * (index_exit / index_entry - 1),
        "trade_path_drawdown": 100 * drawdown,
    }


def summarize(rows):
    if not rows:
        return {"closed": 0, "metrics": None}
    wins = sum(row["net"] > 0 for row in rows)
    return {
        "closed": len(rows), "wins": wins,
        "net_win_rate_pct": round(100 * wins / len(rows), 3),
        "wilson_95_pct_descriptive": wilson_interval(wins, len(rows)),
        "mean_gross_pct": round(mean(r["gross"] for r in rows), 3),
        "mean_net_pct": round(mean(r["net"] for r in rows), 3),
        "mean_taiex_pct": round(mean(r["benchmark"] for r in rows), 3),
        "mean_excess_pp": round(mean(r["net"] - r["benchmark"] for r in rows), 3),
        "worst_single_trade_path_drawdown_pct": round(max(r["trade_path_drawdown"] for r in rows), 3),
    }


def replay(picks, archive, benchmark):
    market_days = sorted(benchmark)
    offsets = {day: i for i, day in enumerate(market_days)}
    stocks = archive["days"]
    actions = validated_actions(archive)
    unique = sorted({(p["day"], p["code"]) for p in picks})
    results = {}
    for horizon in HORIZONS:
        by_offset = {0: {}, 1: {}}
        coverage = {0: Counter(), 1: Counter()}
        for day, code in unique:
            for lag in by_offset:
                entry = offsets[day] + lag
                exit_ = entry + horizon
                if exit_ >= len(market_days):
                    coverage[lag]["pending"] += 1
                    continue
                dates = market_days[entry:exit_ + 1]
                series = [stocks.get(d, {}).get(code) for d in dates]
                if any(px is None or px <= 0 for px in series):
                    coverage[lag]["missing_price"] += 1
                    continue
                if actions_between(actions, code, dates[0], dates[-1]):
                    coverage[lag]["corporate_action_unadjusted"] += 1
                    continue
                coverage[lag]["complete"] += 1
                by_offset[lag][day, code] = measure(series, benchmark[dates[0]], benchmark[dates[-1]])
        common = sorted(by_offset[0].keys() & by_offset[1].keys())
        results[horizon] = {
            "coverage": coverage,
            "same_session_signal_close": summarize(list(by_offset[0].values())),
            "next_session_close": summarize(list(by_offset[1].values())),
            "matched_same_session": summarize([by_offset[0][k] for k in common]),
            "matched_next_session": summarize([by_offset[1][k] for k in common]),
        }
        assert all(sum(counter.values()) == len(unique) for counter in coverage.values())
    return len(unique), results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("index_files", type=Path, nargs="+")
    args = parser.parse_args()
    benchmark, sources = index_closes(args.index_files)
    inputs = {name: Path("remote", name).read_bytes()
              for name in ("pick_validation.json", "daily_prices.json", "strategy_performance.json")}
    picks = json.loads(inputs["pick_validation.json"])["picks"]
    archive = json.loads(inputs["daily_prices.json"])
    ledger = json.loads(inputs["strategy_performance.json"])
    unique, results = replay(picks, archive, benchmark)

    def evidence_counts(rows):
        def status(row):
            proof = row.get("provenance")
            if not proof:
                return "missing_provenance"
            if proof["reconstructed"]:
                return "reconstructed"
            if proof["source_dirty"]:
                return "dirty_source"
            return "candidate_for_independent_review"
        return Counter(map(status, rows))

    print(json.dumps({
        "method": "descriptive replay, same close and next close, equal holding periods; TAIEX zero-cost price index",
        "registered_strategy": False,
        "qualified_oos": 0,
        "inputs_sha256": {name: sha256(data).hexdigest() for name, data in inputs.items()},
        "sources": sources, "index_start": min(benchmark), "index_end": max(benchmark),
        "index_sessions": len(benchmark), "earliest_signal": min(p["day"] for p in picks),
        "latest_signal": max(p["day"] for p in picks), "frozen_signals": len(picks),
        "unique_code_day_signals": unique, "fee_per_side": FEE, "sell_tax": TAX,
        "slippage_per_side": SLIP, "results": results,
        "ledger_signal_provenance": evidence_counts(ledger["signals"]),
        "ledger_closed_provenance": {k: evidence_counts(v["closed"]) for k, v in ledger["strategies"].items()},
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
