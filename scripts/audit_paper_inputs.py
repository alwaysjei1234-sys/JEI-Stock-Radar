"""Audit missing post-signal observations without inventing fills or returns."""
from datetime import date

def audit_snapshot_dates(picks, prices):
    if not isinstance(picks,list) or not isinstance(prices,dict):
        raise ValueError("picks must be list and prices must be mapping")
    issues=[]
    for pick in picks:
        code=str(pick["code"])
        as_of=date.fromisoformat(pick["as_of"])
        series=prices.get(code,[])
        if not isinstance(series,list):
            raise ValueError("price series must be list")
        future=False
        for observation in series:
            observed=date.fromisoformat(observation["date"])
            if observed>as_of:
                future=True
                break
        if not future:
            issues.append({"code":code,"as_of":pick["as_of"],
                           "issue":"no_future_price"})
    return {"total_signals":len(picks),"unresolved":len(issues),"issues":issues}
