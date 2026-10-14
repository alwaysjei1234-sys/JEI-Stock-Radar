import json
import os
import tempfile
import unittest
from unittest.mock import patch

from scripts import probe_production as probe


class ProductionProbeTests(unittest.TestCase):
    def test_distinguishes_vercel_login_from_application_401(self):
        self.assertEqual(
            probe.classify(403, "<title>Vercel Authentication</title>", "HTTP 403"),
            "VERCEL_LOGIN_PROTECTION",
        )
        self.assertEqual(
            probe.classify(401, '{"error":"JEI 私人連線碼不正確"}', "HTTP 401"),
            "AUTH_OR_ACCESS_BLOCK",
        )

    def test_manifest_is_a_published_github_apk_with_new_version(self):
        manifest = {
            "versionCode": 34,
            "url": "https://github.com/alwaysjei1234-sys/JEI-Stock-Radar/releases/download/jei-latest/JEI_Stock_Radar_V3.apk",
        }
        self.assertTrue(probe.health_manifest(manifest))
        self.assertFalse(probe.health_manifest({**manifest, "versionCode": 33}))
        self.assertFalse(probe.health_manifest({**manifest, "url": "https://wrong.invalid/app.apk"}))

    def test_html_sso_page_does_not_count_as_jei_token_denial(self):
        def fake_request(path, *, method="GET", **kwargs):
            if method == "POST":
                return 401, "<title>Vercel Authentication</title>", "HTTP 401"
            if path == "/api/consult":
                return 200, json.dumps({
                    "service": "JEI Free Multi-AI", "free_only": True,
                    "paid_gateway": False, "tokenRequired": True,
                    "providers": {"groq_oss": {}},
                }), ""
            if path == "/remote/system.json":
                return 200, '{"market":{},"data_date":"2026-10-14"}', ""
            if path == "/remote/index.html":
                return 200, "<!-- JEI_REMOTE_UI_V3 -->", ""
            if path == "/remote/update.json":
                return 200, json.dumps({
                    "versionCode": 34,
                    "url": "https://github.com/alwaysjei1234-sys/JEI-Stock-Radar/releases/download/jei-latest/JEI_Stock_Radar_V3.apk",
                }), ""
            raise AssertionError(path)

        with tempfile.TemporaryDirectory() as tmp:
            report = os.path.join(tmp, "health.json")
            with patch.object(probe, "REPORT", report), patch.object(probe, "request", fake_request):
                self.assertEqual(probe.main(), 1)
            with open(report, encoding="utf-8") as f:
                results = json.load(f)
            self.assertEqual(len(results), 5)
            self.assertTrue(all(x["available"] for x in results[:-1]))
            self.assertFalse(results[-1]["available"])

    def test_jei_json_401_is_accepted_without_model_calls(self):
        def fake_request(path, *, method="GET", **kwargs):
            if method == "POST":
                return 401, '{"error":"JEI 私人連線碼不正確"}', "HTTP 401"
            if path == "/api/consult":
                return 200, '{"service":"JEI Free Multi-AI","free_only":true,"paid_gateway":false,"tokenRequired":true,"providers":{"groq_oss":{}}}', ""
            if path == "/remote/system.json":
                return 200, '{"market":{},"data_date":"2026-10-14"}', ""
            if path == "/remote/index.html":
                return 200, "JEI_REMOTE_UI_V3", ""
            if path == "/remote/update.json":
                return 200, '{"versionCode":34,"url":"https://github.com/alwaysjei1234-sys/JEI-Stock-Radar/releases/download/jei-latest/JEI_Stock_Radar_V3.apk"}', ""
            raise AssertionError(path)

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(probe, "REPORT", os.path.join(tmp, "health.json")), patch.object(probe, "request", fake_request):
                self.assertEqual(probe.main(), 0)


if __name__ == "__main__":
    unittest.main()
