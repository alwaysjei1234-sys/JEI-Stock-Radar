#!/usr/bin/env python3
"""JEI public paper-close benchmark: no broker connectivity, no private holdings.

Each validated close D records signals. The *following official trading close*
is the first hypothetical entry; exits are evaluated no earlier than D+2.
Close-to-close figures are observations, not executable fills or predictions.
"""
import json
import math
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = ROOT / "remote/system.json"
DAILY = ROOT / "remote/daily_prices.json"
OUT = ROOT / "remote/strategy_performance.json"
TZ = ZoneInfo("Asia/Taipei")
CAPITAL = 1_000_000.0
LIMIT = 100_000.0
FEE = 0.001425
SELL_TAX = 0.003
RULES = {
    "fixed5": {"name": "固定 +5%", "target": 5.0},
    "fixed7": {"name": "固定 +7%", "target": 7.0},
    "fixed10": {"name": "固定 +10%", "target": 10.0},
    "trailing": {"name": "上漲5%啟動／高點回落2%", "target": 5.0},
}

def initial_state():
    return {
        "schema": 1,
        "mode": "official_daily_close_paper_observation",
        "notes": "訊號日僅觀察，下一個有效交易日收盤才假設進場；再下一日才判斷出場。非實際成交，未計滑價或無法成交。",
        "capital_per_strategy": CAPITAL,
        "position_limit": LIMIT,
        "buy_fee_rate": FEE,
        "sell_fee_rate": FEE,
        "sell_tax_rate": SELL_TAX,
        "last_processed_day": None,
        "signals": [],
        "strategies": {
            key: {"name": rule["name"], "cash": CAPITAL, "positions": [],
                  "closed": [], "equity_history": [], "summary": {}}
            for key, rule in RULES.items()
        },
    }

def price_for(quotes, code):
    try:
        p = float(quotes.get(code, 0))
        return p if math.isfinite(p) and p > 0 else None
    except (ValueError, TypeError, AttributeError):
        return None

def validate(feed, archive, day):
    if (feed.get("data_date") != day or
        feed.get("market", {}).get("mode") != "今日收盤" or
        feed.get("market", {}).get("stale") is not False or
        int(feed.get("market", {}).get("close_count") or 0) < 500):
        raise ValueError("尚未取得今日已驗證官方收盤行情；拒絕更新模擬")
    if (archive.get("schema") != 1 or
        archive.get("kind") != "official_daily_close" or
        not isinstance(archive.get("days"), dict)):
        raise ValueError("官方收盤價封存格式不正確")
    quotes = archive["days"].get(day)
    if not isinstance(quotes, dict) or len(quotes) < 500:
        raise ValueError("當天收盤價封存不足；拒絕以舊價或盤中價模擬")

def daily_signals(feed, quotes, day):
    candidates = []
    seen = set()
    for k in ("attack", "monster"):
        for x in (feed.get(k) or []):
            code = str(x.get("code") or "")
            if not re.fullmatch(r"\d{4,6}", code) or code in seen:
                continue
            if price_for(quotes, code) is None:
                continue
            seen.add(code)
            candidates.append({
                "id": day + ":" + code, "day": day, "code": code,
                "name": str(x.get("name") or code)[:35],
                "score": int(x.get("score") or 0), "source": k,
                "signal_close": price_for(quotes, code),
            })
    candidates.sort(key=lambda x: (-x["score"], x["code"]))
    return candidates[:5]

def exit_reason(rule_key, pos, price):
    pct = (price / pos["entry_price"] - 1) * 100
    pos["peak"] = max(float(pos.get("peak") or pos["entry_price"]), price)
    peak_pct = (pos["peak"] / pos["entry_price"] - 1) * 100
    if pct <= -3:
        return "收盤停損"
    if rule_key == "trailing":
        if peak_pct >= 5 and price <= pos["peak"] * 0.98:
            return "移動停利觸發"
    elif pct >= RULES[rule_key]["target"]:
        return "收盤停利"
    return None

