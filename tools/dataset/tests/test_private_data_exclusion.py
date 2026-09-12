"""WP-10.6 (Issue #84): private-data exclusion tests for tools/dataset.

Two things are proven here: first, that tools/dataset/private_data_scan.py
itself actually detects each disallowed pattern (using synthetic files
built in a tmp directory -- never real dataset content); second, that the
real, shipped tools/dataset directory in this repository is clean right
now, so this test fails loudly the moment anything violating
docs/PRIVATE_ARTIFACT_POLICY.md is added to this directory in the future.
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET_DIR = REPO_ROOT / "tools" / "dataset"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scan_mod = _load_module("wp10_private_data_scan", DATASET_DIR / "private_data_scan.py")


class ScanTreeDetectsViolationsTest(unittest.TestCase):
    """Canary cases: each of these synthetic trees must be caught."""

    def test_clean_tree_has_no_violations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ok.py").write_text("# fine\n", encoding="utf-8")
            (root / "ok.json").write_text("{}", encoding="utf-8")
            self.assertEqual(scan_mod.scan_tree(root), [])

    def test_forbidden_suffix_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sneaky.zip").write_bytes(b"not a real archive, just a canary")
            violations = scan_mod.scan_tree(root)
            self.assertTrue(any("forbidden data-file suffix" in v for v in violations))

    def test_oversized_file_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            oversized = root / "too_big.json"
            oversized.write_bytes(b"0" * (scan_mod.MAX_ALLOWED_FILE_BYTES + 1))
            violations = scan_mod.scan_tree(root)
            self.assertTrue(any("exceeds" in v for v in violations))

    def test_private_prefixed_subdirectory_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "private" / "canary.json"
            nested.parent.mkdir(parents=True)
            nested.write_text("{}", encoding="utf-8")
            violations = scan_mod.scan_tree(root)
            self.assertTrue(any("forbidden path segment" in v for v in violations))

    def test_data_prefixed_subdirectory_at_any_depth_is_detected(self):
        # Not just at the scanned root -- nested under an otherwise
        # ordinary-looking path, matching how a real accidental commit
        # is more likely to happen (a subfolder named data/ several
        # levels down, not immediately obvious at the tree root).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "some" / "nested" / "data" / "canary.json"
            nested.parent.mkdir(parents=True)
            nested.write_text("{}", encoding="utf-8")
            violations = scan_mod.scan_tree(root)
            self.assertTrue(any("forbidden path segment" in v for v in violations))

    def test_pycache_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "__pycache__" / "module.cpython-310.pyc"
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b"\x00\x01\x02")
            self.assertEqual(scan_mod.scan_tree(root), [])

    def test_forbidden_directory_names_are_case_insensitive(self):
        for parts in (
            ("Data",),
            ("Private",),
            ("some", "nested", "dAtA"),
            ("some", "nested", "pRiVaTe"),
        ):
            with self.subTest(parts=parts), tempfile.TemporaryDirectory() as tmp:
                # Use a fresh tree for each spelling: Windows may alias
                # differently cased directory names in a shared tree.
                root = Path(tmp)
                nested = root.joinpath(*parts, "canary.json")
                nested.parent.mkdir(parents=True)
                nested.write_text("{}", encoding="utf-8")
                violations = scan_mod.scan_tree(root)
                self.assertTrue(any("forbidden path segment" in v for v in violations))
                with self.assertRaisesRegex(scan_mod.PrivateDataScanError, "forbidden path segment"):
                    scan_mod.assert_tree_is_clean(root)

    def test_assert_tree_is_clean_raises_on_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sneaky.parquet").write_bytes(b"canary")
            with self.assertRaises(scan_mod.PrivateDataScanError):
                scan_mod.assert_tree_is_clean(root)

    def test_assert_tree_is_clean_passes_on_clean_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ok.py").write_text("# fine\n", encoding="utf-8")
            scan_mod.assert_tree_is_clean(root)  # must not raise


class ShippedDatasetToolingIsCleanTest(unittest.TestCase):
    """The real tools/dataset directory, as shipped by this repository,
    must always pass this scan -- this is the test that actually protects
    the repository going forward, not just the synthetic canaries above.
    """

    def test_shipped_tools_dataset_directory_has_no_violations(self):
        scan_mod.assert_tree_is_clean(DATASET_DIR)


if __name__ == "__main__":
    unittest.main()
