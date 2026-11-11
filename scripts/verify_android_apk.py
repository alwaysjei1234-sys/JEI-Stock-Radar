"""Verify aapt's built-APK identity before uploading a public Android artifact."""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def verify(badging, gradle):
    package = re.search(r"^package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", badging, re.M)
    code = re.search(r'\bversionCode\s+(\d+)', gradle)
    name = re.search(r"\bversionName\s+'([^']+)'", gradle)
    if not package or not code or not name:
        raise ValueError('Missing built APK identity or source version')
    if (package[1] != 'com.jei.stockradar' or int(package[2]) != int(code[1])
            or int(package[2]) <= 0 or package[3] != name[1]):
        raise ValueError('Built APK package/version differs from reviewed source')
    return {'package': package[1], 'versionCode': int(package[2]), 'versionName': package[3]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--badging', required=True)
    args = parser.parse_args()
    result = verify(Path(args.badging).read_text(), (ROOT / 'app/build.gradle').read_text())
    print('Verified built APK: {package} versionCode={versionCode} versionName={versionName}'.format(**result))


if __name__ == '__main__':
    main()
