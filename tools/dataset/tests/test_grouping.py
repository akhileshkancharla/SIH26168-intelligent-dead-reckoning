"""WP-10.3 (Issue #81): tests for tools/dataset/grouping.py.

All FileRecord instances here are synthetic -- fabricated identifiers,
hashes and session IDs used only to exercise the grouping algorithm.
Hashes are real-format-but-fabricated SHA-256 digests (computed from a
synthetic label), never real IO-VNBD content, so that _validate_record's
hash-shape check exercises the exact same code path production input
would.
"""
from __future__ import annotations

import hashlib
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


def _h(label: str) -> str:
    """A real-format-but-fabricated SHA-256 hex digest for `label`."""
    return hashlib.sha256(f"grouping-test:{label}".encode("utf-8")).hexdigest()


class ComputeGroupsTest(unittest.TestCase):
    def test_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            grouping.compute_groups([])

    def test_singletons_get_distinct_groups(self):
        records = [
            grouping.FileRecord("f1", _h("a")),
            grouping.FileRecord("f2", _h("b")),
            grouping.FileRecord("f3", _h("c")),
        ]
        groups = grouping.compute_groups(records)
        self.assertEqual(len(set(groups.values())), 3, "unrelated files must not be merged")

    def test_exact_duplicates_share_a_group(self):
        records = [
            grouping.FileRecord("f1", _h("a")),
            grouping.FileRecord("f2", _h("a")),  # byte-identical to f1
            grouping.FileRecord("f3", _h("b")),
        ]
        groups = grouping.compute_groups(records)
        self.assertEqual(groups["f1"], groups["f2"])
        self.assertNotEqual(groups["f1"], groups["f3"])

    def test_shared_parent_session_shares_a_group_even_with_different_hashes(self):
        records = [
            grouping.FileRecord("f1", _h("a"), parent_session_id="session-1"),
            grouping.FileRecord("f2", _h("b"), parent_session_id="session-1"),
            grouping.FileRecord("f3", _h("c"), parent_session_id="session-2"),
        ]
        groups = grouping.compute_groups(records)
        self.assertEqual(groups["f1"], groups["f2"])
        self.assertNotEqual(groups["f1"], groups["f3"])

    def test_transitive_merge_across_hash_and_session(self):
        # f1/f2 share a session; f2/f3 share a hash. All three must end up
        # in one group (transitive closure), even though f1 and f3 share
        # neither a hash nor a session directly with each other.
        records = [
            grouping.FileRecord("f1", _h("a"), parent_session_id="session-1"),
            grouping.FileRecord("f2", _h("b"), parent_session_id="session-1"),
            grouping.FileRecord("f3", _h("b")),
        ]
        groups = grouping.compute_groups(records)
        self.assertEqual(len({groups["f1"], groups["f2"], groups["f3"]}), 1)

    def test_none_and_empty_session_ids_never_merge_unrelated_files(self):
        records = [
            grouping.FileRecord("f1", _h("a"), parent_session_id=None),
            grouping.FileRecord("f2", _h("b"), parent_session_id=None),
            grouping.FileRecord("f3", _h("c"), parent_session_id=None),
        ]
        groups = grouping.compute_groups(records)
        self.assertEqual(len(set(groups.values())), 3, "missing session IDs must never be treated as a shared session")

    def test_result_is_deterministic_regardless_of_input_order(self):
        records_a = [
            grouping.FileRecord("f1", _h("a"), parent_session_id="session-1"),
            grouping.FileRecord("f2", _h("b"), parent_session_id="session-1"),
            grouping.FileRecord("f3", _h("c")),
        ]
        records_b = list(reversed(records_a))
        self.assertEqual(grouping.compute_groups(records_a), grouping.compute_groups(records_b))

    def test_inconsistent_duplicate_identifier_is_rejected(self):
        records = [
            grouping.FileRecord("f1", _h("a")),
            grouping.FileRecord("f1", _h("b")),  # same identifier, different hash
        ]
        with self.assertRaises(ValueError):
            grouping.compute_groups(records)

    def test_repeated_identical_record_is_not_an_error(self):
        # The exact same record appearing twice (e.g. listed in two
        # source archives) is not an inconsistency.
        records = [
            grouping.FileRecord("f1", _h("a")),
            grouping.FileRecord("f1", _h("a")),
        ]
        groups = grouping.compute_groups(records)
        self.assertEqual(len(groups), 1)

    def test_repeated_identical_record_does_not_change_the_resulting_group_id(self):
        # The specific regression this guards against: identifiers used
        # to seed by_hash/by_session was built from the raw (possibly
        # repeat-containing) records list, so one f1 record and two
        # identical f1 records could produce different group IDs purely
        # because of how many times f1 was listed -- not because
        # anything about the actual grouping changed.
        single = grouping.compute_groups([grouping.FileRecord("f1", _h("a"))])
        repeated = grouping.compute_groups(
            [grouping.FileRecord("f1", _h("a")), grouping.FileRecord("f1", _h("a")), grouping.FileRecord("f1", _h("a"))]
        )
        self.assertEqual(single["f1"], repeated["f1"])

    def test_rejects_empty_identifier(self):
        with self.assertRaises(ValueError):
            grouping.compute_groups([grouping.FileRecord("", _h("a"))])

    def test_rejects_whitespace_only_identifier(self):
        with self.assertRaises(ValueError):
            grouping.compute_groups([grouping.FileRecord("   ", _h("a"))])

    def test_rejects_malformed_hash(self):
        malformed_hashes = [
            "not-a-sha256-digest",
            _h("a")[:-1],  # 63 chars, one short
            _h("a").upper(),  # uppercase hex is not accepted
            _h("a") + "0",  # 65 chars, one long
            "",
        ]
        for bad_hash in malformed_hashes:
            with self.subTest(sha256=bad_hash):
                with self.assertRaises(ValueError):
                    grouping.compute_groups([grouping.FileRecord("f1", bad_hash)])

    def test_rejects_whitespace_only_parent_session_id(self):
        # A blank session id must never be accepted as if it meant "no
        # session" (that is what None is for) -- an accepted blank string
        # would incorrectly group every blank-session record together.
        with self.assertRaises(ValueError):
            grouping.compute_groups([grouping.FileRecord("f1", _h("a"), parent_session_id="   ")])