def summarize(account, quotes):
    closed = account["closed"]
    realized = sum(float(x["net"]) for x in closed)
    win = sum(float(x["net"]) > 0 for x in closed)
    value = account["cash"]
    covered = 0
    for pos in account["positions"]:
        price = price_for(quotes, pos["code"])
        if price is None:
            continue
        covered += 1
        value += price * pos["qty"] * (1 - FEE - SELL_TAX)
    coverage = (covered == len(account["positions"]))
    summary = {
        "closed": len(closed), "wins": win,
        "win_rate_pct": round(100 * win / len(closed), 2) if closed else None,
        "realized_net_ntd": round(realized, 2),
        "realized_return_pct_of_initial": round(100 * realized / CAPITAL, 3),
        "open_positions": len(account["positions"]),
        "cash_ntd": round(account["cash"], 2),
        "estimated_liquidation_equity_ntd": round(value, 2) if coverage else None,
        "official_close_coverage": f"{covered}/{len(account['positions'])}",
    }
    account["summary"] = summary
    return summary

def advance(feed, archive, state, day):
    """Mutate only after validating today's official close; idempotent by trading day."""
    validate(feed, archive, day)
    if state.get("last_processed_day") and state["last_processed_day"] >= day:
        return False
    days = sorted(d for d in archive["days"] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and d <= day)
    prior_day = days[-2] if len(days) > 1 and days[-1] == day else None
    quotes = archive["days"][day]
    prior_signals = [x for x in state["signals"] if x.get("day") == prior_day]

    for key in RULES:
        a = state["strategies"][key]
        remaining = []
        for pos in a["positions"]:
            px = price_for(quotes, pos["code"])
            if px is None or pos["entry_day"] >= day:
                remaining.append(pos)
                continue
            reason = exit_reason(key, pos, px)
            if reason is None:
                remaining.append(pos)
                continue
            proceeds = px * pos["qty"] * (1 - FEE - SELL_TAX)
            net = proceeds - pos["entry_cost"]
            a["cash"] += proceeds
            a["closed"].append({
                "code": pos["code"], "signal_day": pos["signal_day"],
                "entry_day": pos["entry_day"], "exit_day": day,
                "entry_price": pos["entry_price"], "exit_price": px,
                "qty": pos["qty"], "reason": reason,
                "net": round(net, 2),
                "net_return_pct": round(100 * net / pos["entry_cost"], 3),
            })
        a["positions"] = remaining

        # Never enter a signal at its own closing price. Entries are a separate
        # *following session* close assumption; no claim of actual fill.
        for sig in prior_signals:
            code = sig["code"]
            if any(p["code"] == code for p in a["positions"]):
                continue
            px = price_for(quotes, code)
            if px is None:
                continue
            budget = min(LIMIT, a["cash"])
            qty = math.floor(budget / (px * (1 + FEE)))
            if qty < 1:
                continue
            entry_cost = px * qty * (1 + FEE)
            a["cash"] -= entry_cost
            a["positions"].append({
                "code": code, "name": sig["name"], "signal_day": sig["day"],
                "entry_day": day, "entry_price": px,
                "entry_cost": entry_cost, "qty": qty, "peak": px,
            })
        a["closed"] = a["closed"][-500:]
        summary = summarize(a, quotes)
        a["equity_history"].append({"day": day, "equity": summary["estimated_liquidation_equity_ntd"]})
        a["equity_history"] = a["equity_history"][-90:]
        values = [x["equity"] for x in a["equity_history"] if x["equity"] is not None]
        peak = CAPITAL
        dd = 0.0
        for v in values:
            peak = max(peak, v)
            dd = max(dd, 100 * (peak - v) / peak)
        summary["max_drawdown_pct"] = round(dd, 3) if values else None

    state["signals"].extend(daily_signals(feed, quotes, day))
    state["signals"] = state["signals"][-400:]
    state["last_processed_day"] = day
    state["updated_at"] = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    state["latest_signal_count"] = sum(x["day"] == day for x in state["signals"])
    return True

def main():
    now = datetime.now(TZ)
    day = now.strftime("%Y-%m-%d")
    feed = json.loads(SYSTEM.read_text(encoding="utf-8"))
    archive = json.loads(DAILY.read_text(encoding="utf-8"))
    state = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else initial_state()
    updated = advance(feed, archive, state, day)
    if updated:
        OUT.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "day": day, "updated": updated,
        "last_processed_day": state["last_processed_day"],
        "signals_today": state.get("latest_signal_count", 0),
        "strategies": {k: v["summary"] for k, v in state["strategies"].items()},
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
