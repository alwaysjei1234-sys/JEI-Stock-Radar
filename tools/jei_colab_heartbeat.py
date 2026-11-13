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
from pathlib import Path


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


def start_heartbeat(path, source_commit="unknown", interval_seconds=300):
    if interval_seconds < 30:
        raise ValueError("heartbeat interval must be at least 30 seconds")
    stop = threading.Event()
    session_id = str(uuid.uuid4())
    def worker():
        while not stop.is_set():
            try:
                write_heartbeat(path, heartbeat_payload(session_id, source_commit))
            except OSError as exc:
                print("JEI heartbeat write failed:", exc, flush=True)
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
