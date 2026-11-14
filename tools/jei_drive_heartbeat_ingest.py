"""Optional authenticated Google Drive heartbeat ingestion for GitHub Actions.

Requires a dedicated read-only service account shared on the heartbeat file.
No credential or heartbeat is committed to the repository.
"""
import argparse
import json
import os
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
        except Exception as exc:
            result = assess(None)
            result.update(drive_access="unavailable", reason="drive_read_failed",
                          error_type=type(exc).__name__)
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
