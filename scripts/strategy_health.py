"""Conservative, look-ahead-safe feedback from observed close-only pick results.

This evidence is NOT independent OOS, verified fills or a live trading rule.
Only annotate fresh candidates; never alter ranks, frozen picks, or backtests.
"""
import datetime as dt
import math

FAMILIES = ("attack", "next", "monster", "tomorrow_monster", "future_monster")
HORIZONS = ("3", "7")
MIN_COMPLETED = 30
MAX_AGE_DAYS = 7


def _date(value):
    if type(value) is not str or len(value) != 10:
        return None
    try:
        date = dt.date.fromisoformat(value)
    except ValueError:
        return None
    return date if date.isoformat() == value else None


def assess_observed_quality(report, as_of, *, market_open=False):
    base = {
        "source": "forward_official_close_pick_validation",
        "status": "UNVERIFIED",
        "recommendation_mode": "unverified",
        "advisory_only": True,
        "automatic_trade_block": False,
        "independent_oos_verified": False,
        "live_trading_verified": False,
        "evaluated_windows": 0,
        "underperforming_windows": 0,
        "required_windows": len(FAMILIES) * len(HORIZONS),
        "latest_official_day": None,
        "reason": "missing_or_invalid_observed_evidence",
    }
    if (not isinstance(report, dict) or report.get("schema") != 1
            or report.get("mode") != base["source"]):
        return base
    today, observed = _date(as_of), _date(report.get("latest_official_day"))
    if today is None or observed is None:
        return base
    age = (today - observed).days
    if age < 0 or age > MAX_AGE_DAYS or (market_open and age == 0):
        return {**base, "latest_official_day": observed.isoformat(),
                "reason": "future_intraday_or_stale_observed_evidence"}
    groups = report.get("groups")
    if not isinstance(groups, dict):
        return base
    evaluated, underperforming = 0, 0
    for family in FAMILIES:
        periods = groups.get(family)
        if not isinstance(periods, dict):
            continue
        for horizon in HORIZONS:
            stats = periods.get(horizon)
            if not isinstance(stats, dict):
                continue
            completed = stats.get("completed")
            win = stats.get("win_rate_pct")
            net = stats.get("avg_estimated_net_pct")
            if (type(completed) is not int or completed < MIN_COMPLETED
                    or type(win) not in (float, int)
                    or type(net) not in (float, int)
                    or not math.isfinite(win) or not math.isfinite(net)
                    or not 0 <= win <= 100 or not -100 <= net <= 1000):
                continue
            evaluated += 1
            if win < 50 or net <= 0:
                underperforming += 1

    base = {**base, "latest_official_day": observed.isoformat(),
            "evaluated_windows": evaluated,
            "underperforming_windows": underperforming}
    if evaluated < base["required_windows"]:
        return {**base, "status": "INSUFFICIENT_EVIDENCE",
                "reason": "not_all_families_have_3d_and_7d_mature_samples"}
    if underperforming == evaluated:
        return {**base, "status": "ALL_OBSERVED_SHORT_HORIZONS_WEAK",
                "recommendation_mode": "research_only",
                "reason": "all_five_families_have_weak_3d_and_7d_close_only_results"}
    if underperforming:
        return {**base, "status": "SOME_OBSERVED_SHORT_HORIZONS_WEAK",
                "recommendation_mode": "review_before_using",
                "reason": "some_short_horizon_observations_are_weak"}
    return {**base, "status": "OBSERVED_THRESHOLD_MET_NOT_OOS",
            "recommendation_mode": "unverified",
            "reason": "close_only_result_is_not_validated_real_trading"}


def annotate_public_feed(feed, report, as_of, *, market_open=False):
    """Attach risk warnings to a NEW public feed, not historical frozen picks.

    Only the ten sufficiently mature, independent *windows* requirement
    controls the label. Windows overlap, and this does not establish 10
    independent strategies or automatically change trade permissions.
    """
    quality = assess_observed_quality(report, as_of, market_open=market_open)
    feed["strategy_health"] = quality
    if quality["recommendation_mode"] != "research_only":
        return quality
    warning = ("⚠ 主攻／下一棒／妖股等五類的3日與7日收盤觀察，"
               "10組達樣本門檻的結果全部不佳；新候選僅供模擬研究，"
               "不構成已驗證的買進建議，尚無獨立OOS交易績效。")
    risk = feed.get("risk")
    if isinstance(risk, dict):
        risk["strategy_quality_alert"] = True
        reasons = risk.get("reasons")
        if isinstance(reasons, list):
            reasons.insert(0, warning)
    market = feed.get("market")
    if isinstance(market, dict):
        # Market freshness/quote validity remains separate from pick quality.
        market["candidate_readiness"] = "research_only"
    priority = feed.get("priority")
    if isinstance(priority, list):
        priority.insert(0, {"title": "策略觀察績效警戒",
                            "note": warning, "action": "僅模擬研究"})
        for entry in priority:
            if isinstance(entry, dict) and entry.get("action") in ("主攻#1", "下一棒#1"):
                entry["action"] = "僅模擬研究"
                entry["note"] = (str(entry.get("note") or "") + "｜" + warning)
    for family in FAMILIES + ("rotate",):
        rows = feed.get(family)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            row["trade_readiness"] = "research_only"
            row["observed_quality_warning"] = "短期觀察績效全面未達標；僅模擬"
            row["reason"] = str(row.get("reason") or "") + "｜" + warning
    return quality
