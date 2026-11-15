"""Read-only DQN experiment action output -> JEI dated-price OOS comparison.

This is a model-output adapter, not a neural network trainer, real DQN
integration, independent proof of its training cutoff, or brokerage connector.
"""
import argparse
from datetime import date
import json
from pathlib import Path
import re

from tools.jei_blave_bridge import (
    MAX_RECORDS, evaluate_blave_export, load_archive, parse_jsonl, validate_signal
)

DQN_SOURCE = {"dqn-experiment"}


def evaluate_dqn_export(rows, archive):
    if not isinstance(rows, list) or not rows or len(rows) > MAX_RECORDS:
        raise ValueError("empty or oversized DQN action export")
    days, calendar = load_archive(archive)
    seen_ids, seen_slots, versions = set(), set(), {}
    excluded = 0
    oos = []
    for line_no, row in enumerate(rows, 1):
        signal = validate_signal(row, calendar, days, allowed_sources=DQN_SOURCE)
        split = row.get("split")
        version = row.get("model_version")
        cutoff = row.get("trained_through")
        if split not in ("train", "oos"):
            raise ValueError("explicit train/oos split required at line " + str(line_no))
        if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", version):
            raise ValueError("invalid DQN model_version")
        try:
            if not isinstance(cutoff, str) or date.fromisoformat(cutoff).isoformat() != cutoff:
                raise ValueError("invalid training date")
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid trained_through") from exc
        key = (signal["strategy_id"], version)
        old = versions.setdefault(key, cutoff)
        if old != cutoff:
            raise ValueError("model version silently changed training cutoff")
        uid = signal["signal_id"]
        slot = (signal["data_asof"], signal["strategy_id"], signal["ticker"])
        if uid in seen_ids or slot in seen_slots:
            raise ValueError("duplicate signal or strategy/day/ticker")
        seen_ids.add(uid)
        seen_slots.add(slot)
        if split == "train":
            if signal["data_asof"] > cutoff:
                raise ValueError("train observation extends past trained_through")
            excluded += 1
            continue
        if signal["data_asof"] <= cutoff:
            raise ValueError("DQN OOS signal is inside its declared training period")
        oos.append(row)
    if not oos:
        return {
            "schema": 1, "status": "INSUFFICIENT_EVIDENCE",
            "reason": "no_out_of_sample_signals", "train_rows_excluded": excluded,
            "oos_rows": 0, "independent_oos_verified": False,
            "model_training_verified": False, "live_orders_enabled": False,
        }
    report = evaluate_blave_export(
        oos, archive, allowed_sources=DQN_SOURCE,
        source_system="DQN external experiment model-action JSONL (origin and training unverified)")
    report.update({
        "mode": "external_dqn_oos_paper_comparison",
        "train_rows_excluded": excluded,
        "oos_rows": len(oos),
        "declared_model_cutoffs": [
            {"strategy_id": name, "model_version": version, "trained_through": cutoff}
            for (name, version), cutoff in sorted(versions.items())
        ],
        "oos_split_self_reported": True,
        "model_training_verified": False,
        "independent_oos_verified": False,
        "walk_forward_verified": False,
        "note": "Read-only DQN model action validation. No training weights/episode checks or verified third-party fills; cannot claim 80% win rate or model efficacy.",
    })
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--actions", type=Path, required=True)
    parser.add_argument("--prices", type=Path, default=Path("remote/daily_prices.json"))
    parser.add_argument("--out", type=Path, default=Path("audit-output/dqn-oos-comparison.json"))
    args = parser.parse_args()
    try:
        rows = parse_jsonl(args.actions.read_text(encoding="utf-8-sig"))
        archive = json.loads(args.prices.read_text(encoding="utf-8"))
        result = evaluate_dqn_export(rows, archive)
        exit_code = 0 if result["status"] == "OBSERVED_PROXY_ONLY" else 1
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as exc:
        result = {"schema": 1, "status": "REJECTED", "reason": str(exc),
                  "model_training_verified": False, "live_orders_enabled": False}
        exit_code = 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "observations"}, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
