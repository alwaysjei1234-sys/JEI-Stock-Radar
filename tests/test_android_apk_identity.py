import unittest
from scripts.verify_android_apk import verify


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


if __name__ == '__main__':
    unittest.main()
