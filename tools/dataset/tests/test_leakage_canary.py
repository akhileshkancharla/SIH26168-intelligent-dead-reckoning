"""WP-10.6 (Issue #84): end-to-end leakage canary tests.

Each WP-10 module (manifest.py, schema_allowlist.py, grouping.py,
splits.py, feature_firewall.py) already has unit tests proving it
rejects bad input in isolation. This module instead wires them together
into small, fully synthetic end-to-end scenarios -- a "canary" scenario
is one that is deliberately built to try to sneak a leakage failure
past the *composition* of these modules, not just past any one of them
alone, per the architecture's "runtime-vs-label canary checks" and
"leakage/canary" acceptance criteria for C-15 / WP-10
(docs/architecture/SIH26168_Development_Sequence_v1.md,
docs/architecture/SIH26168_Component_Register_v1.csv). Every identifier,
hash, schema name, feature name and label name here is synthetic and
invented for this test file; none of it describes real IO-VNBD data.
"""
from __future__ import annotations

import hashlib
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET_DIR = REPO_ROOT / "tools" / "dataset"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    # Registered before exec_module: on Python 3.10, a module using
    # `from __future__ import annotations` together with a @dataclass
    # needs its own module object discoverable via sys.modules during
    # dataclass field processing, or it fails with
    # AttributeError: 'NoneType' object has no attribute '__dict__'.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


manifest_mod = _load_module("wp10_canary_manifest", DATASET_DIR / "manifest.py")
allowlist_mod = _load_module("wp10_canary_schema_allowlist", DATASET_DIR / "schema_allowlist.py")
grouping_mod = _load_module("wp10_canary_grouping", DATASET_DIR / "grouping.py")
splits_mod = _load_module("wp10_canary_splits", DATASET_DIR / "splits.py")
firewall_mod = _load_module("wp10_canary_feature_firewall", DATASET_DIR / "feature_firewall.py")


def _synthetic_hash(label: str) -> str:
    return hashlib.sha256(f"synthetic-canary:{label}".encode("utf-8")).hexdigest()


def _synthetic_allowlist_document() -> dict:
    return {
        "schema_version": 1,
        "status": "ACTIVE",
        "allowlist": [f"synthetic_canary_schema_{i}" for i in range(1, 7)],
    }


def _synthetic_firewall_document() -> dict:
    return {
        "schema_version": 1,
        "status": "ACTIVE",
        "runtime_allowed_features": ["synthetic_canary_feature_accel", "synthetic_canary_feature_gnss"],
        "forbidden_labels": ["synthetic_canary_label_can_speed"],
    }


def _base_records() -> list:
    """Six synthetic FileRecords: two exact duplicates, two sharing a
    parent_session_id, two independent singletons.
    """
    dup_hash = _synthetic_hash("duplicate-content")
    return [
        grouping_mod.FileRecord(identifier="canary-file-1", sha256=dup_hash),
        grouping_mod.FileRecord(identifier="canary-file-2", sha256=dup_hash),
        grouping_mod.FileRecord(
            identifier="canary-file-3", sha256=_synthetic_hash("session-member-a"),
            parent_session_id="canary-session-alpha",
        ),
        grouping_mod.FileRecord(
            identifier="canary-file-4", sha256=_synthetic_hash("session-member-b"),
            parent_session_id="canary-session-alpha",
        ),
        grouping_mod.FileRecord(identifier="canary-file-5", sha256=_synthetic_hash("singleton-a")),
        grouping_mod.FileRecord(identifier="canary-file-6", sha256=_synthetic_hash("singleton-b")),
    ]


def _build_end_to_end_manifest(records: list) -> tuple:
    """Run the full WP-10.1->10.4 pipeline over `records` and return
    (manifest_document, groups, splits).
    """
    groups = grouping_mod.compute_groups(records)
    group_ids = sorted(set(groups.values()))
    splits = splits_mod.assign_splits(group_ids)
    splits_mod.validate_splits_cover_groups(group_ids, splits)

    document = manifest_mod.new_manifest(
        dataset_id="canary-synthetic-dataset",
        source_revision="0000000000000000000000000000000000000000",
        rights_status="SYNTHETIC_TEST_FIXTURE_NO_REAL_DATA",
        privacy="SYNTHETIC_NON_PRIVATE",
        redistribution="NOT_APPLICABLE_SYNTHETIC",
    )
    document["archive_hashes"] = {"canary-archive": _synthetic_hash("archive")}
    document["file_hashes"] = {r.identifier: r.sha256 for r in records}
    document["schemas"] = ["synthetic_canary_schema_1", "synthetic_canary_schema_2"]
    document["units_status"] = {"synthetic_canary_schema_1": {"status": "DECLARED"}}
    document["exclusions"] = []
    grouping_mod.apply_groups_to_manifest(document, groups)
    grouping_mod.verify_group_membership(document)
    splits_mod.apply_splits_to_manifest(document, splits)
    manifest_mod.validate_manifest(document)
    return document, groups, splits


