#!/usr/bin/env python3
"""Verify the private external S6B1 delivery without extracting it.

The verifier reads the immutable archive in its external workspace and emits
only bounded hash/count evidence. It never copies PBF, SQLite, route, wheel or
archive bytes into the repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any, BinaryIO
from zipfile import BadZipFile, ZipFile, ZipInfo

import jsonschema


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENCE = Path(__file__).with_name("s6b1_reference_v1.json")
DEFAULT_SCHEMA = ROOT / "contracts" / "schemas" / "map_graph_manifest_v1.schema.json"
BUFFER_SIZE = 1024 * 1024
MAX_JSON_MEMBER_BYTES = 1024 * 1024


class VerificationError(RuntimeError):
    """Raised when immutable artifact evidence does not match the reference."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read JSON {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"JSON root must be an object: {path.name}")
    return value


def sha256_stream(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    while chunk := stream.read(BUFFER_SIZE):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            return sha256_stream(stream)
    except OSError as exc:
        raise VerificationError(f"cannot hash {path.name}: {exc}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def verify_delivery_file(directory: Path, record: dict[str, Any]) -> Path:
    path = directory / record["filename"]
    require(path.is_file() and not path.is_symlink(), f"missing regular delivery file: {path.name}")
    require(path.stat().st_size == record["size_bytes"], f"delivery size mismatch: {path.name}")
    require(sha256_file(path) == record["sha256"], f"delivery SHA-256 mismatch: {path.name}")
    return path


def normalized_member_name(info: ZipInfo) -> str:
    name = info.filename
    require("\\" not in name, f"ZIP member uses a backslash: {name}")
    path = PurePosixPath(name)
    require(not path.is_absolute(), f"ZIP member is absolute: {name}")
    require(all(part not in ("", ".", "..") for part in path.parts),
            f"ZIP member has unsafe traversal: {name}")
    require(not info.is_dir(), f"ZIP must not contain directory entries: {name}")
    require(not info.flag_bits & 0x1, f"ZIP member is encrypted: {name}")
    return path.as_posix()


def member_map(archive: ZipFile) -> dict[str, ZipInfo]:
    members: dict[str, ZipInfo] = {}
    for info in archive.infolist():
        name = normalized_member_name(info)
        require(name not in members, f"duplicate ZIP member: {name}")
        members[name] = info
    return members


def read_json_member(archive: ZipFile, info: ZipInfo) -> dict[str, Any]:
    require(info.file_size <= MAX_JSON_MEMBER_BYTES, f"JSON member exceeds size limit: {info.filename}")
    try:
        with archive.open(info, "r") as stream:
            data = stream.read(MAX_JSON_MEMBER_BYTES + 1)
        require(len(data) <= MAX_JSON_MEMBER_BYTES, f"JSON member exceeds size limit: {info.filename}")
        value = json.loads(data.decode("utf-8"))
    except (BadZipFile, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read JSON member {info.filename}: {exc}") from exc
    require(isinstance(value, dict), f"JSON member root must be an object: {info.filename}")
    return value


def find_manifest_entry(manifest_entries: dict[str, dict[str, Any]], path: str) -> dict[str, Any]:
    try:
        return manifest_entries[path]
    except KeyError as exc:
        raise VerificationError(f"artifact manifest is missing required member: {path}") from exc


def verify_recorded_results(
    archive: ZipFile,
    members: dict[str, ZipInfo],
    root: str,
    reference: dict[str, Any],
) -> None:
    def document(relative: str) -> dict[str, Any]:
        name = f"{root}/{relative}"
        require(name in members, f"archive is missing required result: {relative}")
        return read_json_member(archive, members[name])

    source = document("source/source_manifest.json")
    graph = document("results/graph_validation.json")
    tests = document("results/test_results.json")
    deterministic = document("results/deterministic_build_results.json")
    source_validation = document("results/source_validation.json")

    require(source.get("pbf_sha256") == reference["source_pbf_sha256"],
            "source manifest PBF hash mismatch")
    require(source.get("pbf_public_redistribution_authorized") is False,
            "source manifest must prohibit public PBF redistribution")
    require("OpenStreetMap" in source.get("osm_attribution", ""),
            "source manifest is missing OpenStreetMap attribution")
    source_files = source.get("files")
    require(isinstance(source_files, list), "source manifest files must be an array")
    region_records = [item for item in source_files
                      if isinstance(item, dict) and item.get("path") == "source/region.geojson"]
    require(len(region_records) == 1
            and region_records[0].get("sha256") == reference["region_sha256"],
            "source manifest region hash mismatch")

    graph_record = graph.get("graph")
    verification = reference["verification"]
    require(isinstance(graph_record, dict), "graph validation graph record must be an object")
    require(graph.get("status") == "passed", "recorded graph validation did not pass")
    require(graph_record.get("sqlite_sha256") == reference["graph_sha256"],
            "recorded SQLite hash mismatch")
    require(graph.get("logical_content_sha256") == reference["graph_logical_sha256"],
            "recorded logical graph hash mismatch")
    for field, expected in (
        ("node_count", verification["node_count"]),
        ("edge_count", verification["edge_count"]),
        ("way_count", verification["way_count"]),
    ):
        require(graph_record.get(field) == expected, f"recorded graph {field} mismatch")

    routes = graph.get("route_candidates")
    require(isinstance(routes, dict) and isinstance(routes.get("routes"), list),
            "recorded route candidates are malformed")
    require(routes.get("routes"), "recorded route candidate list is empty")
    for route in routes["routes"]:
        require(isinstance(route, dict), "recorded route candidate must be an object")
        require(route.get("status") == reference["route_status"],
                "a route candidate is not FIELD_VALIDATION_PENDING")
        require(route.get("final_selected") in (False, "false"),
                "artifact must not claim a final selected route")

    expected_counts = {
        "passed": verification["tests_passed"],
        "failed": verification["tests_failed"],
        "skipped": verification["tests_skipped"],
    }
    require(tests.get("counts") == expected_counts, "recorded test counts mismatch")
    test_cases = tests.get("tests")
    require(isinstance(test_cases, list) and len(test_cases) == expected_counts["passed"],
            "recorded test case count mismatch")
    require(all(isinstance(case, dict) and case.get("status") == "passed" for case in test_cases),
            "recorded artifact suite contains a non-passing test")

    require(deterministic.get("byte_identical") is verification["byte_identical_rebuild"],
            "recorded byte determinism mismatch")
    require(deterministic.get("logical_identical") is verification["logical_identical_rebuild"],
            "recorded logical determinism mismatch")
    require(deterministic.get("first_sqlite_sha256") == reference["graph_sha256"]
            and deterministic.get("second_sqlite_sha256") == reference["graph_sha256"],
            "deterministic rebuild SQLite hashes mismatch")
    require(deterministic.get("first_logical_sha256") == reference["graph_logical_sha256"]
            and deterministic.get("second_logical_sha256") == reference["graph_logical_sha256"],
            "deterministic rebuild logical hashes mismatch")

    bounds = source_validation.get("pbf_header", {}).get("bounds")
    require(bounds == reference["bounds"], "PBF header bounds mismatch")
    require(source_validation.get("region_bounds") == reference["bounds"],
            "authoritative region bounds mismatch")
    require(source_validation.get("header_bounds_exactly_match_region") is True,
            "PBF header does not exactly match the authoritative region")


def verify_artifact(
    artifact_dir: Path,
    reference_path: Path = DEFAULT_REFERENCE,
    schema_path: Path = DEFAULT_SCHEMA,
) -> dict[str, Any]:
    reference = load_json(reference_path)
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(reference)
    except jsonschema.SchemaError as exc:
        raise VerificationError(f"invalid I-21 schema: {exc.message}") from exc
    except jsonschema.ValidationError as exc:
        raise VerificationError(f"reference violates I-21 schema: {exc.message}") from exc

    artifact_dir = artifact_dir.resolve()
    require(artifact_dir.is_dir(), "artifact directory does not exist")
    delivery = reference.get("delivery")
    require(isinstance(delivery, dict), "reference is missing delivery evidence")
    expected_delivery_names = {
        delivery["manifest"]["filename"],
        delivery["archive"]["filename"],
    }
    try:
        actual_delivery_names = {path.name for path in artifact_dir.iterdir()}
    except OSError as exc:
        raise VerificationError(f"cannot enumerate artifact directory: {exc}") from exc
    require(actual_delivery_names == expected_delivery_names,
            "external delivery directory must contain exactly the manifest and ZIP")
    manifest_path = verify_delivery_file(artifact_dir, delivery["manifest"])
    archive_path = verify_delivery_file(artifact_dir, delivery["archive"])
    manifest = load_json(manifest_path)

    for field, expected in (
        ("schema_version", reference["schema_version"]),
        ("artifact", delivery["artifact"]),
        ("build_version", reference["toolchain"]["build_version"]),
        ("map_version", reference["map_version"]),
        ("gate_decision", reference["gate_decision"]),
        ("source_pbf_sha256", reference["source_pbf_sha256"]),
        ("region_sha256", reference["region_sha256"]),
    ):
        require(manifest.get(field) == expected, f"artifact manifest {field} mismatch")

    expected_counts = {
        "passed": reference["verification"]["tests_passed"],
        "failed": reference["verification"]["tests_failed"],
        "skipped": reference["verification"]["tests_skipped"],
    }
    require(manifest.get("test_counts") == expected_counts,
            "artifact manifest test counts mismatch")
    raw_entries = manifest.get("files")
    require(isinstance(raw_entries, list) and raw_entries,
            "artifact manifest files must be a non-empty array")
    manifest_entries: dict[str, dict[str, Any]] = {}
    for entry in raw_entries:
        require(isinstance(entry, dict), "artifact manifest file entry must be an object")
        path = entry.get("path")
        require(isinstance(path, str) and path, "artifact manifest file path is invalid")
        require(path not in manifest_entries, f"duplicate artifact manifest path: {path}")
        require(set(entry) == {"path", "size_bytes", "sha256"},
                f"artifact manifest file entry has unexpected fields: {path}")
        require(isinstance(entry["size_bytes"], int) and entry["size_bytes"] >= 0,
                f"artifact manifest size is invalid: {path}")
        require(isinstance(entry["sha256"], str) and len(entry["sha256"]) == 64,
                f"artifact manifest hash is invalid: {path}")
        manifest_entries[path] = entry

    required_hashes = {
        "source/mgit_frozen.osm.pbf": reference["source_pbf_sha256"],
        "source/region.geojson": reference["region_sha256"],
        "graph/mgit_graph.sqlite": reference["graph_sha256"],
        "graph/graph_schema.sql": reference["verification"]["graph_schema_sha256"],
        "requirements-lock.txt": reference["toolchain"]["requirements_lock_sha256"],
    }
    for path, expected_hash in required_hashes.items():
        require(find_manifest_entry(manifest_entries, path).get("sha256") == expected_hash,
                f"artifact manifest required hash mismatch: {path}")

    try:
        with ZipFile(archive_path, "r") as archive:
            members = member_map(archive)
            root = delivery["archive_root"]
            expected_names = {f"{root}/{path}" for path in manifest_entries}
            nested_manifest_name = f"{root}/{delivery['manifest']['filename']}"
            expected_names.add(nested_manifest_name)
            require(set(members) == expected_names,
                    "ZIP member set does not exactly match the artifact manifest")

            outer_manifest_bytes = manifest_path.read_bytes()
            with archive.open(members[nested_manifest_name], "r") as stream:
                nested_manifest_bytes = stream.read(MAX_JSON_MEMBER_BYTES + 1)
            require(len(nested_manifest_bytes) <= MAX_JSON_MEMBER_BYTES,
                    "nested artifact manifest exceeds size limit")
            require(nested_manifest_bytes == outer_manifest_bytes,
                    "nested artifact manifest differs from delivery manifest")

            for relative, entry in manifest_entries.items():
                info = members[f"{root}/{relative}"]
                require(info.file_size == entry["size_bytes"],
                        f"ZIP member size mismatch: {relative}")
                with archive.open(info, "r") as stream:
                    digest = sha256_stream(stream)
                require(digest == entry["sha256"],
                        f"ZIP member SHA-256 mismatch: {relative}")

            verify_recorded_results(archive, members, root, reference)
    except (BadZipFile, OSError) as exc:
        raise VerificationError(f"cannot inspect artifact ZIP: {exc}") from exc

    return {
        "status": "passed",
        "map_version": reference["map_version"],
        "gate_decision": reference["gate_decision"],
        "manifest_entries_verified": len(manifest_entries),
        "graph_sha256": reference["graph_sha256"],
        "graph_logical_sha256": reference["graph_logical_sha256"],
        "recorded_tests": expected_counts,
        "route_status": reference["route_status"],
        "limitations": reference.get("limitations", []),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", required=True, type=Path,
                        help="External directory containing the manifest and ZIP")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--json", action="store_true", help="Emit the bounded result as JSON")
    args = parser.parse_args(argv)
    try:
        result = verify_artifact(args.artifact_dir, args.reference, args.schema)
    except VerificationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "PASS: S6B1 artifact identity and recorded evidence verified; "
            f"map_version={result['map_version']} "
            f"members={result['manifest_entries_verified']} "
            f"route_status={result['route_status']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
