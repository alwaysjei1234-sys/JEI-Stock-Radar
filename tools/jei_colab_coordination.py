"""Publish a minimal Colab↔Actions coordination signal, never credentials.

Only an authenticated Google Drive heartbeat can upgrade Colab state.
GitHub Actions computes its existing fallback independently; it cannot
restart a disconnected free Colab runtime. Public status changes are
written only on state transitions to avoid hourly commit cascades.
"""
import argparse
import datetime as dt
import json
from pathlib import Path

VALID_STATES = {"RECENT_HEARTBEAT", "STALE", "UNKNOWN"}
STATUS_KEYS = ("schema", "colab_status", "reason", "evidence", "fallback",
               "restart_possible", "requested_action")


def sanitized_status(watchdog):
    if not isinstance(watchdog, dict):
        watchdog = {}
    state = watchdog.get("status")
    source = watchdog.get("drive_access")
    if source != "authenticated" or state not in VALID_STATES:
        state = "UNKNOWN"
        if source == "unconfigured":
            reason = "drive_configuration_missing"
        elif source == "unavailable":
            reason = "drive_read_failed"
        else:
            reason = "no_authenticated_heartbeat"
        evidence = "unverified"
    else:
        reason = {"RECENT_HEARTBEAT": "recent_heartbeat_not_proof_of_runtime",
                  "STALE": "heartbeat_expired",
                  "UNKNOWN": "invalid_or_unverified_heartbeat"}[state]
        evidence = "authenticated_google_drive_heartbeat"
    action = {"RECENT_HEARTBEAT": "colab_can_continue_if_kernel_is_running",
              "STALE": "inspect_colab_manually_actions_fallback_active",
              "UNKNOWN": "configure_or_verify_drive_heartbeat_actions_fallback_active"}[state]
    return {
        "schema": 1,
        "colab_status": state,
        "reason": reason,
        "evidence": evidence,
        "fallback": "github_actions",
        "restart_possible": False,
        "requested_action": action,
    }


def merge_status(watchdog, previous=None, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("timezone required")
    fresh = sanitized_status(watchdog)
    if isinstance(previous, dict) and all(previous.get(k) == fresh[k] for k in STATUS_KEYS):
        old_date = previous.get("status_changed_at_utc")
        try:
            instant = dt.datetime.fromisoformat(old_date.replace("Z", "+00:00"))
            if instant.tzinfo is not None and instant <= now:
                return {**fresh, "status_changed_at_utc": old_date}
        except (TypeError, ValueError, AttributeError):
            pass
    return {**fresh, "status_changed_at_utc": now.astimezone(dt.timezone.utc).isoformat()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watchdog", default="audit-output/colab_watchdog.json")
    parser.add_argument("--previous", default="remote/colab_coordination.json")
    parser.add_argument("--output", default="audit-output/colab_coordination.json")
    args = parser.parse_args()
    try:
        watchdog = json.loads(Path(args.watchdog).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        watchdog = None
    try:
        previous = json.loads(Path(args.previous).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = None
    result = merge_status(watchdog, previous)
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
