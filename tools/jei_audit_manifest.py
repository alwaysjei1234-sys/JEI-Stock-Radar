"""Index the compute files emitted by the JEI Actions audit."""
import argparse
import hashlib
import json
import os
from pathlib import Path

OUTPUTS = (
    "colab_watchdog.json", "compute_provenance.json", "jei_audit.json",
    "jei_observed_compute.json", "observed_checkpoint.json", "pick_quality.json",
    "resumable_observed.json", "working_31_item_checklist.json",
)


def build_manifest(directory, env):
    files = {}
    for name in OUTPUTS:
        path = directory / name
        if path.is_file():
            content = path.read_bytes()
            files[name] = {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
    missing = sorted(set(OUTPUTS) - files.keys())
    return {
        "schema": 1,
        "provider": "github_actions",
        "event": env.get("GITHUB_EVENT_NAME"),
        "run_id": env.get("GITHUB_RUN_ID"),
        "run_attempt": env.get("GITHUB_RUN_ATTEMPT"),
        "source_commit": env.get("GITHUB_SHA"),
        "files": files,
        "missing": missing,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=Path("audit-output"))
    directory = parser.parse_args().directory
    directory.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(directory, os.environ)
    (directory / "artifact_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
