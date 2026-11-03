"""Recover missing close observations from the earliest verified mainline Git blob.

No market requests, new rankings, or performance-based snapshot selection. Recovered
observations remain non-executable close observations, never qualified OOS fills.
"""
import argparse
import copy
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

from scripts.update_pick_validation import ROOT, TZ, close_verified, update


def last_sealed_day(prior):
    """An explicitly sealed no-signal day is observed, not missing history."""
    days=[p["day"] for p in prior.get("picks",[])]+[s["day"] for s in prior.get("empty_sessions",[])]
    if not days:
        raise ValueError("Recovery requires an existing immutable ledger")
    for day in days:
        try:
            if datetime.strptime(day,"%Y-%m-%d").date().isoformat()!=day:
                raise ValueError("invalid sealed date")
        except (ValueError,TypeError):
            raise ValueError("Invalid immutable ledger session date") from None
    return max(days)


def recover(prior, archive, snapshots, now):
    state = copy.deepcopy(prior)
    last = last_sealed_day(state)
    required = sorted(d for d in archive["days"] if last < d <= now.astimezone(TZ).date().isoformat())
    chosen = {}
    # Git loader supplies first-parent chronological order. Never inspect outcomes
    # when selecting a snapshot. First valid publication wins, including losers.
    for source in snapshots:
        feed = source["feed"]
        day = feed.get("data_date")
        if day not in required or day in chosen or not close_verified(feed, archive, day):
            continue
        committed = datetime.fromisoformat(source["committed_at"]).astimezone(TZ)
        stamp = datetime.strptime(feed["updated_at"], "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        if committed.date().isoformat() != day or not stamp <= committed <= now:
            continue
        chosen[day] = source
    missing = [d for d in required if d not in chosen]
    if missing:
        raise ValueError("No contemporaneous verified mainline snapshot: " + ", ".join(missing))
    proof = []
    for day in required:
        source = chosen[day]
        before = len(state["picks"])
        state, _, captured = update(source["feed"], archive, state,
                                    datetime.fromisoformat(source["committed_at"]))
        if not captured:
            raise ValueError("Historical snapshot did not capture " + day)
        recovered_records=state["picks"][before:]+[
            s for s in state.get("empty_sessions",[]) if s["day"]==day]
        for pick in recovered_records:
            pick.update(origin="recovered_mainline_close_observation",
                        source_commit=source["sha"], source_blob=source["blob"],
                        source_committed_at=source["committed_at"])
        proof.append({"day": day, "source_commit": source["sha"],
                      "source_blob": source["blob"], "committed_at": source["committed_at"],
                      "feed_updated_at": source["feed"]["updated_at"],
                      "captured": len(state["picks"]) - before})
    return state, proof


def git_snapshots(ref, since):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT)
    lines = git("log", "--first-parent", "--reverse", "--format=%H %cI",
                "--since=" + since, ref, "--", "remote/system.json").decode().splitlines()
    for line in lines:
        sha, committed = line.split(" ", 1)
        raw = git("show", sha + ":remote/system.json")
        try:
            feed = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            continue  # A malformed historic publication is not usable evidence.
        blob = git("rev-parse", sha + ":remote/system.json").decode().strip()
        yield {"sha": sha, "blob": blob, "committed_at": committed, "feed": feed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="origin/main")
    parser.add_argument("--write", action="store_true", help="Append only after every missing day verifies")
    args = parser.parse_args()
    ledger = ROOT / "remote/pick_history.json"
    original = ledger.read_bytes()
    prior = json.loads(original)
    archive = json.loads((ROOT / "remote/daily_prices.json").read_bytes())
    last = last_sealed_day(prior)
    state, proof = recover(prior, archive, git_snapshots(args.ref, last), datetime.now(TZ))
    if args.write and proof:
        if ledger.read_bytes() != original:
            raise ValueError("Ledger changed during recovery")
        temp = ledger.with_suffix(".json.tmp")
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(ledger)
        evidence = {"schema": 1, "selection": "earliest_verified_first_parent_same_day_publication",
                    "prior_ledger_sha256": hashlib.sha256(original).hexdigest(),
                    "qualified_oos": False, "sessions": proof}
        path = ROOT / ("data/research_evidence/pick-recovery-" + datetime.now(TZ).strftime("%Y%m%d") + ".json")
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"write": args.write, "recovered_sessions": proof, "picks": len(state["picks"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
