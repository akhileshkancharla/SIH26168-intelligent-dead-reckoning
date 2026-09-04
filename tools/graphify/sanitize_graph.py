#!/usr/bin/env python3
"""Create the deterministic, repository-safe Graphify snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

SCRIPT_VERSION = "1.0.0"
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "graphify-out"
OUTPUT_DIR = REPO_ROOT / "docs" / "architecture" / "dependency-graph"
CONFIG_PATH = REPO_ROOT / "tools" / "graphify" / "graphify_config.json"
VERIFY_PATH = REPO_ROOT / "tools" / "graphify" / "verify_graph.py"

URL_RE = re.compile(r"https?://[^\s<>()\"']+")
WINDOWS_ABSOLUTE_RE = re.compile(r"(?i)(?<![a-z0-9_])[a-z]:[\\/]")
UNIX_ABSOLUTE_RE = re.compile(
    r"(?<![:a-zA-Z0-9_.-])/(?:[a-zA-Z0-9._~-]+/)+[a-zA-Z0-9._~-]+"
)
HOME_SHORTHAND_RE = re.compile(r"(?<![a-zA-Z0-9_])~[\\/]")
SECRET_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{20,}"),
)
VOLATILE_KEYS = {
    "built_at",
    "created_at",
    "generated_at",
    "generation_time",
    "mtime",
    "seen",
    "updated_at",
}
PATH_KEYS = {
    "file",
    "file_path",
    "path",
    "root",
    "source_file",
    "source_path",
}


class GraphSanitizationError(ValueError):
    """Raised when raw output cannot be made portable without guessing."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GraphSanitizationError(f"cannot read JSON {path}: {exc}") from exc


def strip_urls(value: str) -> str:
    return URL_RE.sub("", value)


def secret_name(value: str) -> str | None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(value):
            return pattern.pattern
    return None


def contains_absolute_path(value: str) -> bool:
    candidate = strip_urls(value)
    return bool(
        WINDOWS_ABSOLUTE_RE.search(candidate)
        or UNIX_ABSOLUTE_RE.search(candidate)
        or HOME_SHORTHAND_RE.search(candidate)
    )


class PathPolicy:
    def __init__(self, repo_root: Path, aliases: Iterable[str] = ()) -> None:
        roots = {str(repo_root.resolve()), repo_root.resolve().as_posix(), *aliases}
        normalized = {root.strip().replace("\\", "/").rstrip("/") for root in roots if root}
        self.aliases = sorted(normalized, key=len, reverse=True)

    def _remove_repository_prefix(self, value: str) -> tuple[str, bool]:
        normalized = value.replace("\\", "/")
        lowered = normalized.casefold()
        for alias in self.aliases:
            alias_lower = alias.casefold()
            if lowered == alias_lower:
                return "", True
            if lowered.startswith(alias_lower + "/"):
                return normalized[len(alias) + 1 :], True
        return normalized, False

    def sanitize_path(self, value: str, location: str) -> str:
        if not value:
            return value
        normalized, _ = self._remove_repository_prefix(value)
        if contains_absolute_path(normalized) or normalized.startswith("/"):
            raise GraphSanitizationError(f"unresolved absolute path at {location}: {value!r}")
        path = PurePosixPath(normalized)
        if path.is_absolute() or ".." in path.parts:
            raise GraphSanitizationError(f"path escapes repository at {location}: {value!r}")
        return path.as_posix()

    def sanitize_text(self, value: str, location: str) -> str:
        normalized = value
        for alias in self.aliases:
            normalized = re.sub(re.escape(alias), ".", normalized, flags=re.IGNORECASE)
            native_alias = alias.replace("/", "\\")
            normalized = re.sub(
                re.escape(native_alias), ".", normalized, flags=re.IGNORECASE
            )
        if contains_absolute_path(normalized):
            raise GraphSanitizationError(f"unresolved absolute path at {location}: {value!r}")
        secret = secret_name(normalized)
        if secret:
            raise GraphSanitizationError(f"credential-like material at {location}: {secret}")
        return normalized


