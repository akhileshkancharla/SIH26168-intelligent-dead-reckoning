"""WP-10.3 (Issue #81): tests for tools/dataset/grouping.py.

All FileRecord instances here are synthetic -- fabricated identifiers,
hashes and session IDs used only to exercise the grouping algorithm.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec: grouping.py's @dataclass(frozen=True) with
    # `from __future__ import annotations` needs sys.modules[__name__] to
    # already exist when the class body executes, or dataclasses' own
    # forward-reference resolution raises AttributeError on a None module.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


grouping = _load_module("wp10_grouping", REPO_ROOT / "tools" / "dataset" / "grouping.py")


class ComputeGroupsTest(unittest.TestCase):
    def test_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            grouping.compute_groups([])

    def test_singletons_get_distinct_groups(self):
        records = [
            grouping.FileRecord("f1", "hash-a"),
            grouping.FileRecord("f2", "hash-b"),
            grouping.FileRecord("f3", "hash-c"),
        ]
        groups = grouping.compute_groups(records)
        self.assertEqual(len(set(groups.values())), 3, "unrelated files must not be merged")

    def test_exact_duplicates_share_a_group(self):
        records = [
            grouping.FileRecord("f1", "hash-a"),
            grouping.FileRecord("f2", "hash-a"),  # byte-identical to f1
            grouping.FileRecord("f3", "hash-b"),
        ]
        groups = grouping.compute_groups(records)
        self.assertEqual(groups["f1"], groups["f2"])
        self.assertNotEqual(groups["f1"], groups["f3"])

    def test_shared_parent_session_shares_a_group_even_with_different_hashes(self):
        records = [
            grouping.FileRecord("f1", "hash-a", parent_session_id="session-1"),
            grouping.FileRecord("f2", "hash-b", parent_session_id="session-1"),
            grouping.FileRecord("f3", "hash-c", parent_session_id="session-2"),
        ]
        groups = grouping.compute_groups(records)
        self.assertEqual(groups["f1"], groups["f2"])
        self.assertNotEqual(groups["f1"], groups["f3"])

    def test_transitive_merge_across_hash_and_session(self):
        # f1/f2 share a session; f2/f3 share a hash. All three must end up
        # in one group (transitive closure), even though f1 and f3 share
        # neither a hash nor a session directly with each other.
        records = [
            grouping.FileRecord("f1", "hash-a", parent_session_id="session-1"),
            grouping.FileRecord("f2", "hash-b", parent_session_id="session-1"),
            grouping.FileRecord("f3", "hash-b"),
        ]
        groups = grouping.compute_groups(records)
        self.assertEqual(len({groups["f1"], groups["f2"], groups["f3"]}), 1)

    def test_none_and_empty_session_ids_never_merge_unrelated_files(self):
        records = [
            grouping.FileRecord("f1", "hash-a", parent_session_id=None),
            grouping.FileRecord("f2", "hash-b", parent_session_id=""),
            grouping.FileRecord("f3", "hash-c", parent_session_id=None),
        ]
        groups = grouping.compute_groups(records)
        self.assertEqual(len(set(groups.values())), 3, "missing/empty session IDs must never be treated as a shared session")

    def test_result_is_deterministic_regardless_of_input_order(self):
        records_a = [
            grouping.FileRecord("f1", "hash-a", parent_session_id="session-1"),
            grouping.FileRecord("f2", "hash-b", parent_session_id="session-1"),
            grouping.FileRecord("f3", "hash-c"),
        ]
        records_b = list(reversed(records_a))
        self.assertEqual(grouping.compute_groups(records_a), grouping.compute_groups(records_b))

    def test_inconsistent_duplicate_identifier_is_rejected(self):
        records = [
            grouping.FileRecord("f1", "hash-a"),
            grouping.FileRecord("f1", "hash-b"),  # same identifier, different hash
        ]
        with self.assertRaises(ValueError):
            grouping.compute_groups(records)

    def test_repeated_identical_record_is_not_an_error(self):
        # The exact same record appearing twice (e.g. listed in two
        # source archives) is not an inconsistency.
        records = [
            grouping.FileRecord("f1", "hash-a"),
            grouping.FileRecord("f1", "hash-a"),
        ]
        groups = grouping.compute_groups(records)
        self.assertEqual(len(groups), 1)


class DuplicateMembersByGroupTest(unittest.TestCase):
    def test_reports_only_groups_with_hash_collisions(self):
        records = [
            grouping.FileRecord("f1", "hash-a"),
            grouping.FileRecord("f2", "hash-a"),  # duplicate of f1
            grouping.FileRecord("f3", "hash-b", parent_session_id="session-1"),
            grouping.FileRecord("f4", "hash-c", parent_session_id="session-1"),  # session sibling, not a duplicate
        ]
        groups = grouping.compute_groups(records)
        duplicates = grouping.duplicate_members_by_group(records, groups)
        self.assertEqual(len(duplicates), 1)
        (only_group,) = duplicates.values()
        self.assertEqual(only_group, ["f1", "f2"])


class ApplyGroupsToManifestTest(unittest.TestCase):
    def test_sets_sorted_unique_group_ids(self):
        document = {"group_ids": []}
        groups = {"f1": "grp-b", "f2": "grp-a", "f3": "grp-b"}
        grouping.apply_groups_to_manifest(document, groups)
        self.assertEqual(document["group_ids"], ["grp-a", "grp-b"])


if __name__ == "__main__":
    unittest.main()
