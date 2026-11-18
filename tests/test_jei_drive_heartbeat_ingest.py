"""Credential-free integration guards for Google Drive reader error reporting."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.jei_drive_heartbeat_ingest import ingest


class DummyHTTPError(Exception):
    def __init__(self, code):
        # The response text/exception might contain credentials. Never publish.
        self.response = SimpleNamespace(status_code=code)
        super().__init__("SENSITIVE_TOKEN=NEVER_PRINT_THIS")


class DriveHeartbeatIngestDiagnosticsTests(unittest.TestCase):
    def ingest_error(self, error):
        with tempfile.TemporaryDirectory() as root, patch(
                "tools.jei_drive_heartbeat_ingest.download_heartbeat",
                side_effect=error):
            target = Path(root) / "watchdog.json"
            result = ingest("nonsecret-file-id", "NEVER_PRINT_THIS", target)
            self.assertEqual(json.loads(target.read_text()), result)
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["reason"], "drive_read_failed")
            self.assertEqual(result["drive_access"], "unavailable")
            self.assertNotIn("NEVER_PRINT_THIS", json.dumps(result))
            self.assertFalse(result["restart_possible"])
            return result

    def test_safe_http_status_is_visible_without_full_exception(self):
        expected = {
            400: "invalid_drive_request",
            401: "check_service_account_key",
            403: "check_drive_api_enabled_and_file_share",
            404: "check_file_id_and_file_share",
            429: "drive_api_rate_limited",
            503: "drive_api_transient_error",
        }
        for code, hint in expected.items():
            with self.subTest(code=code):
                result = self.ingest_error(DummyHTTPError(code))
                self.assertEqual(result["http_status"], code)
                self.assertEqual(result["safe_hint"], hint)
                self.assertNotIn("SENSITIVE_TOKEN", json.dumps(result))

    def test_whitelist_provider_reason_without_leaking_google_error_body(self):
        for reason in ("insufficientFilePermissions", "accessNotConfigured",
                       "serviceDisabled", "SERVICE_DISABLED", "domainPolicy",
                       "PERMISSION_DENIED"):
            with self.subTest(reason=reason):
                response = SimpleNamespace(
                    status_code=403,
                    json=lambda: {"error": {
                        "message": "private_key NEVER_PRINT_THIS",
                        "errors": [{"reason": reason, "message": "NEVER_PRINT_THIS"}]}})
                error = DummyHTTPError(403)
                error.response = response
                result = self.ingest_error(error)
                self.assertEqual(result.get("google_error_reason"), reason)
                self.assertNotIn("private_key", json.dumps(result))
        bad = DummyHTTPError(403)
        bad.response = SimpleNamespace(status_code=403,
                                       json=lambda: {"error": {"errors": [
                                           {"reason": "secret=NEVER_PRINT_THIS"}]}})
        result = self.ingest_error(bad)
        self.assertNotIn("google_error_reason", result)

    def test_service_account_identity_is_boolean_not_logged(self):
        email = "jei-colab-heartbeat-reader@jei-stock-radar.iam.gserviceaccount.com"
        credential = json.dumps({"project_id": "jei-stock-radar",
                                 "client_email": email, "private_key": "NEVER_PRINT_THIS"})
        error = DummyHTTPError(403)
        with tempfile.TemporaryDirectory() as root, patch(
                "tools.jei_drive_heartbeat_ingest.download_heartbeat",
                side_effect=error):
            result = ingest("mock-id", credential, Path(root) / "watchdog.json")
        self.assertIs(result["service_account_matches_drive_share"], True)
        self.assertNotIn(email, json.dumps(result))
        self.assertNotIn("NEVER_PRINT_THIS", json.dumps(result))
        with tempfile.TemporaryDirectory() as root, patch(
                "tools.jei_drive_heartbeat_ingest.download_heartbeat",
                side_effect=error):
            incorrect = ingest("mock-id", credential.replace("jei-stock-radar", "other-project"),
                               Path(root) / "watchdog.json")
        self.assertIs(incorrect["service_account_matches_drive_share"], False)

    def test_network_failure_has_no_invented_http_status(self):
        result = self.ingest_error(OSError("token=NEVER_PRINT_THIS"))
        self.assertEqual(result["error_type"], "OSError")
        self.assertNotIn("http_status", result)
        self.assertNotIn("safe_hint", result)

    def test_missing_config_remains_distinct_from_api_failure(self):
        with tempfile.TemporaryDirectory() as root:
            report = ingest("", "", Path(root) / "x.json")
        self.assertEqual(report["drive_access"], "unconfigured")
        self.assertEqual(report["reason"], "drive_configuration_missing")
        self.assertEqual(set(report["missing_configuration"]),
                         {"file_id", "service_account"})


if __name__ == "__main__":
    unittest.main()
