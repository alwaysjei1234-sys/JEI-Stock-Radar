"""Resume observed-performance batch computations after interruption.

This does not create independent out-of-sample trades.
"""
import argparse
import hashlib
import json
from pathlib import Path
from tools.jei_batch_checkpoint import load_checkpoint, save_checkpoint
from tools import jei_shared_compute
from tools.jei_shared_compute import observed_rows


def run_batches(source, checkpoint_path, output_path, max_batches=None, *, recover_invalid_checkpoint=False):
    raw = Path(source).read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw)
    groups = data.get("groups")
    if not isinstance(groups, dict) or not groups:
        raise ValueError("missing_groups")
    params = {
        "schema": 1,
        "engine_sha256": hashlib.sha256(Path(jei_shared_compute.__file__).read_bytes()).hexdigest(),
    }
    recovery = None
    try:
        done = load_checkpoint(checkpoint_path, source_hash, "observed_performance", params)
        if not done.keys() <= groups.keys():
            raise ValueError("invalid_observed_checkpoint_groups")
    except ValueError:
        if not recover_invalid_checkpoint:
            raise
        done = {}
        recovery = "invalid_checkpoint_recomputed"
    reused = len(done)
    names = sorted(groups)
    processed = 0
    for name in names:
        if name in done:
            continue
        done[name] = list(observed_rows(name, groups[name]))
        save_checkpoint(checkpoint_path, source_hash, "observed_performance", params, done)
        processed += 1
        if max_batches is not None and processed >= max_batches:
            break
    complete = done.keys() == groups.keys()
    rows = [row for name in names if name in done for row in done[name]]
    if complete and not rows:
        raise ValueError("no valid completed observations")
    output = {"schema": 1, "source_sha256": source_hash, "completed_groups": len(done),
              "total_groups": len(names), "complete": complete, "reused_groups": reused,
              "checkpoint_recovery": recovery,
              "observed_rows": rows, "independent_oos_verified": False,
              "note": "Resumable observed aggregate computation, not independent OOS backtest."}
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="remote/pick_validation.json")
    parser.add_argument("--checkpoint", default="audit-output/observed_checkpoint.json")
    parser.add_argument("--output", default="audit-output/resumable_observed.json")
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--recover-invalid-checkpoint", action="store_true")
    args = parser.parse_args()
    result = run_batches(args.input, args.checkpoint, args.output, args.max_batches,
                         recover_invalid_checkpoint=args.recover_invalid_checkpoint)
    print(json.dumps({"complete": result["complete"], "completed_groups": result["completed_groups"],
                      "total_groups": result["total_groups"]}))
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
