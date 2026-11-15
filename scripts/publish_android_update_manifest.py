"""Publish Android update metadata only after a stable, signed APK exists.

Call this *after* the release APK asset upload. Refuse malformed, mismatched,
downgraded, or unsigned metadata. Never modify private holdings or passwords.
"""
import argparse
import json
from pathlib import Path

from scripts.verify_android_apk import verify, verify_signer

STABLE_URL = (
    "https://github.com/alwaysjei1234-sys/JEI-Stock-Radar/"
    "releases/download/jei-latest/JEI_Stock_Radar_V3.apk"
)


def build_manifest(badging, gradle, certificate_report, expected_cert, previous):
    identity = verify(badging, gradle)
    signer = verify_signer(certificate_report, expected_cert)
    if not isinstance(previous, dict) or type(previous.get("versionCode")) is not int:
        raise ValueError("Invalid previous Android update metadata")
    old = previous["versionCode"]
    latest = identity["versionCode"]
    if old < 1 or latest < old:
        raise ValueError("Android release version cannot be rolled back")
    if previous.get("url") != STABLE_URL:
        raise ValueError("Published Android update URL is not the pinned release")
    if latest == old:
        if previous.get("versionName") != identity["versionName"]:
            raise ValueError("Same versionCode has a different versionName")
        if previous.get("signerSha256") not in (None, signer):
            raise ValueError("Same versionCode changed signing identity")
        # An already advertised version must never be silently republished.
        return None
    return {
        "versionCode": latest,
        "versionName": identity["versionName"],
        "uiVersion": previous.get("uiVersion", ""),
        "url": STABLE_URL,
        "signerSha256": signer,
        "message": "此版本須通過相同 Android 簽章才能覆蓋更新；請直接安裝，勿先解除安裝。"
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--badging", type=Path, required=True)
    parser.add_argument("--cert-report", type=Path, required=True)
    parser.add_argument("--gradle", type=Path, default=Path("app/build.gradle"))
    parser.add_argument("--manifest", type=Path, default=Path("remote/update.json"))
    parser.add_argument("--expected-cert", required=True)
    args = parser.parse_args()
    previous = json.loads(args.manifest.read_text(encoding="utf-8"))
    updated = build_manifest(
        args.badging.read_text(encoding="utf-8"),
        args.gradle.read_text(encoding="utf-8"),
        args.cert_report.read_text(encoding="utf-8"),
        args.expected_cert,
        previous,
    )
    if updated is None:
        print("Android update manifest already advertises this version; unchanged")
        return
    tmp = args.manifest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(args.manifest)
    print("Android update manifest verified and prepared: versionCode=" + str(updated["versionCode"]))


if __name__ == "__main__":
    main()
