"""Colab heartbeat writer. Run inside a live Colab notebook after Drive mount.

Background thread only runs while the notebook kernel is alive.
No external API or Colab auto-restart is implied.
"""
import argparse
import datetime as dt
import json
import os
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
    return {"state": payload["colab_status"],
            "changed_at_utc": str(payload.get("status_changed_at_utc") or "")[:35]}



def heartbeat_payload(session_id, source_commit, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    return {"schema": 1, "provider": "google_colab",
            "session_id": session_id, "source_commit": source_commit,
            "heartbeat_at_utc": now.isoformat(),
            "runtime_claim": "not_independently_attested"}


def write_heartbeat(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def start_heartbeat(path, source_commit="unknown", interval_seconds=300,
                    coordination_reader=None):
    if interval_seconds < 30:
        raise ValueError("heartbeat interval must be at least 30 seconds")
    stop = threading.Event()
    session_id = str(uuid.uuid4())
    def worker():
        last_signal = None
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
                    except (OSError, ValueError, TypeError) as exc:
                        # Reading a remote status is optional; never stop the
                        # local heartbeat because GitHub is unavailable.
                        print("JEI Github coordination unavailable:",
                              type(exc).__name__, flush=True)
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
