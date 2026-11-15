"""Ensure stable Android updates fail closed and never rotate keys silently."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AndroidOtaWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flow = (ROOT / ".github/workflows/build-apk.yml").read_text(encoding="utf-8")
        cls.script = (ROOT / "scripts/publish_android_update_manifest.py").read_text(encoding="utf-8")

    def test_original_keystore_required_no_debug_regeneration(self):
        self.assertIn("secrets.JEI_STABLE_KEYSTORE_B64", self.flow)
        self.assertIn("secrets.JEI_STORE_PASSWORD", self.flow)
        self.assertIn("secrets.JEI_KEY_ALIAS", self.flow)
        self.assertIn("secrets.JEI_KEY_PASSWORD", self.flow)
        self.assertIn("keytool -exportcert", self.flow)
        self.assertNotIn("keytool -genkeypair", self.flow)
        self.assertNotIn("actions/cache/restore", self.flow)
        self.assertNotIn("actions/cache@v4", self.flow)
        self.assertIn("807326371643b70ec340b8fd526568adb9ff86c8186e059ca6bc5d0633e4cbdd", self.flow)

    def test_signed_release_and_metadata_publication_order(self):
        self.assertIn("gradle :app:assembleRelease", self.flow)
        self.assertIn("app/build/outputs/apk/release/app-release.apk", self.flow)
        self.assertNotIn("gradle :app:assembleDebug", self.flow)
        self.assertIn("python -m scripts.publish_android_update_manifest", self.flow)
        positions = [self.flow.index(x) for x in (
            "      - name: Verify stable update signer",
            "      - name: Check Android upgrade version is newer",
            "      - name: Publish stable APK download",
            "      - name: Advertise version only after signed APK release asset exists")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("if: steps.upgrade.outputs.publish == 'true'", self.flow)
        self.assertIn("git push origin HEAD:main", self.flow)

    def test_metadata_never_claims_automatic_install_or_new_signer(self):
        self.assertIn("verify_signer(", self.script)
        self.assertIn("version cannot be rolled back", self.script)
        self.assertIn("STABLE_URL", self.script)


if __name__ == "__main__":
    unittest.main()
