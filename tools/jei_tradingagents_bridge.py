"""Optional, read-only bridge between JEI dated closes and TradingAgents.

The default path NEVER initializes an LLM, invokes a vendor, or writes orders.
A live research run is a separate, explicit opt-in and uses upstream's own data
vendors; archived JEI prices are a date/provenance gate, not an injected feed.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime

MIN_CLOSE_COVERAGE = 500
ALLOWED_MARKETS = ("TWSE", "TPEx", "US")
ALLOWED_PROVIDERS = ("ollama", "chatgpt")
ANALYSTS = ("market", "news", "fundamentals")
ROLES = {
    "market_report": "technical",
    "news_report": "news",
    "fundamentals_report": "fundamentals",
    "sentiment_report": "sentiment",
    "investment_plan": "research_debate",
    "final_trade_decision": "portfolio_decision",
}
TAIPEI = ZoneInfo("Asia/Taipei")


def _date(value):
    if not isinstance(value, str):
        raise ValueError("date must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("invalid research date") from exc
    if parsed.isoformat() != value:
        raise ValueError("date must be YYYY-MM-DD")
    return parsed


def _symbol(code, market):
    if market not in ALLOWED_MARKETS:
        raise ValueError("unsupported market")
    if market in ("TWSE", "TPEx"):
        if not isinstance(code, str) or not re.fullmatch(r"[0-9]{4,6}", code):
            raise ValueError("invalid Taiwan stock code")
        return code + (".TW" if market == "TWSE" else ".TWO")
    if not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", code):
        raise ValueError("invalid US ticker")
    if code.endswith((".TW", ".TWO")):
        raise ValueError("Taiwan ticker requires correct market")
    return code


def build_candidate(archive, code, market, day, *, today=None):
    """Validate an existing JEI daily archive without editing or fetching it.

    No claim of independent price confirmation: both archive and upstream's
    future Yahoo data may share originating sources.
    """
    ticker = _symbol(code, market)
    day_date = _date(day)
    current = today or datetime.now(TAIPEI).date()
    if day_date > current:
        raise ValueError("future dated research not allowed")
    if not isinstance(archive, dict) or archive.get("schema") != 1 or archive.get("kind") != "official_daily_close":
        raise ValueError("invalid JEI official daily archive")
    prices = archive.get("days")
    if not isinstance(prices, dict):
        raise ValueError("missing dated prices")
    daily = prices.get(day)
    if not isinstance(daily, dict) or len(daily) < MIN_CLOSE_COVERAGE:
        raise ValueError("official close coverage insufficient for selected date")
    price = daily.get(code)
    if type(price) not in (float, int) or not math.isfinite(price) or price <= 0:
        raise ValueError("ticker has no valid dated close")
    return {
        "schema": 1,
        "code": code,
        "market": market,
        "ticker": ticker,
        "analysis_date": day,
        "dated_jei_close": float(price),
        "archive_coverage": len(daily),
        "origin": "JEI remote/daily_prices.json",
        "independent_source_verified": False,
        "live_quote_verified": False,
        "automatic_trading_allowed": False,
    }


def _reports_from_state(state):
    if not isinstance(state, dict):
        return {}
    reports = {}
    for key, label in ROLES.items():
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            reports[label] = value[:1500]
    return reports


def run_review(candidate, *, execute=False, environ=None, graph_factory=None, default_config=None):
    """Create a safe dry-run plan; optionally call real TradingAgentsGraph.

    graph_factory / default_config injection is for no-network CI mocks.
    A user must explicitly opt in again for every actual research invocation.
    """
    if not isinstance(candidate, dict) or set(candidate) != {
        "schema", "code", "market", "ticker", "analysis_date",
        "dated_jei_close", "archive_coverage", "origin",
        "independent_source_verified", "live_quote_verified", "automatic_trading_allowed"
    } or candidate.get("schema") != 1:
        raise ValueError("invalid or privacy-unsafe candidate schema")
    expected_ticker = _symbol(candidate["code"], candidate["market"])
    if candidate["ticker"] != expected_ticker:
        raise ValueError("ticker/market mismatch")
    research_date = _date(candidate["analysis_date"])
    if research_date > datetime.now(TAIPEI).date():
        raise ValueError("future analysis date")
    if (type(candidate["dated_jei_close"]) not in (int, float)
            or not math.isfinite(candidate["dated_jei_close"])
            or candidate["dated_jei_close"] <= 0
            or type(candidate["archive_coverage"]) is not int
            or candidate["archive_coverage"] < MIN_CLOSE_COVERAGE
            or candidate["origin"] != "JEI remote/daily_prices.json"
            or candidate["independent_source_verified"] is not False
            or candidate["live_quote_verified"] is not False
            or candidate["automatic_trading_allowed"] is not False):
        raise ValueError("candidate provenance or safety flags invalid")
    result = {
        "schema": 1,
        "mode": "TRADINGAGENTS_RESEARCH_ONLY",
        "ticker": candidate["ticker"],
        "as_of": research_date.isoformat(),
        "jei_archived_close": candidate["dated_jei_close"],
        "source": candidate["origin"],
        "source_freshness": "historical_or_dated_close_not_live",
        "upstream_data_is_separate": True,
        "independent_market_confirmation": False,
        "upstream_point_in_time_must_be_verified": True,
        "external_model_called": False,
        "auto_order": False,
        "auto_promote": False,
        "actionable_signal": False,
        "status": "DRY_RUN",
        "agent_review": {},
        "model_rating_unverified": None,
    }
    if not execute:
        return result
    env = os.environ if environ is None else environ
    if env.get("JEI_ENABLE_EXTERNAL_AI_RESEARCH") != "1":
        raise ValueError("explicit external research opt-in required")
    provider = env.get("TRADINGAGENTS_LLM_PROVIDER", "").strip().lower()
    if provider not in ALLOWED_PROVIDERS:
        raise ValueError("only local Ollama or user-authorized ChatGPT subscription allowed in pilot")
    if graph_factory is None or default_config is None:
        try:
            from tradingagents.graph.trading_graph import TradingAgentsGraph
            from tradingagents.default_config import DEFAULT_CONFIG
        except ImportError as exc:
            raise RuntimeError("TradingAgents not installed in this isolated environment") from exc
        graph_factory = graph_factory or TradingAgentsGraph
        default_config = default_config or DEFAULT_CONFIG
    config = dict(default_config)
    config.update({
        "llm_provider": provider,
        "output_language": "Traditional Chinese",
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "max_tool_rounds": 4,
        "checkpoint_enabled": False,
    })
    # No personal portfolio passed to upstream. Other vendors may still be
    # contacted by TradingAgents; only execute on a user-controlled host.
    graph = graph_factory(selected_analysts=ANALYSTS, debug=False, config=config)
    state, rating = graph.propagate(candidate["ticker"], research_date.isoformat())
    result["external_model_called"] = True
    result["status"] = "UNVERIFIED_EXTERNAL_RESEARCH"
    result["model_rating_unverified"] = str(rating)[:80]
    result["agent_review"] = _reports_from_state(state)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="JEI non-trading TradingAgents research bridge")
    parser.add_argument("--archive", type=Path, default=Path("remote/daily_prices.json"))
    parser.add_argument("--code", required=True)
    parser.add_argument("--market", choices=ALLOWED_MARKETS, required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--execute", action="store_true",
                        help="Runs third-party LLMs and data tools; requires explicit environment opt-in")
    args = parser.parse_args(argv)
    archive = json.loads(args.archive.read_text(encoding="utf-8"))
    candidate = build_candidate(archive, args.code, args.market, args.date)
    output = run_review(candidate, execute=args.execute)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
