"""A new APK is never advertised without verified signer + version evidence."""
import unittest
from scripts.publish_android_update_manifest import STABLE_URL, build_manifest


def report(cert):
    return "Signer #1 certificate SHA-256 digest: " + cert


class AndroidUpdateManifestTests(unittest.TestCase):
    def setUp(self):
        self.cert = "8" * 64
        self.old = {"versionCode": 42, "versionName": "3.9.19 RISK GUARD",
                    "url": STABLE_URL, "uiVersion": "3.9.16-partial-quotes"}
        self.badging = "package: name='com.jei.stockradar' versionCode='43' versionName='3.9.20'"
        self.gradle = "versionCode 43\nversionName '3.9.20'"

    def build(self, **changes):
        options = {"badging": self.badging, "gradle": self.gradle,
                   "certificate_report": report(self.cert),
                   "expected_cert": self.cert, "previous": self.old}
        options.update(changes)
        return build_manifest(**options)

    def test_verified_upgrade_advertises_built_version_only(self):
        updated = self.build()
        self.assertEqual(updated["versionCode"], 43)
        self.assertEqual(updated["versionName"], "3.9.20")
        self.assertEqual(updated["signerSha256"], self.cert)
        self.assertEqual(updated["url"], STABLE_URL)
        self.assertEqual(self.old["versionCode"], 42)

    def test_signer_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            self.build(certificate_report=report("a" * 64))

    def test_built_apk_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "differs from reviewed source"):
            self.build(badging=self.badging.replace("versionCode='43'", "versionCode='42'"))

    def test_downgrade_rejected(self):
        with self.assertRaisesRegex(ValueError, "rolled back"):
            self.build(previous={**self.old, "versionCode": 44})

    def test_unexpected_update_location_rejected(self):
        with self.assertRaisesRegex(ValueError, "pinned release"):
            self.build(previous={**self.old, "url": "https://example.com/untrusted.apk"})

    def test_same_version_is_idempotent_not_republished(self):
        same = {**self.old, "versionCode": 43, "versionName": "3.9.20",
                "signerSha256": self.cert}
        self.assertIsNone(self.build(previous=same))
        with self.assertRaisesRegex(ValueError, "changed signing identity"):
            self.build(previous={**same, "signerSha256": "a" * 64})
        with self.assertRaisesRegex(ValueError, "different versionName"):
            self.build(previous={**same, "versionName": "3.9.19"})


if __name__ == "__main__":
    unittest.main()
