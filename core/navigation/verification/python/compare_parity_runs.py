#!/usr/bin/env python3
"""Require two separately generated S2 parity result directories to match byte-for-byte."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ARTIFACTS = (
    "cpp_replay_states.csv",
    "cpp_replay_measurements.csv",
    "parity_results.json",
    "parity_details.jsonl",
    "PARITY_REPORT.md",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(first: Path, second: Path) -> dict:
    records = []
    for name in ARTIFACTS:
        first_hash = digest(first / name)
        second_hash = digest(second / name)
        records.append({
            "path": name,
            "first_sha256": first_hash,
            "second_sha256": second_hash,
            "byte_identical": first_hash == second_hash,
        })
    return {
        "schema_version": 1,
        "comparison": "byte-identical",
        "status": "passed" if all(record["byte_identical"] for record in records) else "failed",
        "artifacts": records,
    }


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: compare_parity_runs.py FIRST SECOND OUTPUT_JSON")
    result = compare(Path(sys.argv[1]), Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
