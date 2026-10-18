"""Read-only CLI for immutable daily picks and dated close prices.

Inputs are explicitly provided JSON files. No live quote, no made-up fills.
Example:
 python -m scripts.paper_report --picks data/picks.json --prices data/closes.json --benchmark data/benchmark.json --output report.json

picks: [{"code":"2330","cohort":"momentum","as_of":"2026-01-01"}]
prices: {"2330":[{"date":"2026-01-02","close":100}, ...]}
benchmark: [{"date":"2026-01-02","close":100}, ...] (optional)
"""
import argparse
import json
from pathlib import Path
from scripts.forward_pick_score import score_pick
from scripts.paper_score_summary import summarize
from scripts.paper_benchmark import compare_with_benchmark


def build_report(picks, prices, benchmark=None):
    if not isinstance(picks, list) or not isinstance(prices, dict):
        raise ValueError("picks must be list and prices must be code->sessions object")
    seen = set()
    scored = []
    for pick in picks:
        identity = (pick["as_of"], str(pick["code"]), pick["cohort"])
        if identity in seen:
            raise ValueError(f"duplicate immutable pick: {identity}")
        seen.add(identity)
        code = str(pick["code"])
        scored.append(score_pick({**pick, "code": code}, prices.get(code, [])))
    benchmark_returns = {}
    if benchmark is not None:
        # Use only actual dated benchmark observations; never forward fill.
        by_date = {row["date"]: row["close"] for row in benchmark}
        if len(by_date) != len(benchmark):
            raise ValueError("duplicate benchmark dates")
        for pick in scored:
            entry_date = pick.get("entry_date")
            for outcome in pick["outcomes"].values():
                if outcome["status"] != "mature":
                    continue
                exit_date = outcome["exit_date"]
                if entry_date in by_date and exit_date in by_date:
                    entry, exit_ = by_date[entry_date], by_date[exit_date]
                    if isinstance(entry, (int, float)) and isinstance(exit_, (int, float)) and entry > 0 and exit_ > 0:
                        benchmark_returns[(entry_date, exit_date)] = (exit_ / entry - 1) * 100
    return {"schema_version": 1, "method": "next_session_close_proxy",
            "sample_count": len(scored), "cohort_summary": summarize(scored),
            "benchmark_comparison": compare_with_benchmark(scored, benchmark_returns),
            "picks": scored}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--picks", required=True, type=Path)
    parser.add_argument("--prices", required=True, type=Path)
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    report = build_report(load(args.picks), load(args.prices),
                          load(args.benchmark) if args.benchmark else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"JEI paper report: {report['sample_count']} picks -> {args.output}")

if __name__ == "__main__":
    main()
