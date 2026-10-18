"""Validate JEI paper-trading data freshness without inventing missing returns."""
from datetime import date

def audit_snapshot_dates(picks, prices):
    issues=[]
    for pick in picks:
        code=str(pick["code"])
        as_of=date.fromisoformat(pick["as_of"])
        series=prices.get(code,[])
        future=[x for x in series if date.fromisoformat(x["date"])>as_of]
        if not future:
            issues.append({"code":code,"as_of":pick["as_of"],"issue":"no_future_price"})
    return {"total_signals":len(picks),"unresolved":len(issues),"issues":issues}
