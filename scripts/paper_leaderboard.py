"""Build a compact, mobile-friendly leaderboard from audited-shape paper reports.

No rows are ranked until the report explicitly marks its prices as independently
verified; diagnostic feed-only reports remain unavailable.
"""
import argparse
import json
from pathlib import Path

LABELS={"momentum":"主流強勢","monster":"妖股","pre_breakout":"未來潛力妖股"}
HORIZONS=("3","7","15","30","60")

def leaderboard(report):
    quality=report.get("data_quality",{})
    verified=quality.get("verified_by_system") is True
    result={"schema_version":1,"verified":verified,"method":report.get("method"),
            "disclaimer":"僅為收盤代理價模擬，非實際可成交績效。",
            "horizons":{}}
    for h in HORIZONS:
        rows=[]
        for cohort,label in LABELS.items():
            stat=report.get("cohort_summary",{}).get(cohort,{}).get(h,{})
            bench=report.get("benchmark_comparison",{}).get(cohort,{}).get(h,{})
            matured=stat.get("matured",0)
            eligible = verified and matured >= 10 and bench.get("paired_count",0) >= 10
            rows.append({"cohort":cohort,"label":label,"matured":matured,
                         "pending":stat.get("pending_or_unavailable",0),
                         "win_rate_pct":stat.get("win_rate_pct") if eligible else None,
                         "mean_net_return_pct":stat.get("mean_net_return_pct") if eligible else None,
                         "mean_excess_pct":bench.get("mean_excess_pct") if eligible else None,
                         "paired_count":bench.get("paired_count",0) if verified else 0,
                         "eligible":eligible})
        # Sample-size threshold avoids celebrating a single lucky pick.
        rows.sort(key=lambda r:(r["matured"]>=10 and r["mean_excess_pct"] is not None,
                                r["mean_excess_pct"] if r["matured"]>=10 and r["mean_excess_pct"] is not None else float("-inf")),reverse=True)
        result["horizons"][h]=rows
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    output=leaderboard(json.loads(args.report.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Leaderboard generated; verified:",output["verified"])

if __name__=="__main__":
    main()
