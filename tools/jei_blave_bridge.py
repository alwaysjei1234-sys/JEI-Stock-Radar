"""Read-only Blave signal export -> JEI verified-close paper observations.

This is an offline JSONL contract adapter, NOT a Blave API connection, brokerage
integration, trained DQN model, or independently verified OOS fill record.
No historical pick archives or published JEI strategy scores are mutated.
"""
import argparse
from datetime import date, datetime, time
import json
from math import isfinite
from pathlib import Path
import re
from statistics import mean
from zoneinfo import ZoneInfo

from scripts.forward_pick_score import HORIZONS, score_pick
from scripts.market_sessions import next_expected_session

TZ = ZoneInfo("Asia/Taipei")
SIGNAL_REQUIRED = {"signal_id", "generated_at", "ticker", "market", "strategy_id",
                   "signal", "reference_price", "data_asof", "source"}
SOURCE_LABELS = {"blave-agent", "blave_agent"}
MAX_RECORDS = 5000
MAX_LINE_CHARS = 4096


def valid_price(value):
    return type(value) in (int, float) and isfinite(value) and value > 0


def load_archive(archive):
    """Validate a dated, full-market JEI archive before computing any outcomes."""
    if not isinstance(archive, dict) or archive.get("schema") != 1 or archive.get("kind") != "official_daily_close":
        raise ValueError("invalid official-close archive metadata")
    days = archive.get("days")
    if not isinstance(days, dict) or not days:
        raise ValueError("missing official-close trading days")
    calendar = sorted(days)
    for idx, day in enumerate(calendar):
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError("noncanonical archive date")
        quotes = days[day]
        if not isinstance(quotes, dict) or sum(valid_price(x) for x in quotes.values()) < 500:
            raise ValueError("incomplete official-close session: " + day)
        if idx and next_expected_session(calendar[idx-1]) != day:
            raise ValueError("unverified or skipped exchange session before " + day)
    return days, calendar


