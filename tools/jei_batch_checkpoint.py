"""Idempotent resumable batch checkpoints; no fabricated backtest outcomes."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def checkpoint_key(source_sha256, strategy, parameters):
    canonical = json.dumps([source_sha256, strategy, parameters], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def save_checkpoint(path, source_sha256, strategy, parameters, completed_batches):
    if not isinstance(completed_batches, dict):
        raise ValueError("completed_batches must be a dictionary")
    data = {"schema": 1, "source_sha256": source_sha256, "strategy": strategy,
            "parameters": parameters, "key": checkpoint_key(source_sha256, strategy, parameters),
            "completed_batches": completed_batches}
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, target)
    return data


def load_checkpoint(path, source_sha256, strategy, parameters):
    target = Path(path)
    if not target.exists():
        return {}
    data = json.loads(target.read_text(encoding="utf-8"))
    expected = checkpoint_key(source_sha256, strategy, parameters)
    if data.get("key") != expected or data.get("source_sha256") != source_sha256:
        raise ValueError("checkpoint_source_or_strategy_mismatch")
    batches = data.get("completed_batches")
    if not isinstance(batches, dict):
        raise ValueError("invalid_checkpoint_batches")
    return batches


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--parameters-json", default="{}")
    args = parser.parse_args()
    batches = load_checkpoint(args.checkpoint, args.source_sha256, args.strategy,
                              json.loads(args.parameters_json))
    print(json.dumps({"completed_batches": len(batches), "batch_ids": sorted(batches)}))


if __name__ == "__main__":
    main()
