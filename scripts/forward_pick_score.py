#!/usr/bin/env python3
"""Forward-only JEI pick scoring primitives. No brokerage or network access.

Input: daily immutable signal snapshot and dated close series.
Never substitute a missing future session with the last known price.
"""
from datetime import date
from math import isfinite

HORIZONS = (3, 7, 15, 30, 60)
COHORTS = ("momentum", "monster", "pre_breakout")

def score_pick(pick, sessions, fee_rate=0.001425, sell_tax_rate=0.003, slippage_rate=0.001):
    """sessions: sorted unique trading sessions [{date: ISO, close: positive number}].

    Signal is generated after the snapshot's as_of close; entry is NEXT session's
    close, a conservative reproducible proxy, not an executable trade quote.
    Horizons count sessions AFTER entry, so a 3-session outcome needs four
    sessions following as_of. A real fill simulator must separately model orders.
    """
    as_of = date.fromisoformat(pick["as_of"])
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
    if clean != sorted(clean):
        raise ValueError("sessions must be strictly ascending")
    future = [(d, p) for d, p in clean if d > as_of]
    result = {"code": pick["code"], "as_of": pick["as_of"],
              "cohort": pick["cohort"], "entry_rule": "next_session_close_proxy",
              "outcomes": {}}
    if not future:
        for h in HORIZONS:
            result["outcomes"][str(h)] = {"status": "pending"}
        return result
    entry_date, entry = future[0]
    result["entry_date"] = entry_date.isoformat()
    result["entry_price"] = entry
    for h in HORIZONS:
        # Do not claim h trading sessions elapsed if the source price series
        # skips any exchange sessions. A trusted trading calendar must be
        # supplied by the report pipeline for strict completeness checks.
        if len(future) <= h:
            result["outcomes"][str(h)] = {"status": "pending"}
            continue
        exit_date, exit_price = future[h]
        gross = exit_price / entry - 1
        net = (exit_price * (1 - fee_rate - sell_tax_rate - slippage_rate) /
               (entry * (1 + fee_rate + slippage_rate))) - 1
        result["outcomes"][str(h)] = {
            "status": "mature", "exit_date": exit_date.isoformat(),
            "gross_return_pct": round(gross * 100, 4),
            "net_return_pct": round(net * 100, 4)}
    return result