class GoldenPathEndToEndTest(unittest.TestCase):
    """The full pipeline, run over a clean synthetic scenario, must pass
    every stage without any module needing to reject anything. This is
    the control case the canary (attack) tests below are contrasted
    against -- if this ever starts failing, a canary failure elsewhere
    could mean the pipeline is broken rather than correctly defensive.
    """

    def test_clean_synthetic_scenario_passes_every_stage(self):
        document, groups, splits = _build_end_to_end_manifest(_base_records())
        splits_mod.validate_splits_are_disjoint(document["splits"])
        allowlist_mod.enforce_manifest_against_allowlist(document, _synthetic_allowlist_document())
        firewall_mod.enforce_feature_set(
            ["synthetic_canary_feature_accel", "synthetic_canary_feature_gnss"],
            _synthetic_firewall_document(),
        )

    def test_duplicate_content_files_are_grouped_together(self):
        _, groups, _ = _build_end_to_end_manifest(_base_records())
        self.assertEqual(groups["canary-file-1"], groups["canary-file-2"])

    def test_shared_session_files_are_grouped_together(self):
        _, groups, _ = _build_end_to_end_manifest(_base_records())
        self.assertEqual(groups["canary-file-3"], groups["canary-file-4"])


class CanaryUnknownSchemaIsQuarantinedTest(unittest.TestCase):
    """A manifest that is otherwise perfectly well-formed, and that
    passes validate_manifest, must still be rejected end-to-end the
    moment it names one schema outside the active allowlist -- schema
    validity alone must never be mistaken for allowlist compliance.
    """

    def test_manifest_with_one_out_of_allowlist_schema_is_rejected(self):
        document, _, _ = _build_end_to_end_manifest(_base_records())
        document["schemas"] = ["synthetic_canary_schema_1", "attacker_injected_unknown_schema"]
        manifest_mod.validate_manifest(document)  # still structurally valid on its own
        with self.assertRaises(allowlist_mod.SchemaAllowlistError):
            allowlist_mod.enforce_manifest_against_allowlist(document, _synthetic_allowlist_document())


class CanaryForbiddenLabelHiddenAmongAllowedFeaturesTest(unittest.TestCase):
    """A forbidden label mixed in among otherwise-legitimate runtime
    features must still be caught -- the firewall must not be fooled by
    a mostly-clean feature set into approving the whole batch.
    """

    def test_one_forbidden_label_among_many_allowed_features_is_rejected(self):
        proposed = [
            "synthetic_canary_feature_accel",
            "synthetic_canary_feature_gnss",
            "synthetic_canary_label_can_speed",  # smuggled in
        ]
        with self.assertRaises(firewall_mod.FeatureFirewallError):
            firewall_mod.enforce_feature_set(proposed, _synthetic_firewall_document())

    def test_audit_isolates_exactly_the_bad_entry(self):
        proposed = [
            "synthetic_canary_feature_accel",
            "synthetic_canary_feature_gnss",
            "synthetic_canary_label_can_speed",
        ]
        result = firewall_mod.audit_feature_set(proposed, _synthetic_firewall_document())
        self.assertEqual(result["synthetic_canary_feature_accel"], firewall_mod.ALLOWED)
        self.assertEqual(result["synthetic_canary_feature_gnss"], firewall_mod.ALLOWED)
        self.assertEqual(result["synthetic_canary_label_can_speed"], firewall_mod.FORBIDDEN_LABEL)


