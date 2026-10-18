"""Aggregate matured JEI paper outcomes without counting pending picks as wins.

Use with scripts.forward_pick_score.score_pick results.
"""
from statistics import mean
from math import isfinite
from scripts.forward_pick_score import COHORTS, HORIZONS

def summarize(scored_picks):
    output = {}
    for cohort in COHORTS:
        output[cohort] = {}
        selected = [p for p in scored_picks if p.get("cohort") == cohort]
        for horizon in HORIZONS:
            key = str(horizon)
            valid = [p["outcomes"][key]["net_return_pct"] for p in selected
                     if p.get("outcomes", {}).get(key, {}).get("status") == "mature"
                     and isinstance(p["outcomes"][key].get("net_return_pct"), (int, float))
                     and not isinstance(p["outcomes"][key].get("net_return_pct"), bool)
                     and isfinite(p["outcomes"][key]["net_return_pct"])]
            output[cohort][key] = {
                "total_signals": len(selected),
                "matured": len(valid),
                "pending_or_unavailable": len(selected) - len(valid),
                "win_rate_pct": round(sum(x > 0 for x in valid) / len(valid) * 100, 2) if valid else None,
                "mean_net_return_pct": round(mean(valid), 4) if valid else None,
                "min_net_return_pct": min(valid) if valid else None,
            }
    return output
