"""Colab heartbeat writer. Run inside a live Colab notebook after Drive mount.

Background thread only runs while the notebook kernel is alive.
No external API or Colab auto-restart is implied.
"""
import argparse
import datetime as dt
import json
import hashlib
import os
import math
import re
import threading
import time
import uuid
import urllib.request
from pathlib import Path

# Public, credential-free GitHub signal. This is only a work coordination hint,
# not a command to run unsafe code or a way to wake a disconnected Colab kernel.
COORDINATION_URL = (
    "https://raw.githubusercontent.com/alwaysjei1234-sys/"
    "JEI-Stock-Radar/main/remote/colab_coordination.json"
)
VALID_SIGNAL_STATES = {"RECENT_HEARTBEAT", "STALE", "UNKNOWN"}
# A temporarily unavailable GitHub snapshot must not permanently disable a
# day's Colab -> Actions verification task while the Colab kernel is alive.
TASK_RETRY_BUDGET = 3
TASK_RETRY_COOLDOWN_SECONDS = 30 * 60


def observed_snapshot_digest(picks):
    """Version the public aggregate input, excluding irrelevant timestamp metadata."""
    payload = {"latest_official_day": picks["latest_official_day"],
               "groups": picks["groups"]}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def valid_observed_task_id(task_id, day=None):
    if not isinstance(task_id, str):
        return False
    match = re.fullmatch(r"observed-(20\d{2}-\d{2}-\d{2})(?:-([0-9a-f]{64}))?", task_id)
    if match is None or (day is not None and match.group(1) != day):
        return False
    try:
        dt.date.fromisoformat(match.group(1))
    except ValueError:
        return False
    return True


def allow_task_attempt(attempts, key, now=None):
    """Allow three attempts, pause 30m, then retry; bound state to one task.

    A transient 404, date rollover, CDN delay, or rate limit must not consume
    an official trading day's task forever. The cooldown also prevents busy
    loops if the public data never becomes valid.
    """
    now = time.monotonic() if now is None else now
    previous = attempts.get(key)
    if (previous is None or now < previous[1] or
            now - previous[1] >= TASK_RETRY_COOLDOWN_SECONDS):
        attempts.clear()
        attempts[key] = (1, now)
        return True
    count, _ = previous
    if count >= TASK_RETRY_BUDGET:
        return False
    attempts[key] = (count + 1, now)
    return True


def retain_current_task_result(last_result, task):
    """Never re-advertise yesterday's completion as today's task response.

    GitHub's public coordination may move to a new official trading day while
    the same Colab kernel stays alive. Drop the previous result before deciding
    whether to send an Actions review request for the current task.
    """
    if not isinstance(task, dict) or not isinstance(last_result, dict):
        return None
    if last_result.get("task_id") != task.get("task_id"):
        return None
    if last_result.get("status") != "completed" or last_result.get("observed_only") is not True:
        return None
    return last_result


