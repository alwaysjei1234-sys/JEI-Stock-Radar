"""Aggregate matured JEI paper outcomes without counting pending picks as wins.

Use with scripts.forward_pick_score.score_pick results.
"""
from statistics import mean, median
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
                "max_net_return_pct": max(valid) if valid else None,
                "median_net_return_pct": round(median(valid), 4) if valid else None,
                "loss_rate_pct": round(sum(x < 0 for x in valid) / len(valid) * 100, 2) if valid else None,
                "profit_factor": (round(sum(x for x in valid if x > 0) / -sum(x for x in valid if x < 0), 4)
                                  if any(x < 0 for x in valid) else None),
                "profit_factor_note": ("no_realized_losses" if valid and not any(x < 0 for x in valid)
                                       else "no_matured_samples" if not valid else "measured"),
            }
    return output


def rank_strategies(scored_picks, horizon=15, min_matured=10):
    """Rank only sufficiently observed cohorts; insufficient samples remain unranked."""
    if horizon not in HORIZONS:
        raise ValueError("unsupported horizon")
    if isinstance(min_matured, bool) or not isinstance(min_matured, int) or min_matured < 1:
        raise ValueError("min_matured must be a positive integer")
    summary = summarize(scored_picks)
    rows = []
    for cohort in COHORTS:
        item = summary[cohort][str(horizon)]
        eligible = item["matured"] >= min_matured
        rows.append({"cohort": cohort, "horizon": horizon, "eligible": eligible,
                     "reason": "sufficient_samples" if eligible else "insufficient_matured_samples",
                     **item})
    # Median-first ranking reduces sensitivity to one-off outlier gains.
    ranked = sorted((r for r in rows if r["eligible"]),
                    key=lambda r: (r["median_net_return_pct"], r["win_rate_pct"],
                                   r["mean_net_return_pct"]), reverse=True)
    for position, row in enumerate(ranked, 1):
        row["rank"] = position
    for row in rows:
        if not row["eligible"]:
            row["rank"] = None
    return sorted(rows, key=lambda r: (r["rank"] is None, r["rank"] or 999))