class DuplicateMembersByGroupTest(unittest.TestCase):
    def test_reports_only_groups_with_hash_collisions(self):
        records = [
            grouping.FileRecord("f1", _h("a")),
            grouping.FileRecord("f2", _h("a")),  # duplicate of f1
            grouping.FileRecord("f3", _h("b"), parent_session_id="session-1"),
            grouping.FileRecord("f4", _h("c"), parent_session_id="session-1"),  # session sibling, not a duplicate
        ]
        groups = grouping.compute_groups(records)
        duplicates = grouping.duplicate_members_by_group(records, groups)
        self.assertEqual(len(duplicates), 1)
        (only_group,) = duplicates.values()
        self.assertEqual(only_group, ["f1", "f2"])

    def test_repeated_identical_record_does_not_create_duplicate_evidence(self):
        # The specific regression this guards against: a single file
        # listed three times identically is still just one file, not
        # three files that happen to share a hash -- duplicate_members_by_group
        # must not report it as a duplicate group at all.
        records = [
            grouping.FileRecord("f1", _h("a")),
            grouping.FileRecord("f1", _h("a")),
            grouping.FileRecord("f1", _h("a")),
        ]
        groups = grouping.compute_groups(records)
        duplicates = grouping.duplicate_members_by_group(records, groups)
        self.assertEqual(duplicates, {})


