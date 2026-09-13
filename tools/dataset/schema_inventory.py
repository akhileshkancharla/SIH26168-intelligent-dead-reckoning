"""Private header-only inventory; fingerprints are candidates, never approved IDs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def describe_header(path: Path, *, delimiter: str, units: list[str],
                    timestamp_semantics: str, source_revision: str) -> dict:
    """Read one CSV record, never serialize data rows or the source path.

    Units and clock semantics must come from evidence supplied by the operator;
    they cannot safely be inferred from a header or sample values.
    """
    if len(delimiter) != 1 or delimiter in "\r\n\0":
        raise ValueError("a single explicit delimiter is required")
    if not timestamp_semantics.strip() or not source_revision.strip():
        raise ValueError("clock evidence and source revision are required")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        header = next(csv.reader(stream, delimiter=delimiter, strict=True), [])
    if not header or any(not column.strip() for column in header) or len(set(header)) != len(header):
        raise ValueError("header must contain unique nonblank column names")
    if len(units) != len(header) or any(not isinstance(unit, str) or not unit.strip() for unit in units):
        raise ValueError("one explicit unit (or dimensionless marker) per column is required")
    descriptor = {"ordered_columns": header, "units": units,
                  "delimiter": delimiter, "timestamp_semantics": timestamp_semantics}
    canonical = json.dumps(descriptor, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return {"status": "CANDIDATE_REQUIRES_S0_RECONCILIATION", "source_revision": source_revision,
            "descriptor": descriptor, "schema_fingerprint": hashlib.sha256(canonical.encode()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--delimiter", required=True)
    parser.add_argument("--units-json", required=True, help="JSON array in header order")
    parser.add_argument("--timestamp-semantics", required=True)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    units = json.loads(args.units_json)
    if not isinstance(units, list):
        parser.error("--units-json must be an array")
    result = describe_header(args.csv_path, delimiter=args.delimiter, units=units,
                             timestamp_semantics=args.timestamp_semantics, source_revision=args.source_revision)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
