"""WP-10.1 (Issue #79): tests for tools/dataset/manifest.py.

Uses only the synthetic fixture under tools/dataset/tests/fixtures/ --
never real IO-VNBD data or hashes -- per docs/PRIVATE_ARTIFACT_POLICY.md
and the Verification Strategy's "unit tests only on synthetic/tiny lawful
fixtures; no IO-VNBD download" rule.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "dataset_manifest_v1_fixture.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


manifest = _load_module("wp10_manifest", REPO_ROOT / "tools" / "dataset" / "manifest.py")


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class DatasetManifestSchemaTest(unittest.TestCase):
    def test_schema_is_valid_draft_2020_12(self):
        import jsonschema

        jsonschema.Draft202012Validator.check_schema(manifest.load_schema())

    def test_schema_is_tier_a_closed(self):
        schema = manifest.load_schema()
        self.assertFalse(
            schema.get("additionalProperties", True),
            "DatasetManifestV1 is a Tier A contract (I-20): additionalProperties must be false",
        )

    def test_golden_fixture_validates(self):
        manifest.validate_manifest(_fixture())

    def test_removing_a_required_field_is_rejected(self):
        schema = manifest.load_schema()
        for field in schema["required"]:
            with self.subTest(missing=field):
                doc = copy.deepcopy(_fixture())
                del doc[field]
                with self.assertRaises(manifest.DatasetManifestError):
                    manifest.validate_manifest(doc)

    def test_unrecognized_top_level_field_is_rejected(self):
        doc = copy.deepcopy(_fixture())
        doc["x_unapproved_field"] = True
        with self.assertRaises(manifest.DatasetManifestError):
            manifest.validate_manifest(doc)

    def test_malformed_hash_is_rejected(self):
        doc = copy.deepcopy(_fixture())
        doc["archive_hashes"]["synthetic-archive-01"] = "not-a-sha256-digest"
        with self.assertRaises(manifest.DatasetManifestError):
            manifest.validate_manifest(doc)

    def test_empty_archive_hashes_is_rejected(self):
        # archive_hashes/file_hashes/schemas all require minProperties/
        # minItems >= 1: a DatasetManifest may never claim to cover zero
        # archives while still being "complete".
        doc = copy.deepcopy(_fixture())
        doc["archive_hashes"] = {}
        with self.assertRaises(manifest.DatasetManifestError):
            manifest.validate_manifest(doc)

    def test_new_manifest_skeleton_is_not_yet_schema_valid(self):
        # new_manifest() is a construction aid, not a finished manifest --
        # it must not be mistakable for one until populated.
        skeleton = manifest.new_manifest(
            "SYNTHETIC-TEST-FIXTURE-0002",
            "synthetic-fixture-revision-02",
            rights_status="SYNTHETIC_TEST_FIXTURE_NO_REAL_DATA",
            privacy="SYNTHETIC_NON_PRIVATE",
            redistribution="NOT_APPLICABLE_SYNTHETIC",
        )
        with self.assertRaises(manifest.DatasetManifestError):
            manifest.validate_manifest(skeleton)


class DatasetManifestLoadTest(unittest.TestCase):
    def test_load_manifest_round_trips_the_golden_fixture(self):
        loaded = manifest.load_manifest(FIXTURE_PATH)
        self.assertEqual(loaded, _fixture())

    def test_load_manifest_rejects_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "not_json.json"
            bad.write_text("{not valid json", encoding="utf-8")
            with self.assertRaises(manifest.DatasetManifestError):
                manifest.load_manifest(bad)


class DatasetManifestHashVerificationTest(unittest.TestCase):
    def test_verify_file_hashes_accepts_matching_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            file_a = tmp_path / "a.bin"
            file_a.write_bytes(b"synthetic-fixture-bytes-a")
            doc = manifest.new_manifest(
                "SYNTHETIC-TEST-FIXTURE-0003",
                "synthetic-fixture-revision-03",
                rights_status="SYNTHETIC_TEST_FIXTURE_NO_REAL_DATA",
                privacy="SYNTHETIC_NON_PRIVATE",
                redistribution="NOT_APPLICABLE_SYNTHETIC",
            )
            doc["file_hashes"]["synthetic-file-a"] = manifest.sha256_of_file(file_a)
            manifest.verify_file_hashes(doc, {"synthetic-file-a": file_a})

    def test_verify_file_hashes_rejects_a_changed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            file_a = tmp_path / "a.bin"
            file_a.write_bytes(b"synthetic-fixture-bytes-a")
            doc = manifest.new_manifest(
                "SYNTHETIC-TEST-FIXTURE-0004",
                "synthetic-fixture-revision-04",
                rights_status="SYNTHETIC_TEST_FIXTURE_NO_REAL_DATA",
                privacy="SYNTHETIC_NON_PRIVATE",
                redistribution="NOT_APPLICABLE_SYNTHETIC",
            )
            doc["file_hashes"]["synthetic-file-a"] = manifest.sha256_of_file(file_a)
            # Mutate the file after it was hashed -- verify_file_hashes
            # must catch this, proving the manifest's immutability claim
            # is actually checked, not just asserted.
            file_a.write_bytes(b"tampered-bytes")
            with self.assertRaises(manifest.DatasetManifestError):
                manifest.verify_file_hashes(doc, {"synthetic-file-a": file_a})

    def test_verify_file_hashes_rejects_a_missing_file(self):
        doc = copy.deepcopy(_fixture())
        with self.assertRaises(manifest.DatasetManifestError):
            manifest.verify_file_hashes(doc, {})

    def test_iter_group_ids_used_in_splits(self):
        doc = _fixture()
        self.assertEqual(
            sorted(manifest.iter_group_ids_used_in_splits(doc)),
            ["synthetic-group-01", "synthetic-group-02"],
        )


if __name__ == "__main__":
    unittest.main()
