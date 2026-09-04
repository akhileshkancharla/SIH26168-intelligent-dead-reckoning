from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sanitize = load_module("sanitize_graph", REPO_ROOT / "tools" / "graphify" / "sanitize_graph.py")
verify = load_module("verify_graph", REPO_ROOT / "tools" / "graphify" / "verify_graph.py")


def synthetic_graph(source_file: str = "src/main.py") -> dict:
    return {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {"id": "z", "label": "callee", "source_file": source_file, "source_location": "L2", "community": 1},
            {"id": "a", "label": "caller", "source_file": "src/entry.py", "source_location": "L1", "community": 0},
        ],
        "links": [
            {
                "source": "a",
                "target": "z",
                "relation": "calls",
                "context": "call",
                "source_file": "src/entry.py",
                "source_location": "L1",
                "confidence": "EXTRACTED",
            }
        ],
        "hyperedges": [],
        "built_at_commit": "0" * 40,
    }


class PathSanitizationTests(unittest.TestCase):
    def test_windows_repository_path_is_normalized(self):
        alias = "Z" + ":" + "\\" + "work" + "\\" + "repo"
        value = alias + "\\" + "src" + "\\" + "main.py"
        policy = sanitize.PathPolicy(Path("/repo"), [alias])
        self.assertEqual(policy.sanitize_path(value, "$.source_file"), "src/main.py")

    def test_windows_outside_path_is_rejected(self):
        value = "Q" + ":" + "\\" + "Users" + "\\" + "person" + "\\" + "file.py"
        policy = sanitize.PathPolicy(Path("/repo"))
        with self.assertRaises(sanitize.GraphSanitizationError):
            policy.sanitize_path(value, "$.source_file")

    def test_unix_repository_path_is_normalized(self):
        root = "/" + "srv" + "/repo"
        policy = sanitize.PathPolicy(Path(root), [root])
        self.assertEqual(
            policy.sanitize_path(root + "/src/main.py", "$.source_file"),
            "src/main.py",
        )

    def test_unix_outside_path_is_rejected(self):
        value = "/" + "opt" + "/outside/file.py"
        policy = sanitize.PathPolicy(Path("/repo"))
        with self.assertRaises(sanitize.GraphSanitizationError):
            policy.sanitize_path(value, "$.source_file")

    def test_user_profile_path_is_rejected(self):
        value = "/" + "home" + "/person/private/file.py"
        with self.assertRaises(sanitize.GraphSanitizationError):
            sanitize.PathPolicy(Path("/repo")).sanitize_text(value, "$.label")

    def test_relative_backslashes_are_normalized(self):
        policy = sanitize.PathPolicy(Path("/repo"))
        self.assertEqual(policy.sanitize_path("src\\main.py", "$.source_file"), "src/main.py")

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(sanitize.GraphSanitizationError):
            sanitize.PathPolicy(Path("/repo")).sanitize_path("../outside.py", "$.source_file")


class GraphStructureTests(unittest.TestCase):
    def test_nodes_and_edges_are_stably_sorted(self):
        graph = synthetic_graph()
        graph["links"].append(
            {
                "source": "z",
                "target": "a",
                "relation": "references",
                "context": "type",
                "source_file": "src/main.py",
                "source_location": "L2",
                "confidence": "INFERRED",
            }
        )
        clean, _ = sanitize.sanitize_graph_document(graph, sanitize.PathPolicy(Path("/repo")))
        self.assertEqual([node["id"] for node in clean["nodes"]], ["a", "z"])
        self.assertEqual([edge["source"] for edge in clean["links"]], ["a", "z"])

    def test_duplicate_node_is_detected(self):
        graph = synthetic_graph()
        graph["nodes"].append(dict(graph["nodes"][0]))
        errors = verify.validate_graph_document(graph)
        self.assertTrue(any("duplicate node id" in error for error in errors))

    def test_invalid_edge_endpoint_is_detected(self):
        graph = synthetic_graph()
        graph["links"][0]["target"] = "missing"
        errors = verify.validate_graph_document(graph)
        self.assertTrue(any("invalid target endpoint" in error for error in errors))

    def test_secret_like_value_is_rejected(self):
        token = "gh" + "p_" + ("A" * 24)
        errors = verify.scan_text(token, "synthetic")
        self.assertTrue(any("token" in error.lower() for error in errors))


class SnapshotTests(unittest.TestCase):
    def create_snapshot(self, root: Path) -> tuple[Path, Path]:
        raw = root / "raw"
        output = root / "snapshot"
        raw.mkdir()
        repository_alias = "R" + ":" + "\\" + "checkout"
        graph = synthetic_graph(repository_alias + "\\" + "src" + "\\" + "main.py")
        (raw / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
        (raw / "GRAPH_REPORT.md").write_text(
            "## Import Cycles\n- None detected.\n**1 isolated node(s):** sample\n",
            encoding="utf-8",
        )
        (raw / ".graphify_root").write_text(repository_alias, encoding="utf-8")
        sanitize.generate_snapshot(
            REPO_ROOT,
            raw,
            output,
            "0.9.53",
            "test-branch",
            "0" * 40,
            True,
        )
        return raw, output

    def test_raw_root_marker_is_not_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            raw, output = self.create_snapshot(Path(directory))
            self.assertTrue((raw / ".graphify_root").is_file())
            self.assertFalse((output / ".graphify_root").exists())

    def test_repeated_sanitization_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            raw, output = self.create_snapshot(Path(directory))
            first = {path.name: path.read_bytes() for path in output.iterdir()}
            sanitize.generate_snapshot(
                REPO_ROOT,
                raw,
                output,
                "0.9.53",
                "test-branch",
                "0" * 40,
                True,
            )
            second = {path.name: path.read_bytes() for path in output.iterdir()}
            self.assertEqual(first, second)

    def test_hash_verification_passes_then_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            _, output = self.create_snapshot(Path(directory))
            self.assertEqual(verify.validate_snapshot(output, REPO_ROOT), [])
            report = output / "GRAPH_REPORT.md"
            report.write_text(report.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8")
            errors = verify.validate_snapshot(output, REPO_ROOT)
            self.assertTrue(any("checksum mismatch" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
