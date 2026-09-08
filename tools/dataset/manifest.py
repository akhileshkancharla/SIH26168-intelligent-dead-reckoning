#!/usr/bin/env python3
"""WP-10.1 (Issue #79): DatasetManifest (I-20) load/build/validate tooling.

This module owns exactly the "immutable source manifest" half of WP-10.1's
scope: constructing, loading and structurally validating a DatasetManifest
document against contracts/schemas/dataset_manifest_v2.schema.json, and
verifying that the hashes it records still match the files it describes.

It deliberately does NOT implement:
  - the six-schema IO-VNBD validation allowlist (WP-10.2 / Issue #80)
  - duplicate/parent-session grouping (WP-10.3 / Issue #81)
  - leakage-safe split construction (WP-10.4 / Issue #82)
  - runtime-feature/forbidden-label firewall (WP-10.5 / Issue #83)
  - leakage canary tests (WP-10.6 / Issue #84)

Per docs/PRIVATE_ARTIFACT_POLICY.md, this module never reads or stores raw
private bytes -- only SHA-256 digests and structural metadata may enter a
DatasetManifest document, and a DatasetManifest document is safe to commit
to Git (it is hash-only; see docs/architecture/SIH26168_High_Level_Architecture_Revision3.md
component C-15 and contracts/INTERFACE_SCHEMA_PLAN.md#I-20).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "contracts/schemas/dataset_manifest_v2.schema.json"

# A read chunk size for streaming SHA-256 computation, so a large private
# archive is never fully loaded into memory just to be hashed.
_HASH_CHUNK_BYTES = 1024 * 1024


class DatasetManifestError(Exception):
    """Raised for any DatasetManifest structural or integrity failure.

    Per the architecture's C-15 failure mode ("Quarantine unknown
    schema/hash/unit; stop experiment"), callers must treat this as a hard
    stop -- never catch-and-continue with an unverified manifest.
    """


def load_schema() -> Dict[str, Any]:
    """Load and return the I-20 DatasetManifest JSON Schema document."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def sha256_of_file(path: Path) -> str:
    """Return the lowercase hex SHA-256 digest of a file's bytes.

    Streams the file in fixed-size chunks so this is safe to call on large
    private archives without loading them fully into memory.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest(document: Dict[str, Any]) -> None:
    """Validate a DatasetManifest document against the I-20 schema.

    Raises DatasetManifestError (wrapping the underlying
    jsonschema.ValidationError) on any structural violation -- including
    an unrecognized top-level field, since the schema is Tier A
    (additionalProperties: false).
    """
    schema = load_schema()
    try:
        jsonschema.Draft202012Validator(schema).validate(document)
    except jsonschema.ValidationError as exc:
        raise DatasetManifestError(f"DatasetManifest failed schema validation: {exc.message}") from exc


def load_manifest(path: Path) -> Dict[str, Any]:
    """Load a DatasetManifest document from disk and validate it.

    Raises DatasetManifestError if the file is not valid JSON or fails
    schema validation. A manifest is never trusted merely because it
    parses -- see verify_file_hashes for confirming its hash claims still
    hold against the files it describes.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetManifestError(f"DatasetManifest is not valid JSON: {path}: {exc}") from exc
    validate_manifest(document)
    return document


def new_manifest(
    dataset_id: str,
    source_revision: str,
    *,
    rights_status: str,
    privacy: str,
    redistribution: str,
) -> Dict[str, Any]:
    """Build an empty-but-valid-shaped DatasetManifest skeleton.

    Callers (or later WP-10.2/10.3/10.4 tooling) populate archive_hashes,
    file_hashes, schemas, units_status, group_ids, file_group_ids, splits
    and exclusions before this document can pass validate_manifest -- an
    empty skeleton is intentionally not itself schema-valid
    (archive_hashes/file_hashes/schemas all require at least one entry),
    so a caller cannot mistake scaffolding for a real manifest.
    """
    return {
        "schema_version": 2,
        "dataset_id": dataset_id,
        "source_revision": source_revision,
        "archive_hashes": {},
        "file_hashes": {},
        "schemas": [],
        "units_status": {},
        "group_ids": [],
        "file_group_ids": {},
        "splits": {"train": [], "validation": [], "test": []},
        "exclusions": [],
        "rights_status": rights_status,
        "privacy": privacy,
        "redistribution": redistribution,
    }


def verify_file_hashes(document: Dict[str, Any], files_by_identifier: Dict[str, Path]) -> None:
    """Recompute and compare file_hashes for every identifier supplied.

    `files_by_identifier` maps each file_hashes key present in the
    manifest to its actual on-disk Path (inside the private workspace --
    see workspace.py). Raises DatasetManifestError naming every
    identifier whose recomputed digest does not match the manifest's
    recorded digest, that the manifest references but no path was
    supplied for, or that was supplied but is not present in the
    manifest's own file_hashes at all -- the supplied identifier set must
    match the recorded set exactly, in both directions, or verification
    itself cannot be trusted to have covered the right files. `document`
    is validated against the I-20 schema first (see validate_manifest):
    an invalid document -- including one with an empty or missing
    file_hashes -- must never be able to "pass" verification by having
    nothing left to check. This is the "immutable source manifest"
    guarantee: once recorded, a file's hash must never silently change
    underneath the manifest.
    """
    validate_manifest(document)

    mismatches = []
    recorded = document.get("file_hashes", {})
    recorded_identifiers = set(recorded)
    supplied_identifiers = set(files_by_identifier)

    unexpected = sorted(supplied_identifiers - recorded_identifiers)
    for identifier in unexpected:
        mismatches.append(f"{identifier}: supplied for verification but not present in the manifest's file_hashes")

    for identifier, expected_digest in recorded.items():
        path = files_by_identifier.get(identifier)
        if path is None:
            mismatches.append(f"{identifier}: no on-disk file supplied for verification")
            continue
        if not path.is_file():
            mismatches.append(f"{identifier}: recorded file is missing on disk: {path}")
            continue
        actual_digest = sha256_of_file(path)
        if actual_digest != expected_digest:
            mismatches.append(f"{identifier}: hash mismatch (manifest={expected_digest}, actual={actual_digest})")
    if mismatches:
        raise DatasetManifestError(
            "DatasetManifest file_hashes verification failed; quarantine and stop the experiment:\n"
            + "\n".join(f"  - {m}" for m in mismatches)
        )


def iter_group_ids_used_in_splits(document: Dict[str, Any]) -> Iterable[str]:
    """Yield every group_id referenced anywhere in `splits`.

    A thin structural helper for WP-10.4's leakage-safe split checks; this
    module does not itself decide whether the resulting assignment is
    leakage-safe (that is WP-10.4's scope), only exposes the raw union.
    """
    for split_name in ("train", "validation", "test"):
        yield from document.get("splits", {}).get(split_name, [])