def validate_signal(row, calendar, days):
    if not isinstance(row, dict) or not SIGNAL_REQUIRED.issubset(row):
        raise ValueError("missing required Blave signal fields")
    signal_id, strategy_id = row["signal_id"], row["strategy_id"]
    if not isinstance(signal_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", signal_id):
        raise ValueError("invalid signal_id")
    if not isinstance(strategy_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", strategy_id):
        raise ValueError("invalid strategy_id")
    if row["source"] not in SOURCE_LABELS or row["market"] != "TW":
        raise ValueError("unexpected signal origin or non-TW market")
    action = row["signal"]
    if action not in ("BUY", "SELL", "HOLD"):
        raise ValueError("invalid signal action")
    ticker = row["ticker"]
    if not isinstance(ticker, str) or not re.fullmatch(r"[0-9]{4,6}[A-Z]?", ticker):
        raise ValueError("invalid Taiwan ticker")
    stamp = row["data_asof"]
    if not isinstance(stamp, str) or date.fromisoformat(stamp).isoformat() != stamp:
        raise ValueError("invalid signal data_asof date")
    if stamp not in days:
        raise ValueError("signal has no archived official source session")
    try:
        observed = datetime.fromisoformat(row["generated_at"].replace("Z", "+00:00"))
    except (TypeError, AttributeError, ValueError) as exc:
        raise ValueError("invalid generated_at") from exc
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("generated_at requires explicit timezone")
    local = observed.astimezone(TZ)
    if local.date().isoformat() != stamp or local.time() < time(13, 30):
        raise ValueError("signal must be generated after its same-day Taiwan official close")
    reference = row["reference_price"]
    official = days[stamp].get(ticker)
    if not valid_price(reference) or not valid_price(official):
        raise ValueError("invalid or missing source-day price")
    if abs(float(reference) / float(official) - 1.0) > 0.005:
        raise ValueError("Blave reference price differs from JEI unadjusted official close")
    return {
        "signal_id": signal_id,
        "strategy_id": strategy_id,
        "ticker": ticker,
        "generated_at": observed.isoformat(),
        "data_asof": stamp,
        "signal": action,
        "reference_price": reference,
        "source": row["source"],
    }


def evaluate_blave_export(rows, archive):
    days, calendar = load_archive(archive)
    if not isinstance(rows, list) or not rows or len(rows) > MAX_RECORDS:
        raise ValueError("empty or oversized external signal export")
    seen_ids, seen_slots = set(), set()
    observations = []
    unsupported = []
    for index, row in enumerate(rows, 1):
        signal = validate_signal(row, calendar, days)
        signal_id = signal["signal_id"]
        slot = (signal["data_asof"], signal["strategy_id"], signal["ticker"])
        if signal_id in seen_ids or slot in seen_slots:
            raise ValueError("duplicate signal_id or strategy/day/ticker at row " + str(index))
        seen_ids.add(signal_id)
        seen_slots.add(slot)
        if signal["signal"] != "BUY":
            unsupported.append({"signal_id": signal_id, "reason": "non_buy_not_scored"})
            continue
        ticker = signal["ticker"]
        priced = [{"date": d, "close": q[ticker]} for d, q in sorted(days.items())
                  if valid_price(q.get(ticker))]
        proxy = score_pick({"code": ticker, "as_of": signal["data_asof"], "cohort": "momentum"},
                           priced, trading_dates=calendar)
        observations.append({**signal,
            "entry_rule": proxy["entry_rule"],
            "entry_date": proxy.get("entry_date"),
            "entry_price": proxy.get("entry_price"),
            "outcomes": proxy["outcomes"]})
    summaries = {}
    for strategy in sorted({x["strategy_id"] for x in observations}):
        selected = [x for x in observations if x["strategy_id"] == strategy]
        summary = {}
        for h in HORIZONS:
            results = [x["outcomes"][str(h)] for x in selected]
            returns = [x["net_return_pct"] for x in results if x["status"] == "mature"]
            summary[str(h)] = {
                "selected": len(selected),
                "matured": len(returns),
                "pending": sum(x["status"] == "pending" for x in results),
                "unavailable": sum(x["status"] == "unavailable" for x in results),
                "win_rate_pct": round(100 * sum(x > 0 for x in returns) / len(returns), 2)
                                if returns else None,
                "avg_estimated_net_pct": round(mean(returns), 4) if returns else None,
            }
        summaries[strategy] = summary
    return {
        "schema": 1, "status": "OBSERVED_PROXY_ONLY",
        "source_system": "Blave Agent external user-exported JSONL (unverified provenance)",
        "external_connection_active": False, "live_orders_enabled": False,
        "independent_oos_verified": False, "walk_forward_verified": False,
        "price_source": "JEI dated archive; official provenance requires separate independent verification",
        "execution_basis": "next official trading-session CLOSE proxy, not an executable opening fill",
        "input_signals": len(rows), "scored_buy_signals": len(observations),
        "not_scored_non_buy_signals": unsupported,
        "strategies": summaries, "observations": observations,
        "note": "Research comparison only; no DQN training, no actual Blave runtime/API integration, no 80% win-rate claim."
    }


def parse_jsonl(text):
    if not isinstance(text, str) or len(text) > MAX_RECORDS * MAX_LINE_CHARS:
        raise ValueError("oversized external signal export")
    result = []
    for line_no, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        if len(raw) > MAX_LINE_CHARS:
            raise ValueError("oversized signal at line " + str(line_no))
        try:
            row = json.loads(raw)
        except ValueError as exc:
            raise ValueError("invalid JSONL at line " + str(line_no)) from exc
        result.append(row)
        if len(result) > MAX_RECORDS:
            raise ValueError("too many external signals")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--signals", type=Path, required=True, help="offline Blave signal JSONL export")
    parser.add_argument("--prices", type=Path, default=Path("remote/daily_prices.json"))
    parser.add_argument("--out", type=Path, default=Path("audit-output/blave-comparison.json"))
    args = parser.parse_args()
    try:
        rows = parse_jsonl(args.signals.read_text(encoding="utf-8-sig"))
        archive = json.loads(args.prices.read_text(encoding="utf-8"))
        result = evaluate_blave_export(rows, archive)
        code = 0
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as exc:
        result = {"schema": 1, "status": "REJECTED", "reason": str(exc),
                  "external_connection_active": False, "live_orders_enabled": False}
        code = 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "observations"}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
