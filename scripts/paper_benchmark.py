"""Compare matured JEI paper returns with same-window benchmark returns.

Benchmark must have dated, observed returns; missing benchmark observations are
reported as unpaired rather than silently treated as zero.
"""
from math import isfinite
from statistics import mean
from scripts.forward_pick_score import COHORTS, HORIZONS

def compare_with_benchmark(scored_picks, benchmark_returns):
    """benchmark_returns maps (entry_date, exit_date) -> percentage return."""
    report = {}
    for cohort in COHORTS:
        report[cohort] = {}
        for h in HORIZONS:
            matched, unmatched, excess = [], 0, []
            for pick in scored_picks:
                if pick.get("cohort") != cohort:
                    continue
                outcome = pick.get("outcomes", {}).get(str(h), {})
                if outcome.get("status") != "mature":
                    continue
                ret = outcome.get("net_return_pct")
                if not isinstance(ret, (int, float)) or isinstance(ret, bool) or not isfinite(ret):
                    continue
                key = (pick.get("entry_date"), outcome.get("exit_date"))
                benchmark = benchmark_returns.get(key)
                if not isinstance(benchmark, (int, float)) or isinstance(benchmark, bool) or not isfinite(benchmark):
                    unmatched += 1
                    continue
                matched.append(ret)
                excess.append(ret - benchmark)
            report[cohort][str(h)] = {
                "paired_count": len(matched),
                "missing_benchmark_count": unmatched,
                "mean_excess_pct": round(mean(excess), 4) if excess else None,
                "benchmark_beat_rate_pct": round(100 * sum(x > 0 for x in excess) / len(excess), 2) if excess else None,
            }
    return report
