"""Optional authenticated Google Drive heartbeat ingestion for GitHub Actions.

Requires a dedicated read-only service account shared on the heartbeat file.
No credential or heartbeat is committed to the repository.
"""
import argparse
import json
import os
import re
from pathlib import Path
from tools.jei_colab_watchdog import assess


def download_heartbeat(file_id, service_account_json):
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    if not file_id or not service_account_json:
        raise ValueError("missing_drive_configuration")
    info = json.loads(service_account_json)
    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    session = AuthorizedSession(credentials)
    response = session.get(
        "https://www.googleapis.com/drive/v3/files/" + file_id,
        params={"alt": "media"}, timeout=20)
    response.raise_for_status()
    return response.json()


def ingest(file_id, credential_json, out):
    missing = [name for name, value in (("file_id", file_id), ("service_account", credential_json))
               if not value]
    if missing:
        result = assess(None)
        result.update(drive_access="unconfigured", reason="drive_configuration_missing",
                      missing_configuration=missing)
    else:
        try:
            report = download_heartbeat(file_id, credential_json)
            result = assess(report)
            result["drive_access"] = "authenticated"
            # Optional Colab→GitHub work request. The service account already
            # authenticates the Drive file; still allowlist fields strictly.
            # It only triggers read-only CI diagnostics, never deployment.
            if result["status"] == "RECENT_HEARTBEAT" and isinstance(report, dict):
                if report.get("actions_request") == "review_pick_quality":
                    result["colab_request"] = "review_pick_quality"
                ack = report.get("colab_task_result")
                if isinstance(ack, dict):
                    task_id = ack.get("task_id")
                    if (isinstance(task_id, str)
                            and re.fullmatch(r"observed-20\d{2}-\d{2}-\d{2}", task_id)
                            and ack.get("status") == "completed"
                            and ack.get("observed_only") is True):
                        result["colab_task_result"] = {
                            "task_id": task_id, "status": "completed",
                            "observed_only": True}

        except Exception as exc:
            # Never log the service-account JSON, response body, request URL,
            # or full exception text (all may contain sensitive information).
            # Preserve only HTTP status and a small diagnostic classification
            # so an API-disabled 403 can be distinguished from a wrong-file 404.
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
            status = status if type(status) is int and 400 <= status <= 599 else None
            result = assess(None)
            result.update(drive_access="unavailable", reason="drive_read_failed",
                          error_type=type(exc).__name__)
            if status is not None:
                result["http_status"] = status
                result["safe_hint"] = {
                    400: "invalid_drive_request",
                    401: "check_service_account_key",
                    403: "check_drive_api_enabled_and_file_share",
                    404: "check_file_id_and_file_share",
                    429: "drive_api_rate_limited",
                    500: "drive_api_transient_error",
                    502: "drive_api_transient_error",
                    503: "drive_api_transient_error",
                    504: "drive_api_transient_error",
                }.get(status, "inspect_drive_api_permissions")
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="audit-output/colab_watchdog.json")
    args = parser.parse_args()
    result = ingest(os.environ.get("JEI_COLAB_HEARTBEAT_FILE_ID"),
                    os.environ.get("JEI_DRIVE_SERVICE_ACCOUNT_JSON"), args.output)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