class ApplyGroupsToManifestTest(unittest.TestCase):
    def test_sets_sorted_unique_group_ids(self):
        document = {"group_ids": [], "file_group_ids": {}}
        groups = {"f1": "grp-b", "f2": "grp-a", "f3": "grp-b"}
        grouping.apply_groups_to_manifest(document, groups)
        self.assertEqual(document["group_ids"], ["grp-a", "grp-b"])

    def test_sets_full_file_group_id_membership_mapping(self):
        # This is the fix itself: apply_groups_to_manifest previously
        # discarded the identifier -> group_id mapping and stored only
        # the unique group_id set, so a manifest could not prove that
        # every file resolves to exactly one group.
        document = {"group_ids": [], "file_group_ids": {}}
        groups = {"f1": "grp-b", "f2": "grp-a", "f3": "grp-b"}
        grouping.apply_groups_to_manifest(document, groups)
        self.assertEqual(document["file_group_ids"], {"f1": "grp-b", "f2": "grp-a", "f3": "grp-b"})


class VerifyGroupMembershipTest(unittest.TestCase):
    def _document(self, file_hashes, file_group_ids, group_ids):
        return {"file_hashes": file_hashes, "file_group_ids": file_group_ids, "group_ids": group_ids}

    def test_complete_and_no_extra_membership_passes(self):
        document = self._document(
            file_hashes={"f1": _h("a"), "f2": _h("b")},
            file_group_ids={"f1": "grp-1", "f2": "grp-2"},
            group_ids=["grp-1", "grp-2"],
        )
        grouping.verify_group_membership(document)  # must not raise

    def test_missing_file_group_id_entry_is_rejected(self):
        # "complete" coverage: every file_hashes identifier must appear
        # in file_group_ids.
        document = self._document(
            file_hashes={"f1": _h("a"), "f2": _h("b")},
            file_group_ids={"f1": "grp-1"},  # f2 missing
            group_ids=["grp-1"],
        )
        with self.assertRaises(ValueError):
            grouping.verify_group_membership(document)

    def test_extra_file_group_id_entry_is_rejected(self):
        # "no-extra" coverage: file_group_ids must not reference an
        # identifier that isn't in file_hashes at all.
        document = self._document(
            file_hashes={"f1": _h("a")},
            file_group_ids={"f1": "grp-1", "unexpected": "grp-1"},
            group_ids=["grp-1"],
        )
        with self.assertRaises(ValueError):
            grouping.verify_group_membership(document)

    def test_undeclared_group_id_reference_is_rejected(self):
        # file_group_ids referencing a group_id that group_ids never
        # declared is an inconsistency, not something to silently accept.
        document = self._document(
            file_hashes={"f1": _h("a")},
            file_group_ids={"f1": "grp-not-declared"},
            group_ids=["grp-1"],
        )
        with self.assertRaises(ValueError):
            grouping.verify_group_membership(document)

    def test_unused_declared_group_id_is_rejected(self):
        # A group_id declared but never actually referenced by any file
        # is equally an inconsistency (a stale or orphaned group_id).
        document = self._document(
            file_hashes={"f1": _h("a")},
            file_group_ids={"f1": "grp-1"},
            group_ids=["grp-1", "grp-orphaned"],
        )
        with self.assertRaises(ValueError):
            grouping.verify_group_membership(document)

    def test_real_pipeline_output_passes_verification(self):
        # End-to-end: compute_groups + apply_groups_to_manifest output
        # must satisfy verify_group_membership without any hand-tuning.
        records = [
            grouping.FileRecord("f1", _h("a")),
            grouping.FileRecord("f2", _h("a")),  # duplicate of f1
            grouping.FileRecord("f3", _h("c"), parent_session_id="session-1"),
            grouping.FileRecord("f4", _h("d"), parent_session_id="session-1"),
        ]
        groups = grouping.compute_groups(records)
        document = {
            "file_hashes": {r.identifier: r.sha256 for r in records},
            "group_ids": [],
            "file_group_ids": {},
        }
        grouping.apply_groups_to_manifest(document, groups)
        grouping.verify_group_membership(document)  # must not raise


if __name__ == "__main__":
    unittest.main()
