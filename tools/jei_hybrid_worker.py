"""Pull a public audit task from the existing GitHub/Colab manifest.

One-shot by default; suitable for an explicitly installed local scheduled task.
Never uploads anything or accepts arbitrary instructions or URLs.
"""
import argparse
from http.client import HTTPException
import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

from jei_local_ai_router import NoRedirect, local_ready, read_response
from tools.jei_colab_heartbeat import read_github_coordination
from tools.jei_colab_coordination import task_from_picks
from tools.jei_hybrid_audit import MAX_BYTES, run_audit, local_summary
from tools.jei_hybrid_jobs import JobStore

PICKS_URL = ("https://raw.githubusercontent.com/alwaysjei1234-sys/"
             "JEI-Stock-Radar/main/remote/pick_validation.json")

def fetch_public_picks():
    request = Request(PICKS_URL, headers={"User-Agent": "JEI-Hybrid-Worker/1.0",
                                         "Cache-Control": "no-cache"})
    deadline = time.monotonic() + 20
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=20) as response:
        return read_response(response, deadline, MAX_BYTES)

def atomic_receipt(folder, result):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    suffix = "-summary" if "narrative" in result else "-deterministic"
    target = folder / (result["task_id"] + suffix + ".json")
    # Separate deterministic and narrative receipts. A busy worker cannot
    # overwrite a completed narrative with its deterministic-only fallback.
    fd, temp = tempfile.mkstemp(prefix=".receipt-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, allow_nan=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp, target)  # create once on a local NTFS/POSIX filesystem
        except FileExistsError:
            pass
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return target

def pull_once(*, output_dir, job_db, enable_local=False,
              reader=read_github_coordination, fetcher=fetch_public_picks,
              probe=local_ready, summarize=local_summary):
    try:
        signal = reader()
        task = signal.get("task") if isinstance(signal, dict) else None
        if not isinstance(task, dict):
            return {"status": "no_supported_task", "uploaded": False}
        raw = fetcher()
        if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
            raise ValueError("invalid input size")
        picks = json.loads(raw)
        expected = task_from_picks(picks, versioned=True)
        if not expected or task != expected:
            return {"status": "snapshot_mismatch_or_legacy_task", "uploaded": False}
        available = enable_local and probe()
        store = None
        if available:
            try:
                store = JobStore(job_db)
            except (OSError, sqlite3.Error):
                available = False
        result = run_audit(raw, enabled=enable_local, local_available=available,
                           summarize=summarize, job_store=store)
        # Re-read both signals: same-day publication can race with inference.
        after = reader()
        after_raw = fetcher()
        if not isinstance(after_raw, bytes) or len(after_raw) > MAX_BYTES:
            raise ValueError("invalid current snapshot size")
        if (not isinstance(after, dict) or after.get("task") != expected
                or task_from_picks(json.loads(after_raw), versioned=True) != expected):
            return {"status": "superseded", "task_id": expected["task_id"],
                    "uploaded": False}
        receipt = {"schema": 1, "task_id": expected["task_id"],
                   "kind": expected["kind"], "data_class": "public",
                   "observed": result["observed"],
                   "narrative_status": result["narrative_status"],
                   "narrative_source": result["narrative_source"],
                   "routing_candidate": result["routing_candidate"],
                   "uploaded": False}
        if "narrative" in result:
            receipt["narrative"] = result["narrative"]
        path = atomic_receipt(output_dir, receipt)
        return {"status": "receipt_saved", "task_id": expected["task_id"],
                "receipt": str(path), "narrative_source": receipt["narrative_source"],
                "uploaded": False}
    except (HTTPException, OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error) as exc:
        return {"status": "retry_later", "error_type": type(exc).__name__, "uploaded": False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-ai", action="store_true",
                        help="enable verified offline local model; no uploads")
    parser.add_argument("--output-dir", default="audit-output/hybrid-receipts")
    parser.add_argument("--job-db", default="audit-output/hybrid_jobs.sqlite3")
    args = parser.parse_args()
    result = pull_once(output_dir=args.output_dir, job_db=args.job_db,
                       enable_local=args.local_ai)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "receipt_saved" else 2

if __name__ == "__main__":
    raise SystemExit(main())