def sanitize_value(
    value: Any,
    policy: PathPolicy,
    location: str = "$",
    key: str | None = None,
    removed_volatile: list[str] | None = None,
) -> Any:
    removed_volatile = removed_volatile if removed_volatile is not None else []
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for child_key, child_value in value.items():
            child_location = f"{location}.{child_key}"
            if child_key.casefold() in VOLATILE_KEYS:
                removed_volatile.append(child_location)
                continue
            result[child_key] = sanitize_value(
                child_value, policy, child_location, child_key, removed_volatile
            )
        return result
    if isinstance(value, list):
        return [
            sanitize_value(item, policy, f"{location}[{index}]", key, removed_volatile)
            for index, item in enumerate(value)
        ]
    if isinstance(value, str):
        if key and (key.casefold() in PATH_KEYS or key.casefold().endswith("_path")):
            return policy.sanitize_path(value, location)
        return policy.sanitize_text(value, location)
    return value


def stable_item_key(item: Any, preferred: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(item, dict):
        return (json.dumps(item, ensure_ascii=False, sort_keys=True),)
    prefix = tuple(str(item.get(field, "")) for field in preferred)
    return (*prefix, json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def sanitize_graph_document(
    graph: dict[str, Any], policy: PathPolicy
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list):
        raise GraphSanitizationError("raw graph must contain a nodes array")
    edge_key = "links" if "links" in graph else "edges" if "edges" in graph else None
    if edge_key is None or not isinstance(graph.get(edge_key), list):
        raise GraphSanitizationError("raw graph must contain a links or edges array")

    removed: list[str] = []
    clean = sanitize_value(graph, policy, removed_volatile=removed)
    clean["nodes"] = sorted(
        clean["nodes"], key=lambda item: stable_item_key(item, ("id", "label", "source_file"))
    )
    clean[edge_key] = sorted(
        clean[edge_key],
        key=lambda item: stable_item_key(
            item,
            (
                "source",
                "target",
                "relation",
                "context",
                "source_file",
                "source_location",
            ),
        ),
    )
    if isinstance(clean.get("hyperedges"), list):
        clean["hyperedges"] = sorted(
            clean["hyperedges"], key=lambda item: stable_item_key(item, ("id",))
        )
    return clean, sorted(removed)


def graph_edges(graph: dict[str, Any]) -> list[dict[str, Any]]:
    edges = graph.get("links", graph.get("edges", []))
    return [edge for edge in edges if isinstance(edge, dict)]


def graph_statistics(graph: dict[str, Any]) -> dict[str, int]:
    edges = graph_edges(graph)
    communities = {
        node.get("community")
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and node.get("community") is not None
    }
    confidence = defaultdict(int)
    for edge in edges:
        confidence[str(edge.get("confidence", "UNKNOWN")).upper()] += 1
    return {
        "node_count": len(graph.get("nodes", [])),
        "edge_count": len(edges),
        "community_count": len(communities),
        "extracted_edge_count": confidence["EXTRACTED"],
        "inferred_edge_count": confidence["INFERRED"],
    }


def high_degree_nodes(graph: dict[str, Any], limit: int = 10) -> list[tuple[dict[str, Any], int]]:
    by_id = {
        node.get("id"): node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    degree = defaultdict(int)
    for edge in graph_edges(graph):
        degree[edge.get("source")] += 1
        degree[edge.get("target")] += 1
    ranked = sorted(
        ((node, degree[node_id]) for node_id, node in by_id.items()),
        key=lambda pair: (-pair[1], str(pair[0].get("id", ""))),
    )
    return ranked[:limit]


def weak_node_summary(graph: dict[str, Any], limit: int = 15) -> tuple[int, list[tuple[dict[str, Any], int]]]:
    degree = defaultdict(int)
    for edge in graph_edges(graph):
        degree[edge.get("source")] += 1
        degree[edge.get("target")] += 1
    candidates = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or not node.get("source_file"):
            continue
        if degree[node.get("id")] <= 1:
            candidates.append((node, degree[node.get("id")]))
    candidates.sort(key=lambda pair: (pair[1], str(pair[0].get("source_file")), str(pair[0].get("id"))))
    return len(candidates), candidates[:limit]


def import_cycles(graph: dict[str, Any]) -> list[list[str]]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in graph_edges(graph):
        if edge.get("relation") == "imports":
            adjacency[str(edge.get("source"))].append(str(edge.get("target")))
    state: dict[str, int] = {}
    stack: list[str] = []
    cycles: set[tuple[str, ...]] = set()

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for target in sorted(adjacency.get(node, [])):
            if state.get(target, 0) == 0:
                visit(target)
            elif state.get(target) == 1 and target in stack:
                cycle = stack[stack.index(target) :] + [target]
                cycles.add(tuple(cycle))
        stack.pop()
        state[node] = 2

    for node in sorted(adjacency):
        if state.get(node, 0) == 0:
            visit(node)
    return [list(cycle) for cycle in sorted(cycles)]


def repository_link(source_file: str) -> str:
    safe = PurePosixPath(source_file).as_posix()
    return f"../../../{safe}"


def render_report(
    graph: dict[str, Any], metadata: dict[str, Any], raw_report: str
) -> str:
    stats = graph_statistics(graph)
    source_files = {
        str(node.get("source_file"))
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and node.get("source_file")
    }
    module_rows = (
        ("Android app", "android/", "Launcher/UI scaffold; no sensor-to-position path"),
        ("Portable core", "core/", "C++ contract-version smoke scaffold"),
        ("Contracts", "contracts/", "Bootstrap replay schema and enum artifacts"),
        ("Repository automation", "tools/bootstrap/", "Repository and GitHub governance tooling"),
        ("Policy CI", "ci/", "Repository validation and generated-file checks"),
        ("Acquisition/JNI/ML/maps/analyzer", "__placeholder__", "README-only or disconnected placeholders"),
    )
    module_lines = []
    for name, prefix, interpretation in module_rows:
        count = 0 if prefix == "__placeholder__" else sum(path.startswith(prefix) for path in source_files)
        module_lines.append(f"| {name} | {count} | {interpretation} |")

    high_lines = []
    for node, degree in high_degree_nodes(graph):
        label = str(node.get("label", node.get("id", "unknown"))).replace("|", "\\|")
        source = str(node.get("source_file", ""))
        location = str(node.get("source_location", ""))
        if source:
            display = f"[{source}:{location}]({repository_link(source)})" if location else f"[{source}]({repository_link(source)})"
        else:
            display = "external/unlocated symbol"
        high_lines.append(f"| `{label}` | {degree} | {display} |")

    weak_count, weak_nodes = weak_node_summary(graph)
    weak_lines = []
    for node, degree in weak_nodes:
        label = str(node.get("label", node.get("id", "unknown"))).replace("|", "\\|")
        source = str(node.get("source_file", ""))
        weak_lines.append(
            f"| `{label}` | {degree} | [{source}]({repository_link(source)}) |"
        )

    raw_isolated_match = re.search(r"\*\*(\d+) isolated node", raw_report)
    raw_isolated = raw_isolated_match.group(1) if raw_isolated_match else "not reported"
    cycles = import_cycles(graph)
    cycle_text = "No import cycles were extracted." if not cycles else f"{len(cycles)} import cycle(s) were extracted."

    return "\n".join(
        [
            "# Sanitized Graphify Dependency Report",
            "",
            "## Snapshot metadata",
            "",
            f"- Snapshot classification: `{metadata['snapshot_classification']}`",
            f"- Source repository: `{metadata['source_repository']}`",
            f"- Source branch: `{metadata['source_branch']}`",
            f"- Source parent commit: `{metadata['source_parent_commit']}`",
            f"- Graphify version: `{metadata['graphify_version']}`",
            f"- Graphify mode: code-only static extraction; semantic document extraction disabled",
            f"- Counts: {stats['node_count']} nodes, {stats['edge_count']} edges, {stats['community_count']} communities",
            f"- Edge evidence: {stats['extracted_edge_count']} extracted, {stats['inferred_edge_count']} inferred",
            f"- CI mode: `{metadata['ci_mode']}`",
            "",
            "## VERIFIED FROM CODE",
            "",
            "The repository is presently a bootstrap and governance scaffold. No executable raw-sensor-to-position navigation path exists. Android startup renders a replay-labelled scaffold, and the native core exposes only a contract-version smoke function.",
            "",
            "Android, core, acquisition, JNI, training, map, and analyzer areas remain disconnected or placeholders. This statement describes current implementation, not the intended Revision 3 architecture.",
            "",
            "### Major modules",
            "",
            "| Module | Extracted source files | Current interpretation |",
            "| --- | ---: | --- |",
            *module_lines,
            "",
            "### Entry points",
            "",
            "- Android: [`MainActivity.onCreate`](../../../android/app/src/main/java/org/sih26168/app/MainActivity.kt)",
            "- C++ smoke test: [`core/navigation/tests/smoke_test.cpp`](../../../core/navigation/tests/smoke_test.cpp)",
            "- Repository verifier: [`ci/verify_repository.py`](../../../ci/verify_repository.py)",
            "- Bootstrap generator: [`tools/bootstrap/generate_repository.py`](../../../tools/bootstrap/generate_repository.py)",
            "",
            "### Actual dependency paths",
            "",
            "- Android launcher → `MainActivity.onCreate` → scaffold `TextView`.",
            "- C++ smoke test → `contract_version()` → fixed bootstrap version comparison.",
            "- Synthetic replay fixture → bootstrap smoke/policy validation.",
            "- There is no extracted IMU/GNSS ingestion → preprocessing → state-estimation → position-output path.",
            "",
            "## VERIFIED FROM GRAPH",
            "",
            "Current high-degree nodes are primarily repository administration tooling, not navigation runtime modules.",
            "",
            "### High-degree nodes",
            "",
            "| Node | Degree | Source |",
            "| --- | ---: | --- |",
            *high_lines,
            "",
            "### Weakly connected or orphan candidates",
            "",
            f"The raw Graphify report identified {raw_isolated} isolated symbol nodes. This sanitizer independently found {weak_count} repository-backed nodes with degree at most one; the bounded sample below is diagnostic, not deletion evidence.",
            "",
            "| Node | Degree | Source |",
            "| --- | ---: | --- |",
            *weak_lines,
            "",
            "### Cycles",
            "",
            cycle_text,
            "",
            "## INFERRED FROM ARCHITECTURE",
            "",
            "Revision 3 intends acquisition, preprocessing, a single-owner S2 C++ core, integrity/reacquisition, optional learned/map proposals, and separate scientific/display outputs. Those intended relationships must not be mistaken for implemented dependencies.",
            "",
            "## PROPOSED IMPROVEMENT",
            "",
            "Use the graph with source inspection to establish cross-module contracts as implementation proceeds. Do not add inferred runtime edges merely to make the graph resemble the intended design.",
            "",
            "## Known limitations",
            "",
            "- The snapshot uses local code-only AST extraction; documentation is interpreted separately.",
            "- The committed snapshot and bootstrap repository manifest are excluded from extraction to avoid generated-artifact recursion.",
            "- Static extraction cannot prove absence of JNI, Android callback, manifest, reflection, generated-code, dependency-injection, resource, or serialized-contract relationships.",
            "- Empty and README-only modules may not appear as graph communities.",
            "- Graphify cannot prove runtime reachability, correctness, performance, or scientific validity.",
            "- Node and edge counts are tool-version and extraction-mode dependent.",
            "- `graph.html` is not committed because the portable JSON/report snapshot is the reviewed artifact and HTML determinism has not been established.",
            "",
            "## Architecture interpretation warning",
            "",
            "Architecture Revision 3 is authoritative. Graphify is supporting static evidence only. C-07 remains the sole owner of S2 navigation state, operational biases, covariance, and evidence acceptance; ML and map components can submit bounded proposals but cannot overwrite the core.",
            "",
            "## Regeneration",
            "",
            "From the repository root, use `tools/graphify/update_graph.ps1` on Windows or `tools/graphify/update_graph.sh` on Unix with the configured Graphify version available. The wrapper updates raw local output, sanitizes the shared snapshot, verifies it, and refreshes checksums.",
            "",
        ]
    )


def render_readme(metadata: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Dependency Graph Snapshot",
            "",
            "This directory contains a generated and sanitized Graphify snapshot for repository knowledge transfer. Raw machine-specific output remains in the ignored `graphify-out/` directory.",
            "",
            "## Contents",
            "",
            "- `GRAPH_REPORT.md`: bounded human-readable architecture and dependency findings.",
            "- `graph.json`: canonical machine-readable graph with sorted nodes, edges, and object keys.",
            "- `metadata.json`: provenance, tool/configuration identity, counts, and limitations.",
            "- `SHA256SUMS.txt`: hashes for every committed snapshot artifact except the checksum file itself.",
            "",
            "`graph.html` is intentionally local-only because deterministic portable HTML has not been established.",
            "",
            "## Regeneration",
            "",
            f"Configured Graphify version: `{metadata['graphify_version']}`.",
            "",
            "- Windows: `tools/graphify/update_graph.ps1`",
            "- Unix: `tools/graphify/update_graph.sh`",
            "- Verify only: `python tools/graphify/verify_graph.py`",
            "",
            "The wrappers do not install Graphify. They fail unless the configured version can be identified exactly. See [`tools/graphify/README.md`](../../../tools/graphify/README.md) for environment details.",
            "",
            "## Maintenance policy",
            "",
            "Regenerate after meaningful architectural or multi-file changes affecting Android, the C++ core, contracts, analyzer, dataset, training, maps, root CMake, Gradle settings/build files, Android manifests, or native/JNI build configuration.",
            "",
            "Regeneration is generally unnecessary for spelling-only documentation changes, issue templates, non-architectural comments, or purely presentational README corrections.",
            "",
            "Before deletion or major refactoring, combine graph traversal with text search, Android manifest and Gradle inspection, native/JNI symbol inspection, configuration/schema inspection, build and test evidence, and runtime-entry-point reasoning.",
            "",
            "## Evidence boundary",
            "",
            "Graphify is supporting static evidence, not architectural authority or scientific evidence. Architecture Revision 3 controls interpretation.",
            "",
            f"CI mode: `{metadata['ci_mode']}`. CI validates the committed snapshot and deterministic tooling tests; it does not install or execute Graphify.",
            "",
        ]
    )


def configuration_sha256(repo_root: Path) -> str:
    digest = hashlib.sha256()
    for relative in (Path(".graphifyignore"), Path("tools/graphify/graphify_config.json")):
        path = repo_root / relative
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def git_value(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_root, check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def build_metadata(
    graph: dict[str, Any],
    repo_root: Path,
    graphify_version: str,
    source_branch: str,
    source_parent_commit: str,
    source_includes_working_tree: bool,
    removed_volatile: list[str],
) -> dict[str, Any]:
    config = load_json(repo_root / "tools" / "graphify" / "graphify_config.json")
    stats = graph_statistics(graph)
    return {
        "architecture_authority_statement": "Architecture Revision 3 is authoritative; this static graph is supporting evidence only.",
        "ci_mode": "snapshot-validation-only",
        "community_count": stats["community_count"],
        "extracted_edge_count": stats["extracted_edge_count"],
        "generator_script_version": SCRIPT_VERSION,
        "graph_bootstrap_commands": config["bootstrap_commands"],
        "graph_html_committed": False,
        "graph_post_update_command": config["post_update_command"],
        "graph_update_command": config["update_command"],
        "graphify_configuration_sha256": configuration_sha256(repo_root),
        "graphify_package": str(config["package_name"]),
        "graphify_product": str(config["product_name"]),
        "graphify_version": graphify_version,
        "inferred_edge_count": stats["inferred_edge_count"],
        "known_graphify_limitations": [
            "Code-only AST extraction does not semantically index architecture documents.",
            "The committed dependency snapshot and bootstrap repository manifest are excluded to prevent recursive generated-artifact graphs.",
            "Static extraction can miss JNI, Android callback/manifest, reflection, generated-code, resource, dependency-injection, and serialized-contract relationships.",
            "Static relationships do not prove runtime reachability, correctness, performance, or scientific validity.",
            "Community and centrality results can change with Graphify version and extraction mode.",
        ],
        "node_count": stats["node_count"],
        "edge_count": stats["edge_count"],
        "raw_graph_built_at_commit": graph.get("built_at_commit"),
        "removed_volatile_fields": removed_volatile,
        "sanitizer_script_sha256": sha256_file(repo_root / "tools" / "graphify" / "sanitize_graph.py"),
        "schema_version": 1,
        "snapshot_classification": "generated-and-sanitized",
        "source_branch": source_branch,
        "source_includes_working_tree": source_includes_working_tree,
        "source_parent_commit": source_parent_commit,
        "source_repository": str(config["source_repository"]),
        "verification_script_sha256": sha256_file(repo_root / "tools" / "graphify" / "verify_graph.py"),
    }


def write_checksums(output_dir: Path) -> None:
    names = ("GRAPH_REPORT.md", "README.md", "graph.json", "metadata.json")
    lines = [f"{sha256_file(output_dir / name)}  {name}" for name in sorted(names)]
    (output_dir / "SHA256SUMS.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )


def generate_snapshot(
    repo_root: Path,
    raw_dir: Path,
    output_dir: Path,
    graphify_version: str,
    source_branch: str,
    source_parent_commit: str,
    source_includes_working_tree: bool,
) -> dict[str, Any]:
    raw_graph_path = raw_dir / "graph.json"
    raw_report_path = raw_dir / "GRAPH_REPORT.md"
    if not raw_graph_path.is_file() or not raw_report_path.is_file():
        raise GraphSanitizationError("raw Graphify graph.json and GRAPH_REPORT.md are required")

    aliases: list[str] = []
    raw_root_marker = raw_dir / ".graphify_root"
    if raw_root_marker.is_file():
        aliases.append(raw_root_marker.read_text(encoding="utf-8").strip())
    policy = PathPolicy(repo_root, aliases)
    graph, removed = sanitize_graph_document(load_json(raw_graph_path), policy)
    metadata = build_metadata(
        graph,
        repo_root,
        graphify_version,
        source_branch,
        source_parent_commit,
        source_includes_working_tree,
        removed,
    )
    raw_report = raw_report_path.read_text(encoding="utf-8")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "graph.json").write_bytes(canonical_json_bytes(graph))
    (output_dir / "metadata.json").write_bytes(canonical_json_bytes(metadata))
    (output_dir / "GRAPH_REPORT.md").write_text(
        render_report(graph, metadata, raw_report), encoding="utf-8", newline="\n"
    )
    (output_dir / "README.md").write_text(
        render_readme(metadata), encoding="utf-8", newline="\n"
    )
    write_checksums(output_dir)
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--graphify-version", required=True)
    parser.add_argument("--source-branch")
    parser.add_argument("--source-parent-commit")
    parser.add_argument(
        "--source-state",
        choices=("clean", "working-tree"),
        default="working-tree",
        help="Whether extraction included uncommitted source changes.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    raw_dir = (args.raw_dir or repo_root / "graphify-out").resolve()
    output_dir = (
        args.output_dir or repo_root / "docs" / "architecture" / "dependency-graph"
    ).resolve()
    branch = args.source_branch or git_value(repo_root, "branch", "--show-current")
    parent = args.source_parent_commit or git_value(repo_root, "rev-parse", "HEAD")
    try:
        metadata = generate_snapshot(
            repo_root,
            raw_dir,
            output_dir,
            args.graphify_version,
            branch,
            parent,
            args.source_state == "working-tree",
        )
    except GraphSanitizationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "Sanitized Graphify snapshot: "
        f"{metadata['node_count']} nodes, {metadata['edge_count']} edges, "
        f"{metadata['community_count']} communities"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
