"""Deterministic five-mode report schema. No model calls or trading orders."""
import json
from pathlib import Path

MODES = {
    "market_news": ["real_impact", "affected_markets", "horizon", "priced_in_logic", "historical_analogues", "bullish", "bearish", "next_step"],
    "technical": ["trend", "support_resistance", "volume", "rsi_macd_moving_averages", "structure", "institutional_hypotheses", "scenario", "strength", "key_levels"],
    "fundamental": ["revenue_eps", "margins", "cash_flow", "moat", "valuation", "growth_drivers", "critical_disclosures", "strength", "concerns"],
    "decision": ["news", "technical", "fundamental", "sentiment", "capital_flows", "contradictions", "biggest_risk", "scenarios", "bias", "posture"],
    "personalized": ["market", "style", "risk_appetite", "priorities", "risk_controls", "backtest_status"],
}
COMMON = ["as_of", "sources", "facts", "inferences", "invalidating_conditions"]

def report_template(mode):
    if mode not in MODES:
        raise ValueError("unknown_mode")
    return {"mode": mode, "status": "INSUFFICIENT_EVIDENCE",
            **{key: None for key in COMMON + MODES[mode]},
            "no_live_trade_signal": True}

def validate_report(report):
    if not isinstance(report, dict) or report.get("mode") not in MODES:
        return ["invalid_mode"]
    required = COMMON + MODES[report["mode"]]
    errors = ["missing_" + key for key in required if key not in report or report[key] is None]
    if report.get("no_live_trade_signal") is not True:
        errors.append("trade_signal_not_allowed")
    return errors

def load_profile(path="config/jei_ai_trader_profile.json"):
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    if profile.get("auto_trade") is not False or profile.get("auto_promote") is not False:
        raise ValueError("unsafe_profile")
    return profile