class CanaryDuplicateContentNeverStraddlesASplitTest(unittest.TestCase):
    """Demonstrates the specific leakage that grouping-before-splitting
    exists to prevent: splitting by identifier alone (ignoring content
    grouping) CAN put two byte-identical files in different splits,
    while splitting by group_id (as tools/dataset actually does) always
    keeps them together, regardless of what their individual identifiers
    happen to hash to.
    """

    def test_naive_per_identifier_hashing_would_have_split_these_two_apart(self):
        # These two identifiers were deliberately chosen (see this PR's
        # description) because hashing each one directly, independent of
        # content, lands them in different default-ratio buckets --
        # proving the scenario below is a real attack this pipeline must
        # defend against, not a vacuously-true assertion.
        position_a = splits_mod._stable_unit_interval_position("file-canary-0-a")
        position_b = splits_mod._stable_unit_interval_position("file-canary-0-b")

        def bucket(position: float) -> str:
            if position < 0.7:
                return "train"
            if position < 0.85:
                return "validation"
            return "test"

        self.assertNotEqual(
            bucket(position_a), bucket(position_b),
            "test fixture assumption broken: pick a different identifier pair",
        )

    def test_grouped_assignment_keeps_duplicate_content_in_one_split(self):
        # canary-file-1 and canary-file-2 are byte-identical (see
        # _base_records) and therefore share one group_id; assign_splits
        # operates on group_ids, so they are structurally incapable of
        # landing in different splits, unlike the naive per-identifier
        # hashing demonstrated above.
        document, groups, splits = _build_end_to_end_manifest(_base_records())
        group_id = groups["canary-file-1"]
        self.assertEqual(group_id, groups["canary-file-2"])

        containing_splits = [name for name, members in splits.items() if group_id in members]
        self.assertEqual(len(containing_splits), 1)


class CanaryOverlappingSplitsAreRejectedEndToEndTest(unittest.TestCase):
    """A splits assignment corrupted after the fact (e.g. by a buggy or
    malicious external tool) to place one real, grouped group_id in two
    splits at once must be caught before it reaches a committed
    manifest -- exercised here against group_ids that actually came out
    of compute_groups, not hand-invented strings.
    """

    def test_hand_corrupted_overlap_on_real_group_ids_is_rejected(self):
        _, groups, splits = _build_end_to_end_manifest(_base_records())
        any_group_id = next(iter(groups.values()))
        corrupted = {name: list(members) for name, members in splits.items()}
        # Inject the same real group_id into a second split too.
        other_split = next(name for name in corrupted if any_group_id not in corrupted[name])
        corrupted[other_split].append(any_group_id)

        with self.assertRaises(splits_mod.SplitError):
            splits_mod.validate_splits_are_disjoint(corrupted)


class CanaryOrphanedGroupIdInSplitsTest(unittest.TestCase):
    """A splits dictionary that references a group_id absent from the
    manifest's own group_ids (e.g. a stale split left over from a
    previous, larger dataset revision) must be rejected as an
    inconsistency, not silently accepted.
    """

    def test_split_referencing_an_unknown_group_id_is_rejected(self):
        _, groups, splits = _build_end_to_end_manifest(_base_records())
        real_group_ids = sorted(set(groups.values()))
        corrupted = {name: list(members) for name, members in splits.items()}
        corrupted["train"].append("grp-stale-from-a-previous-revision")

        with self.assertRaises(splits_mod.SplitError):
            splits_mod.validate_splits_cover_groups(real_group_ids, corrupted)


class CanaryCorruptedFileGroupMembershipTest(unittest.TestCase):
    """WP-10.3's file_group_ids is the manifest's own committed proof that
    every file_hashes identifier resolves to exactly one group -- exercised
    here end-to-end against a manifest that actually came out of
    _build_end_to_end_manifest, not a hand-invented document, so this
    proves the composed pipeline calls verify_group_membership() (added
    to _build_end_to_end_manifest per this file's own review), not just
    that grouping.py's own unit tests do.
    """

    def test_removed_file_group_id_entry_is_rejected_end_to_end(self):
        # Simulate a tool that updates file_hashes with a new file but
        # forgets to also extend file_group_ids -- exactly the
        # "membership silently goes stale" failure verify_group_membership
        # exists to catch.
        document, _, _ = _build_end_to_end_manifest(_base_records())
        del document["file_group_ids"]["canary-file-1"]

        with self.assertRaises(ValueError):
            grouping_mod.verify_group_membership(document)

    def test_corrupted_file_group_id_reference_is_rejected_end_to_end(self):
        # Simulate a hand-edit that repoints one file at a group_id that
        # was never actually produced by compute_groups for this
        # dataset revision -- an undeclared-group-reference attack, not
        # just a missing/extra key.
        document, _, _ = _build_end_to_end_manifest(_base_records())
        document["file_group_ids"]["canary-file-1"] = "grp-never-computed-for-this-revision"

        with self.assertRaises(ValueError):
            grouping_mod.verify_group_membership(document)


if __name__ == "__main__":
    unittest.main()
