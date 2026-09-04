#!/usr/bin/env python3
"""Validate the committed sanitized Graphify snapshot without dependencies."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = REPO_ROOT / "docs" / "architecture" / "dependency-graph"
REQUIRED_FILES = {
    "GRAPH_REPORT.md",
    "README.md",
    "SHA256SUMS.txt",
    "graph.json",
    "metadata.json",
}
HASHED_FILES = REQUIRED_FILES - {"SHA256SUMS.txt"}
REQUIRED_METADATA = {
    "architecture_authority_statement",
    "ci_mode",
    "community_count",
    "edge_count",
    "extracted_edge_count",
    "generator_script_version",
    "graph_bootstrap_commands",
    "graph_html_committed",
    "graph_post_update_command",
    "graph_update_command",
    "graphify_configuration_sha256",
    "graphify_package",
    "graphify_product",
    "graphify_version",
    "inferred_edge_count",
    "known_graphify_limitations",
    "node_count",
    "raw_graph_built_at_commit",
    "removed_volatile_fields",
    "sanitizer_script_sha256",
    "schema_version",
    "snapshot_classification",
    "source_branch",
    "source_includes_working_tree",
    "source_parent_commit",
    "source_repository",
    "verification_script_sha256",
}
URL_RE = re.compile(r"https?://[^\s<>()\"']+")
WINDOWS_ABSOLUTE_RE = re.compile(r"(?i)(?<![a-z0-9_])[a-z]:[\\/]")
UNIX_ABSOLUTE_RE = re.compile(
    r"(?<![:a-zA-Z0-9_.-])/(?:[a-zA-Z0-9._~-]+/)+[a-zA-Z0-9._~-]+"
)
HOME_SHORTHAND_RE = re.compile(r"(?<![a-zA-Z0-9_])~[\\/]")
SECRET_PATTERNS = (
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("GitHub fine-grained token", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "private key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    ("bearer token", re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{20,}")),
)
PATH_KEYS = {"file", "file_path", "path", "root", "source_file", "source_path"}


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configuration_sha256(repo_root: Path) -> str:
    digest = hashlib.sha256()
    for relative in (Path(".graphifyignore"), Path("tools/graphify/graphify_config.json")):
        path = repo_root / relative
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def stable_item_key(item: Any, preferred: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(item, dict):
        return (json.dumps(item, ensure_ascii=False, sort_keys=True),)
    prefix = tuple(str(item.get(field, "")) for field in preferred)
    return (*prefix, json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def scan_text(value: str, label: str) -> list[str]:
    errors: list[str] = []
    candidate = URL_RE.sub("", value)
    if WINDOWS_ABSOLUTE_RE.search(candidate):
        errors.append(f"Windows absolute path remains in {label}")
    if UNIX_ABSOLUTE_RE.search(candidate) or HOME_SHORTHAND_RE.search(candidate):
        errors.append(f"Unix/home absolute path remains in {label}")
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(value):
            errors.append(f"{name} material remains in {label}")
    return errors


def iter_path_fields(value: Any, location: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            if isinstance(child, str) and (
                key.casefold() in PATH_KEYS or key.casefold().endswith("_path")
            ):
                yield child_location, child
            yield from iter_path_fields(child, child_location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_path_fields(child, f"{location}[{index}]")


def validate_repository_path(value: str, location: str) -> list[str]:
    if not value:
        return []
    errors: list[str] = []
    if "\\" in value:
        errors.append(f"non-POSIX repository path at {location}: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or WINDOWS_ABSOLUTE_RE.search(value):
        errors.append(f"non-relative or escaping repository path at {location}: {value!r}")
    return errors


def edge_key(edge: dict[str, Any]) -> tuple[str, ...]:
    if "id" in edge:
        return ("id", str(edge["id"]))
    return (
        "tuple",
        str(edge.get("source", "")),
        str(edge.get("target", "")),
        str(edge.get("relation", "")),
        str(edge.get("context", "")),
        str(edge.get("source_file", "")),
        str(edge.get("source_location", "")),
    )


def validate_graph_document(graph: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(graph, dict):
        return ["graph.json root must be an object"]
    nodes = graph.get("nodes")
    edge_field = "links" if "links" in graph else "edges" if "edges" in graph else None
    edges = graph.get(edge_field) if edge_field else None
    if not isinstance(nodes, list):
        errors.append("graph.json must contain a nodes array")
        nodes = []
    if not isinstance(edges, list):
        errors.append("graph.json must contain a links or edges array")
        edges = []

    node_ids: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]:
            errors.append(f"node {index} has no stable string id")
            continue
        if node["id"] in node_ids:
            errors.append(f"duplicate node id: {node['id']}")
        node_ids.add(node["id"])

    edge_ids: set[tuple[str, ...]] = set()
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"edge {index} is not an object")
            continue
        stable = edge_key(edge)
        if stable in edge_ids:
            errors.append(f"duplicate edge identity: {stable}")
        edge_ids.add(stable)
        for endpoint in ("source", "target"):
            value = edge.get(endpoint)
            if not isinstance(value, str) or value not in node_ids:
                errors.append(f"edge {index} has invalid {endpoint} endpoint: {value!r}")

    expected_nodes = sorted(nodes, key=lambda item: stable_item_key(item, ("id", "label", "source_file")))
    if nodes != expected_nodes:
        errors.append("graph nodes are not in deterministic order")
    expected_edges = sorted(
        edges,
        key=lambda item: stable_item_key(
            item,
            ("source", "target", "relation", "context", "source_file", "source_location"),
        ),
    )
    if edges != expected_edges:
        errors.append("graph edges are not in deterministic order")

    for location, value in iter_path_fields(graph):
        errors.extend(validate_repository_path(value, location))
        normalized = value.replace("\\", "/")
        if normalized.startswith("graphify-out/") or normalized.startswith(
            "docs/architecture/dependency-graph/"
        ):
            errors.append(f"recursive Graphify output indexed at {location}: {value!r}")
    return errors


def parse_checksums(path: Path) -> tuple[dict[str, str], list[str]]:
    hashes: dict[str, str] = {}
    errors: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    names_in_order: list[str] = []
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if not match:
            errors.append(f"invalid checksum line: {line!r}")
            continue
        digest, name = match.groups()
        if name in hashes:
            errors.append(f"duplicate checksum entry: {name}")
        hashes[name] = digest
        names_in_order.append(name)
    if names_in_order != sorted(names_in_order):
        errors.append("SHA256SUMS.txt entries are not sorted by filename")
    return hashes, errors


def tracked_graphify_errors(repo_root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_root,
            check=True,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return [f"cannot inspect tracked files: {exc}"]
    tracked = [line.strip().replace("\\", "/") for line in result.stdout.splitlines()]
    errors = [f"raw Graphify output is tracked: {path}" for path in tracked if path.startswith("graphify-out/")]
    errors.extend(
        f"raw Graphify root marker is tracked: {path}"
        for path in tracked
        if PurePosixPath(path).name == ".graphify_root"
    )
    return errors


def validate_snapshot(snapshot_dir: Path, repo_root: Path) -> list[str]:
    errors: list[str] = []
    actual_files = {path.name for path in snapshot_dir.iterdir() if path.is_file()} if snapshot_dir.is_dir() else set()
    missing = REQUIRED_FILES - actual_files
    unexpected = actual_files - REQUIRED_FILES
    errors.extend(f"missing snapshot file: {name}" for name in sorted(missing))
    errors.extend(f"unexpected snapshot file: {name}" for name in sorted(unexpected))
    if missing:
        return errors

    decoded: dict[str, str] = {}
    for name in sorted(REQUIRED_FILES):
        path = snapshot_dir / name
        try:
            raw = path.read_bytes()
            decoded[name] = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"{name} is not readable UTF-8: {exc}")
            continue
        if b"\r" in raw:
            errors.append(f"{name} does not use normalized LF line endings")
        errors.extend(scan_text(decoded[name], name))

    try:
        graph = json.loads(decoded.get("graph.json", ""))
    except json.JSONDecodeError as exc:
        errors.append(f"graph.json does not parse: {exc}")
        graph = {}
    try:
        metadata = json.loads(decoded.get("metadata.json", ""))
    except json.JSONDecodeError as exc:
        errors.append(f"metadata.json does not parse: {exc}")
        metadata = {}

    if graph:
        errors.extend(validate_graph_document(graph))
        if (snapshot_dir / "graph.json").read_bytes() != canonical_json_bytes(graph):
            errors.append("graph.json is not canonical deterministic JSON")
    if metadata:
        if (snapshot_dir / "metadata.json").read_bytes() != canonical_json_bytes(metadata):
            errors.append("metadata.json is not canonical deterministic JSON")
        missing_metadata = REQUIRED_METADATA - set(metadata)
        errors.extend(f"metadata field missing: {name}" for name in sorted(missing_metadata))
        if metadata.get("schema_version") != 1:
            errors.append("metadata schema_version must be 1")
        if metadata.get("snapshot_classification") != "generated-and-sanitized":
            errors.append("metadata snapshot classification is invalid")
        if metadata.get("ci_mode") != "snapshot-validation-only":
            errors.append("metadata CI mode is not snapshot-validation-only")
        version = metadata.get("graphify_version")
        if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
            errors.append("metadata Graphify version is missing or invalid")
        config = json.loads(
            (repo_root / "tools" / "graphify" / "graphify_config.json").read_text(
                encoding="utf-8"
            )
        )
        if version != config.get("graphify_version"):
            errors.append("metadata Graphify version does not match configuration")
        if metadata.get("source_repository") != config.get("source_repository"):
            errors.append("metadata source repository does not match configuration")
        if metadata.get("ci_mode") != config.get("ci_mode"):
            errors.append("metadata CI mode does not match configuration")
        if metadata.get("graph_html_committed") is not False:
            errors.append("metadata must record graph.html as uncommitted")
        command_fields = {
            "graph_bootstrap_commands": "bootstrap_commands",
            "graph_post_update_command": "post_update_command",
            "graph_update_command": "update_command",
        }
        for metadata_field, config_field in command_fields.items():
            if metadata.get(metadata_field) != config.get(config_field):
                errors.append(f"metadata {metadata_field} does not match configuration")
        if not isinstance(metadata.get("source_includes_working_tree"), bool):
            errors.append("metadata source_includes_working_tree must be boolean")
        if not isinstance(metadata.get("known_graphify_limitations"), list) or not metadata.get(
            "known_graphify_limitations"
        ):
            errors.append("metadata known Graphify limitations are incomplete")
        for commit_field in ("source_parent_commit", "raw_graph_built_at_commit"):
            commit = metadata.get(commit_field)
            if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
                errors.append(f"metadata {commit_field} is not an honest full commit SHA")
        if metadata.get("source_parent_commit") != metadata.get("raw_graph_built_at_commit"):
            errors.append("raw graph commit does not match the recorded source parent commit")
        if graph:
            graph_edge_list = graph.get("links", graph.get("edges", []))
            edge_count = len(graph_edge_list)
            communities = {
                node.get("community")
                for node in graph.get("nodes", [])
                if isinstance(node, dict) and node.get("community") is not None
            }
            expected_counts = {
                "node_count": len(graph.get("nodes", [])),
                "edge_count": edge_count,
                "community_count": len(communities),
                "extracted_edge_count": sum(
                    isinstance(edge, dict) and str(edge.get("confidence", "")).upper() == "EXTRACTED"
                    for edge in graph_edge_list
                ),
                "inferred_edge_count": sum(
                    isinstance(edge, dict) and str(edge.get("confidence", "")).upper() == "INFERRED"
                    for edge in graph_edge_list
                ),
            }
            for field, count in expected_counts.items():
                if metadata.get(field) != count:
                    errors.append(f"metadata {field} does not match graph")
        expected_config_hash = configuration_sha256(repo_root)
        if metadata.get("graphify_configuration_sha256") != expected_config_hash:
            errors.append("Graphify configuration hash does not match")
        script_hashes = {
            "sanitizer_script_sha256": repo_root / "tools" / "graphify" / "sanitize_graph.py",
            "verification_script_sha256": repo_root / "tools" / "graphify" / "verify_graph.py",
        }
        for field, path in script_hashes.items():
            if metadata.get(field) != sha256_file(path):
                errors.append(f"metadata {field} does not match")

    checksums, checksum_errors = parse_checksums(snapshot_dir / "SHA256SUMS.txt")
    errors.extend(checksum_errors)
    if set(checksums) != HASHED_FILES:
        errors.append("SHA256SUMS.txt file set does not match required artifacts")
    for name, expected in checksums.items():
        target = snapshot_dir / name
        if target.is_file() and sha256_file(target) != expected:
            errors.append(f"checksum mismatch: {name}")

    gitignore = repo_root / ".gitignore"
    if not gitignore.is_file() or "graphify-out/" not in gitignore.read_text(encoding="utf-8").splitlines():
        errors.append(".gitignore does not exclude raw graphify-out/")
    errors.extend(tracked_graphify_errors(repo_root))
    return errors


def main() -> int:
    errors = validate_snapshot(SNAPSHOT_DIR, REPO_ROOT)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors))
        return 1
    metadata = json.loads((SNAPSHOT_DIR / "metadata.json").read_text(encoding="utf-8"))
    print(
        "PASS: sanitized Graphify snapshot "
        f"({metadata['node_count']} nodes, {metadata['edge_count']} edges, "
        f"{metadata['community_count']} communities)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
