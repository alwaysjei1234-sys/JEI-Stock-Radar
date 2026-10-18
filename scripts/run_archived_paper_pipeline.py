"""Offline end-to-end JEI paper pipeline.

Uses only archived files. It will NOT claim an official verified scorecard
unless official close series and a benchmark calendar are explicitly provided.
"""
import argparse
import json
from pathlib import Path
from scripts.collect_pick_snapshots import load_snapshots
from scripts.collect_feed_closes import collect
from scripts.paper_report import build_report

def run(pick_directory, price_directory, benchmark=None):
    picks=load_snapshots(pick_directory)
    prices=collect(price_directory)
    result=build_report(picks,prices,benchmark)
    result["data_quality"]={
        "price_source":"JEI feed observation, NOT verified official close",
        "official_close_verified":False,
        "benchmark_supplied":benchmark is not None,
        "signal_snapshot_count":len(list(Path(pick_directory).glob("????-??-??.json"))),
        "price_snapshot_count":len(list(Path(price_directory).glob("????-??-??.json"))),
        "stock_series_count":len(prices),
        "note":"Use for pipeline diagnostics only, not audited investment returns."
    }
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--picks-dir",type=Path,default=Path("data/pick_snapshots"))
    p.add_argument("--feed-prices-dir",type=Path,default=Path("data/feed_closes"))
    p.add_argument("--benchmark",type=Path)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    benchmark=json.loads(args.benchmark.read_text(encoding="utf-8")) if args.benchmark else None
    result=run(args.picks_dir,args.feed_prices_dir,benchmark)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Diagnostic report: {result['sample_count']} signals; official closes NOT verified.")

if __name__=="__main__":
    main()
