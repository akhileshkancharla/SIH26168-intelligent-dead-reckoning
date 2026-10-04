#!/usr/bin/env python3
"""Generate the deterministic S1 delivery manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "S1_ARTIFACT_MANIFEST_v1.json"
EXCLUDED_PARTS = {"build", ".gradle", ".idea", "__pycache__"}


def role(path: str) -> str:
    if path == "README.md" or path.startswith("docs/"):
        return "documentation"
    if path.startswith("app/src/test/") or path.startswith("app/src/androidTest/") or path.startswith("tests/"):
        return "automated_test"
    if path.startswith("app/src/main/") or path.startswith("analyzer/"):
        return "source_code"
    if path.startswith("fixtures/"):
        return "synthetic_fixture"
    if path.startswith("results/"):
        return "verification_evidence"
    if path.startswith("scripts/"):
        return "tooling"
    return "build_system"


def classification(path: str) -> str:
    generated_prefixes = ("fixtures/deterministic_session/", "results/")
    generated_names = {"gradlew", "gradlew.bat", "gradle/wrapper/gradle-wrapper.jar"}
    return "generated" if path.startswith(generated_prefixes) or path in generated_names else "source"


def main() -> None:
    entries = []
    for candidate in sorted(ROOT.rglob("*")):
        if not candidate.is_file() or candidate == OUTPUT:
            continue
        relative = candidate.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS or part.endswith(".pyc") for part in relative.parts):
            continue
        data = candidate.read_bytes()
        path = relative.as_posix()
        entries.append({
            "path": path,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "artifact_role": role(path),
            "classification": classification(path),
        })
    payload = {
        "schema_version": "s1.artifact_manifest.v1",
        "artifact_root": ROOT.name,
        "hash_algorithm": "SHA-256",
        "self_exclusion": OUTPUT.name,
        "files": entries,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
