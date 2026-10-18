"""Build an always-safe public strategy scoreboard from archived JEI observations.

Feed observations are diagnostic, never independently verified official closes.
This job cannot set verified=True, even if benchmark data is supplied.
"""
import argparse
import json
from pathlib import Path
from scripts.run_archived_paper_pipeline import run
from scripts.paper_leaderboard import leaderboard

def build(pick_dir,price_dir):
    report=run(pick_dir,price_dir)
    report["data_quality"]["verified_by_system"]=False
    board=leaderboard(report)
    board["data_date"]=max((p["as_of"] for p in report["picks"]),default=None)
    board["price_data_date"]=max((row["date"] for rows in __import__("scripts.collect_feed_closes",fromlist=["collect"]).collect(price_dir).values() for row in rows),default=None)
    board["data_quality"]={"price_source":"JEI feed snapshots",
                           "verified_by_system":False,
                           "sample_count":report["sample_count"],
                           "warning":"Not official historical closes; performance withheld."}
    return board

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--picks-dir",type=Path,default=Path("data/pick_snapshots"))
    parser.add_argument("--prices-dir",type=Path,default=Path("data/feed_closes"))
    parser.add_argument("--output",type=Path,default=Path("remote/paper-leaderboard.json"))
    args=parser.parse_args()
    result=build(args.picks_dir,args.prices_dir)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Wrote unverified strategy scoreboard from",result["data_quality"]["sample_count"],"signals")

if __name__=="__main__":
    main()
