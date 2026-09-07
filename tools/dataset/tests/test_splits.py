"""WP-10.4 (Issue #82): tests for tools/dataset/splits.py.

All group_ids here are synthetic identifiers with no relationship to any
real dataset.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


splits_mod = _load_module("wp10_splits", REPO_ROOT / "tools" / "dataset" / "splits.py")


def _synthetic_group_ids(n: int) -> list[str]:
    return [f"grp-synthetic-{i:04d}" for i in range(n)]


class AssignSplitsTest(unittest.TestCase):
    def test_every_group_is_assigned_exactly_once(self):
        group_ids = _synthetic_group_ids(200)
        result = splits_mod.assign_splits(group_ids)
        splits_mod.validate_splits_cover_groups(group_ids, result)

    def test_result_is_deterministic_across_calls(self):
        group_ids = _synthetic_group_ids(50)
        first = splits_mod.assign_splits(group_ids)
        second = splits_mod.assign_splits(group_ids)
        self.assertEqual(first, second)

    def test_result_is_stable_when_new_groups_are_added(self):
        # A group_id's split assignment must not depend on which other
        # group_ids are present -- adding new groups must never move an
        # existing group_id's assigned split.
        base = _synthetic_group_ids(50)
        grown = base + _synthetic_group_ids(200)[50:]  # base + 150 new groups
        base_result = splits_mod.assign_splits(base)
        grown_result = splits_mod.assign_splits(grown)

        def split_of(group_id, result):
            for name, members in result.items():
                if group_id in members:
                    return name
            raise AssertionError(f"{group_id} missing from result")

        for group_id in base:
            self.assertEqual(split_of(group_id, base_result), split_of(group_id, grown_result))

    def test_approximate_ratios_hold_over_many_groups(self):
        group_ids = _synthetic_group_ids(4000)
        result = splits_mod.assign_splits(group_ids)
        total = sum(len(v) for v in result.values())
        self.assertEqual(total, len(group_ids))
        # Loose tolerance -- hash-bucket assignment approximates ratios
        # over a large-enough sample; this is not a statistical claim
        # about any real dataset, just a sanity check on the bucketing.
        train_fraction = len(result["train"]) / total
        self.assertAlmostEqual(train_fraction, 0.7, delta=0.05)

    def test_rejects_ratios_not_summing_to_one(self):
        with self.assertRaises(splits_mod.SplitError):
            splits_mod.assign_splits(["g1"], ratios={"train": 0.5, "validation": 0.2, "test": 0.2})

    def test_rejects_negative_ratio(self):
        with self.assertRaises(splits_mod.SplitError):
            splits_mod.assign_splits(["g1"], ratios={"train": 1.1, "validation": -0.1, "test": 0.0})

    def test_rejects_missing_split_name_in_ratios(self):
        with self.assertRaises(splits_mod.SplitError):
            splits_mod.assign_splits(["g1"], ratios={"train": 0.5, "validation": 0.5})

    def test_rejects_duplicate_group_id(self):
        with self.assertRaises(splits_mod.SplitError):
            splits_mod.assign_splits(["g1", "g2", "g1"])

    def test_all_train_ratio_puts_everything_in_train(self):
        group_ids = _synthetic_group_ids(20)
        result = splits_mod.assign_splits(group_ids, ratios={"train": 1.0, "validation": 0.0, "test": 0.0})
        self.assertEqual(sorted(result["train"]), sorted(group_ids))
        self.assertEqual(result["validation"], [])
        self.assertEqual(result["test"], [])


class ValidateSplitsAreDisjointTest(unittest.TestCase):
    def test_disjoint_splits_pass(self):
        splits_mod.validate_splits_are_disjoint({"train": ["g1"], "validation": ["g2"], "test": ["g3"]})

    def test_overlapping_splits_are_rejected(self):
        with self.assertRaises(splits_mod.SplitError):
            splits_mod.validate_splits_are_disjoint({"train": ["g1"], "validation": ["g1"], "test": []})


class ValidateSplitsCoverGroupsTest(unittest.TestCase):
    def test_exact_coverage_passes(self):
        splits_mod.validate_splits_cover_groups(["g1", "g2"], {"train": ["g1"], "validation": ["g2"], "test": []})

    def test_missing_group_is_rejected(self):
        with self.assertRaises(splits_mod.SplitError):
            splits_mod.validate_splits_cover_groups(["g1", "g2"], {"train": ["g1"], "validation": [], "test": []})

    def test_unexpected_group_is_rejected(self):
        with self.assertRaises(splits_mod.SplitError):
            splits_mod.validate_splits_cover_groups(["g1"], {"train": ["g1", "g2"], "validation": [], "test": []})

    def test_overlap_is_caught_before_coverage(self):
        with self.assertRaises(splits_mod.SplitError):
            splits_mod.validate_splits_cover_groups(["g1"], {"train": ["g1"], "validation": ["g1"], "test": []})


class ApplySplitsToManifestTest(unittest.TestCase):
    def test_sets_sorted_splits_for_all_three_names(self):
        document = {"splits": {}}
        splits_mod.apply_splits_to_manifest(document, {"train": ["g2", "g1"], "validation": [], "test": ["g3"]})
        self.assertEqual(
            document["splits"],
            {"train": ["g1", "g2"], "validation": [], "test": ["g3"]},
        )

    def test_missing_split_name_defaults_to_empty(self):
        document = {"splits": {}}
        splits_mod.apply_splits_to_manifest(document, {"train": ["g1"]})
        self.assertEqual(document["splits"], {"train": ["g1"], "validation": [], "test": []})


if __name__ == "__main__":
    unittest.main()
