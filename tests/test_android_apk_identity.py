import unittest
from scripts.verify_android_apk import verify, verify_signer


class ApkIdentityTests(unittest.TestCase):
    def test_built_artifact_identity_not_just_source_metadata(self):
        gradle = "versionCode 41\nversionName '3.9.18'"
        valid = "package: name='com.jei.stockradar' versionCode='41' versionName='3.9.18' platformBuildVersionName='15'\nsdkVersion:'26'"
        self.assertEqual(verify(valid, gradle)['versionCode'], 41)
        for broken in (valid.replace("versionCode='41'", "versionCode='40'"),
                       valid.replace("versionName='3.9.18'", "versionName='3.9.17'"),
                       valid.replace('com.jei.stockradar', 'other.app'),
                       'application-label:JEI', ''):
            with self.subTest(badging=broken), self.assertRaises(ValueError):
                verify(broken, gradle)


class AndroidSignerTests(unittest.TestCase):
    def test_release_signer_requires_one_pinned_sha256_certificate(self):
        expected = 'a' * 64
        pinned = 'Signer #1 certificate SHA-256 digest: ' + expected.upper()
        self.assertEqual(verify_signer(pinned, expected), expected)
        for report in ('', pinned.replace('SHA-256', 'SHA-1'),
                       pinned + '\nSigner #2 certificate SHA-256 digest: ' + 'b' * 64):
            with self.subTest(report=report), self.assertRaisesRegex(ValueError, 'one SHA-256'):
                verify_signer(report, expected)
        with self.assertRaisesRegex(ValueError, 'differs'):
            verify_signer(pinned, 'b' * 64)


if __name__ == '__main__':
    unittest.main()
