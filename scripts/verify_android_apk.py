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


def verify_signer(report, expected):
    digests = re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]{64})\s*$', report, re.M)
    if len(digests) != 1:
        raise ValueError('Expected one SHA-256 certificate digest from apksigner')
    actual = digests[0].lower()
    if actual != expected.lower():
        raise ValueError(f'APK signer differs from stable signer (actual={actual}, expected={expected.lower()})')
    return actual


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--badging')
    source.add_argument('--cert-report', type=Path)
    parser.add_argument('--expected-cert')
    args = parser.parse_args()
    if args.cert_report:
        if not args.expected_cert or not re.fullmatch(r'[0-9a-fA-F]{64}', args.expected_cert):
            parser.error('--cert-report requires a 64-digit --expected-cert')
        try:
            print('Verified stable APK signer: ' + verify_signer(args.cert_report.read_text(), args.expected_cert))
        except ValueError as error:
            parser.exit(1, str(error) + '\n')
        return
    result = verify(Path(args.badging).read_text(), (ROOT / 'app/build.gradle').read_text())
    print('Verified built APK: {package} versionCode={versionCode} versionName={versionName}'.format(**result))


if __name__ == '__main__':
    main()
