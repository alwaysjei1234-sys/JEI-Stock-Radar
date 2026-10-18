#!/usr/bin/env python3
"""Forward-only JEI pick scoring primitives. No brokerage or network access.

Input: daily immutable signal snapshot and dated close series.
Never substitute a missing future session with the last known price.
"""
from datetime import date
from math import isfinite

HORIZONS = (3, 7, 15, 30, 60)
COHORTS = ("momentum", "monster", "pre_breakout")

def score_pick(pick, sessions, fee_rate=0.001425, sell_tax_rate=0.003, slippage_rate=0.001, trading_dates=None):
    """sessions: sorted unique trading sessions [{date: ISO, close: positive number}].

    Signal is generated after the snapshot's as_of close; entry is NEXT session's
    close, a conservative reproducible proxy, not an executable trade quote.
    Horizons count sessions AFTER entry, so a 3-session outcome needs four
    sessions following as_of. A real fill simulator must separately model orders.
    """
    as_of = date.fromisoformat(pick["as_of"])
    for name,value in (("fee_rate",fee_rate),("sell_tax_rate",sell_tax_rate),("slippage_rate",slippage_rate)):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or not 0 <= value < 1:
            raise ValueError(f"invalid {name}")
    if pick["cohort"] not in COHORTS:
        raise ValueError("unknown cohort")
    if not pick.get("code"):
        raise ValueError("missing code")
    seen = set()
    clean = []
    for item in sessions:
        d = date.fromisoformat(item["date"])
        p = item["close"]
        if d in seen:
            raise ValueError("duplicate session")
        if not isinstance(p, (int, float)) or isinstance(p, bool) or not isfinite(p) or p <= 0:
            raise ValueError("invalid close")
        seen.add(d)
        clean.append((d, float(p)))
    if any(clean[i][0] >= clean[i+1][0] for i in range(len(clean)-1)):
        raise ValueError("sessions must be strictly ascending")
    if trading_dates is not None:
        calendar = [date.fromisoformat(d) for d in trading_dates]
        if calendar != sorted(set(calendar)):
            raise ValueError("trading calendar must be unique and ascending")
        prices = dict(clean)
        calendar_dates=set(calendar)
        if any(d > as_of and d not in calendar_dates for d,_ in clean):
            raise ValueError("stock price date outside benchmark trading calendar")
        # Benchmark calendar is authoritative; extra stock rows are ignored.
        future = [(d, prices.get(d)) for d in calendar if d > as_of]
    else:
        future = [(d, p) for d, p in clean if d > as_of]
    result = {"code": pick["code"], "as_of": pick["as_of"],
              "cohort": pick["cohort"], "entry_rule": "next_session_close_proxy",
              "outcomes": {}}
    if not future:
        for h in HORIZONS:
            result["outcomes"][str(h)] = {"status": "pending"}
        return result
    entry_date, entry = future[0]
    if entry is None:
        for h in HORIZONS:
            result["outcomes"][str(h)] = {"status": "unavailable", "reason": "missing_entry_close"}
        return result
    result["entry_date"] = entry_date.isoformat()
    result["entry_price"] = entry
    for h in HORIZONS:
        if len(future) <= h:
            result["outcomes"][str(h)] = {"status": "pending"}
            continue
        exit_date, exit_price = future[h]
        if exit_price is None:
            result["outcomes"][str(h)] = {"status": "unavailable", "reason": "missing_exit_close",
                                          "exit_date": exit_date.isoformat()}
            continue
        gross = exit_price / entry - 1
        net = (exit_price * (1 - fee_rate - sell_tax_rate - slippage_rate) /
               (entry * (1 + fee_rate + slippage_rate))) - 1
        result["outcomes"][str(h)] = {
            "status": "mature", "exit_date": exit_date.isoformat(),
            "gross_return_pct": round(gross * 100, 4),
            "net_return_pct": round(net * 100, 4)}
    return result
