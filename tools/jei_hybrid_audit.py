"""Isolated executable public-data audit. Never changes feeds or sends alerts.

Actions and Colab retain their existing independent deterministic audit.
The optional Ollama narrative is secondary; no AI output affects the audit.
"""
import argparse
import hashlib
import sqlite3
import json
import os
import tempfile
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

from jei_local_ai_router import MODEL, NoRedirect, route
from tools.jei_colab_coordination import merge_status, task_from_picks
from tools.jei_colab_heartbeat import audit_observed_picks
from tools.jei_hybrid_jobs import JobStore, job_key

MAX_BYTES = 2_000_000

def summary_counts(aggregate):
    counts = {k: aggregate[k] for k in
              ("eligible_aggregates", "underperforming_aggregates")}
    n, weak = counts.values()
    if type(n) is not int or type(weak) is not int or not 0 <= weak <= n <= 10000:
        raise ValueError("invalid counts")
    return counts

def validate_summary_response(result, counts):
    if not isinstance(result, dict) or result.get("model") != MODEL or result.get("done") is not True:
        raise ValueError("incomplete_model_response")
    if result.get("done_reason") != "stop":
        raise ValueError("model_token_limit" if result.get("done_reason") == "length" else "unexpected_done_reason")
    message = result.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise ValueError("invalid_model_message")
    try:
        payload = json.loads(message["content"])
    except ValueError:
        raise ValueError("invalid_model_json") from None
    n, weak = counts.values()
    expected = "no_samples" if n == 0 else "all_weak" if weak == n else "none_weak" if weak == 0 else "some_weak"
    if (not isinstance(payload, dict) or set(payload) != {"eligible_aggregates", "underperforming_aggregates", "classification"}
            or any(type(payload.get(k)) is not int or payload[k] != v for k,v in counts.items())
            or payload.get("classification") != expected):
        raise ValueError("incorrect_model_classification")
    # Render verified facts ourselves, never publish free-form model thoughts.
    return f"符合門檻的觀察統計共 {n} 組，其中 {weak} 組未達績效標準。此為既有觀察統計，並非獨立樣本外回測。"

def local_summary(aggregate):
    # Only two validated integer aggregates are sent. No free-form input,
    # stock holdings, credentials, or raw feed content reaches this endpoint.
    counts = summary_counts(aggregate)
    schema = {"type":"object","additionalProperties":False,
              "required":["eligible_aggregates","underperforming_aggregates","classification"],
              "properties":{"eligible_aggregates":{"type":"integer"},
                            "underperforming_aggregates":{"type":"integer"},
                            "classification":{"type":"string","enum":["no_samples","all_weak","none_weak","some_weak"]}}}
    body = {"model": MODEL, "stream": False, "format": schema,
        "messages": [{"role":"system","content":"Return only JSON. Copy both integer counts exactly. Classification: no_samples if eligible is zero; all_weak if weak equals eligible and eligible > 0; none_weak if weak is zero and eligible > 0; otherwise some_weak."},
                     {"role":"user","content":json.dumps(counts)}],
        "options":{"num_predict":256,"temperature":0}}
    if MODEL.startswith("qwen3:"):
        body["think"] = False
        body["messages"][-1]["content"] += " /no_think"
    request = Request("http://127.0.0.1:11434/api/chat",
                      data=json.dumps(body).encode(), method="POST",
                      headers={"Content-Type": "application/json"})
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=45) as res:
        raw = res.read(65537)
    if len(raw) > 65536:
        raise ValueError("oversized model response")
    result = json.loads(raw)
    return validate_summary_response(result, counts)

def run_audit(raw, *, enabled=False, local_available=False, watchdog=None,
              summarize=local_summary, job_store=None):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise ValueError("invalid input size")
    picks = json.loads(raw)
    task = task_from_picks(picks, versioned=True)
    if not task:
        raise ValueError("invalid public audit task")
    # Execute existing deterministic computation even when Colab is offline.
    observed = audit_observed_picks(task, fetcher=lambda: raw)
    coordination = merge_status(watchdog, picks=picks, versioned=True)
    recent = (isinstance(watchdog, dict)
              and watchdog.get("drive_access") == "authenticated"
              and watchdog.get("status") == "RECENT_HEARTBEAT")
    decision = route(data_class="public", enabled=enabled,
                     local_available=local_available,
                     colab_coordination=coordination,
                     colab_heartbeat_verified=recent,
                     colab_task_supported=True, task_kind=task["kind"])
    result = {"task_id": task["task_id"], "observed": observed,
              "routing_candidate": decision,
              "colab_status": coordination["colab_status"],
              "colab_ack": coordination["colab_task_ack"],
              "dispatch_performed": False,
              "narrative_status": "not_requested", "narrative_source": None}
    if decision == "local_candidate":
        try:
            if job_store is None:
                result["narrative"] = summarize(observed)
                result["narrative_source"] = "model"
            else:
                engine = hashlib.sha256(b"".join(
                    (Path(__file__).parent / name).read_bytes()
                    for name in ("jei_hybrid_audit.py", "jei_colab_heartbeat.py",
                                 "jei_hybrid_jobs.py"))).hexdigest()
                key = job_key(task["task_id"].encode("ascii"), MODEL, engine)
                result["narrative"], result["narrative_source"] = (
                    job_store.summarize_once(key, observed, summarize))
            result["narrative_status"] = "local_model_returned_unverified_text"
        except (OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error) as exc:
            result["narrative_error_type"] = type(exc).__name__
            safe_codes = {"incomplete_model_response", "model_token_limit", "unexpected_done_reason",
                          "invalid_model_message", "invalid_model_json", "incorrect_model_classification"}
            result["narrative_error_code"] = str(exc) if isinstance(exc, ValueError) and str(exc) in safe_codes else "other"
            result["narrative_status"] = "local_failed_deterministic_audit_retained"
            result["routing_candidate"] = route(
                data_class="public", enabled=enabled, local_available=False,
                colab_coordination=coordination,
                colab_heartbeat_verified=recent, colab_task_supported=True,
                task_kind=task["kind"])
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-ai", action="store_true",
                        help="opt in only after local/offline model setup is verified")
    parser.add_argument("--check-colab", action="store_true",
                        help="read current authorized Drive heartbeat if configured")
    parser.add_argument("--job-db", default="audit-output/hybrid_jobs.sqlite3",
                        help="persistent local disk only; never sync this database across devices")
    args = parser.parse_args()
    with Path("remote/pick_validation.json").open("rb") as f:
        raw = f.read(MAX_BYTES + 1)
    watchdog = None
    if args.check_colab:
        from tools.jei_drive_heartbeat_ingest import ingest
        with tempfile.TemporaryDirectory() as d:
            watchdog = ingest(os.environ.get("JEI_COLAB_HEARTBEAT_FILE_ID"),
                              os.environ.get("JEI_DRIVE_SERVICE_ACCOUNT_JSON"),
                              str(Path(d) / "watchdog.json"))
    from jei_local_ai_router import local_ready
    available = args.local_ai and local_ready()
    job_store = None
    if available:
        try:
            job_store = JobStore(args.job_db)
        except (OSError, sqlite3.Error):
            available = False  # never run without the requested persistent guard
    result = run_audit(raw, enabled=args.local_ai or args.check_colab,
                       local_available=available,
                       watchdog=watchdog, job_store=job_store)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