def read_github_coordination():
    """Poll the shared Actions status once per heartbeat while Colab is alive."""
    request = urllib.request.Request(
        COORDINATION_URL, headers={"User-Agent": "JEI-Colab-Heartbeat/1.0",
                                   "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read(4096)
    payload = json.loads(raw.decode("utf-8"))
    if (not isinstance(payload, dict) or payload.get("schema") != 1
            or payload.get("colab_status") not in VALID_SIGNAL_STATES
            or payload.get("fallback") != "github_actions"
            or payload.get("restart_possible") is not False):
        raise ValueError("untrusted_github_coordination")
    # Allowlist only, never read code execution commands from remote JSON.
    signal = {"state": payload["colab_status"],
              "changed_at_utc": str(payload.get("status_changed_at_utc") or "")[:35]}
    task = payload.get("colab_task")
    if isinstance(task, dict):
        day, task_id = task.get("official_day"), task.get("task_id")
        if (task.get("kind") == "audit_observed_picks"
                and isinstance(day, str)
                and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", day)
                and valid_observed_task_id(task_id, day)):
            signal["task"] = {"kind": "audit_observed_picks",
                              "task_id": task_id, "official_day": day}
    return signal


def audit_observed_picks(task, fetcher=None):
    """Independent recomputation of existing aggregates (NOT OOS validation).

    Executes only one fixed, built-in operation and reads a bounded public JSON.
    No remote code execution, shell, trading, or private data.
    """
    if (not isinstance(task, dict) or task.get("kind") != "audit_observed_picks"
            or not isinstance(task.get("official_day"), str)
            or not valid_observed_task_id(task.get("task_id"), task["official_day"])):
        raise ValueError("unsupported_colab_task")
    day = task["official_day"]
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", day):
        raise ValueError("invalid_task_date")
    url = ("https://raw.githubusercontent.com/alwaysjei1234-sys/"
           "JEI-Stock-Radar/main/remote/pick_validation.json")
    if fetcher is None:
        def fetcher():
            request = urllib.request.Request(url, headers={"User-Agent": "JEI-Colab-Observed-Check"})
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.read(2_000_001)
    raw = fetcher()
    if not isinstance(raw, bytes) or len(raw) > 2_000_000:
        raise ValueError("observed_data_invalid_or_oversize")
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("latest_official_day") != day:
        raise ValueError("official_date_changed")
    groups = data.get("groups")
    if not isinstance(groups, dict):
        raise ValueError("missing_observed_groups")
    if task["task_id"] != "observed-" + day:
        expected = "observed-" + day + "-" + observed_snapshot_digest(data)
        if task["task_id"] != expected:
            raise ValueError("official_snapshot_changed")
    eligible = 0
    weak = 0
    for horizons in groups.values():
        if not isinstance(horizons, dict):
            continue
        for period in ("3", "7", "15", "30"):
            stats = horizons.get(period)
            if not isinstance(stats, dict):
                continue
            n, win, net = (stats.get(key) for key in
                           ("completed", "win_rate_pct", "avg_estimated_net_pct"))
            if (type(n) is not int or n < 30 or type(win) not in (int, float)
                    or type(net) not in (int, float)
                    or not math.isfinite(win) or not math.isfinite(net)
                    or not 0 <= win <= 100 or net < -100):
                continue
            eligible += 1
            if net <= 0 or win < 50:
                weak += 1
    return {"task_id": task["task_id"], "status": "completed",
            "observed_only": True, "eligible_aggregates": eligible,
            "underperforming_aggregates": weak}




def heartbeat_payload(session_id, source_commit, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    return {"schema": 1, "provider": "google_colab",
            "session_id": session_id, "source_commit": source_commit,
            "heartbeat_at_utc": now.isoformat(),
            "runtime_claim": "not_independently_attested"}


def write_heartbeat(path, payload, *, preserve_drive_id=None):
    """Persist a heartbeat while preserving a mounted Drive file's identity.

    os.replace() works atomically on local POSIX files, but a Drive FUSE
    rename/replace can delete and recreate a cloud file with a NEW file ID.
    GitHub's read-only service account tracks that file ID, not the name.
    Write the existing Drive mount file in place instead; a concurrent Drive
    read may temporarily see partial JSON and must fail closed/retry.
    Other paths keep their previous atomic replace behavior.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if preserve_drive_id is None:
        # Actual Google Colab Drive mount, not local Unix scratch/temp files.
        preserve_drive_id = path.as_posix().startswith("/content/drive/")
    data = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if preserve_drive_id:
        # Truncates/reuses the same path-backed Drive item rather than a
        # rename. Its exact remote ID must still be verified on Google Drive.
        path.write_text(data, encoding="utf-8")
    else:
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(data, encoding="utf-8")
        os.replace(temp, path)


def start_heartbeat(path, source_commit="unknown", interval_seconds=300,
                    coordination_reader=None, task_runner=None):
    if interval_seconds < 30:
        raise ValueError("heartbeat interval must be at least 30 seconds")
    stop = threading.Event()
    session_id = str(uuid.uuid4())
    # Publish first heartbeat before any network request/task execution; an
    # unavailable GitHub coordination URL must not delay Colab liveness.
    write_heartbeat(path, heartbeat_payload(session_id, source_commit))
    def worker():
        last_signal = None
        last_task_result = None
        task_attempts = {}
        while not stop.is_set():
            try:
                payload = heartbeat_payload(session_id, source_commit)
                if coordination_reader is not None:
                    try:
                        signal = coordination_reader()
                        if isinstance(signal, dict) and signal.get("state") in VALID_SIGNAL_STATES:
                            payload["github_coordination"] = {
                                "state": signal["state"],
                                "changed_at_utc": str(signal.get("changed_at_utc") or "")[:35]}
                            if signal["state"] != last_signal:
                                print("JEI GitHub coordination:", signal["state"],
                                      "(Actions fallback remains independent)", flush=True)
                                last_signal = signal["state"]
                            task = signal.get("task")
                            # A result for a previous official date must not
                            # trigger stale review_pick_quality requests after
                            # the Actions-side task advances to a new day.
                            last_task_result = retain_current_task_result(last_task_result, task)
                            if task_runner is not None and isinstance(task, dict):
                                key = task["task_id"]
                                already_completed = (isinstance(last_task_result, dict)
                                    and last_task_result.get("task_id") == key
                                    and last_task_result.get("status") == "completed")
                                if not already_completed and allow_task_attempt(task_attempts, key):
                                    try:
                                        result = task_runner(task)
                                        if (isinstance(result, dict)
                                                and result.get("task_id") == key
                                                and result.get("status") == "completed"
                                                and result.get("observed_only") is True):
                                            last_task_result = {k: result[k] for k in (
                                                "task_id", "status", "observed_only",
                                                "eligible_aggregates", "underperforming_aggregates")
                                                if k in result}
                                            print("JEI Colab task completed:", key, flush=True)
                                    except (OSError, ValueError, TypeError, KeyError) as exc:
                                        print("JEI Colab task retry:", type(exc).__name__, flush=True)

                    except (OSError, ValueError, TypeError) as exc:
                        # Reading a remote status is optional; never stop the
                        # local heartbeat because GitHub is unavailable.
                        print("JEI Github coordination unavailable:",
                              type(exc).__name__, flush=True)
                if isinstance(last_task_result, dict):
                    payload["colab_task_result"] = last_task_result
                    if last_task_result.get("underperforming_aggregates", 0) > 0:
                        # A bounded suggestion. GitHub runs read-only audits
                        # only after authenticating this Drive heartbeat.
                        payload["actions_request"] = "review_pick_quality"
                write_heartbeat(path, payload)
            except OSError as exc:
                print("JEI heartbeat write failed:", type(exc).__name__, flush=True)
            stop.wait(interval_seconds)
    thread = threading.Thread(target=worker, name="jei-colab-heartbeat", daemon=True)
    thread.start()
    return stop, thread


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    parser.add_argument("--source-commit", default="unknown")
    parser.add_argument("--interval-seconds", type=int, default=300)
    args = parser.parse_args()
    stop, thread = start_heartbeat(args.path, args.source_commit, args.interval_seconds)
    try:
        while thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
