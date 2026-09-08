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
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "dataset_manifest_v2_fixture.json"


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
            "DatasetManifestV2 is a Tier A contract (I-20): additionalProperties must be false",
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

    def test_file_hashes_identifier_rejects_unsafe_forms(self):
        # file_hashes keys must be canonical, archive-relative identifiers
        # -- never something that could carry a private machine path (an
        # absolute path, a Windows drive path, a backslash separator) or
        # escape the archive root via a '..' traversal segment -- into a
        # manifest that is otherwise safe to commit to Git.
        valid_hash = next(iter(_fixture()["file_hashes"].values()))
        # The Windows-style examples are built by concatenation, not as a
        # single contiguous literal, so this test file's own source text
        # never contains a drive-letter+':'+slash sequence -- the same
        # pattern ci/verify_repository.py's `forbidden` check flags
        # anywhere in the repository as a local/absolute path leak.
        _drive = "C"
        unsafe_identifiers = [
            "/etc/passwd",
            _drive + ":/example/subdir/file.bin",
            _drive + ":\\example\\subdir\\file.bin",
            "\\\\server\\share\\file.bin",
            "../escape.bin",
            "nested/../escape.bin",
            "..",
            "",
        ]
        for identifier in unsafe_identifiers:
            with self.subTest(identifier=identifier):
                doc = copy.deepcopy(_fixture())
                doc["file_hashes"] = {identifier: valid_hash}
                with self.assertRaises(manifest.DatasetManifestError):
                    manifest.validate_manifest(doc)

    def test_file_hashes_identifier_accepts_nested_relative_path(self):
        # The propertyNames guard must not be so strict that it rejects
        # legitimate multi-segment, forward-slash-separated identifiers.
        valid_hash = next(iter(_fixture()["file_hashes"].values()))
        doc = copy.deepcopy(_fixture())
        doc["file_hashes"] = {"session-01/frame-0001.bin": valid_hash}
        manifest.validate_manifest(doc)  # must not raise

    def test_file_group_ids_identifier_rejects_unsafe_forms(self):
        # file_group_ids keys are file identifiers too (they mirror
        # file_hashes) and must be held to the same canonical-identifier
        # guard -- an absolute path here is exactly as unsafe as one in
        # file_hashes.
        doc = copy.deepcopy(_fixture())
        _drive = "C"
        doc["file_group_ids"] = {_drive + ":/example/file.bin": "synthetic-group-01"}
        with self.assertRaises(manifest.DatasetManifestError):
            manifest.validate_manifest(doc)


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
        # verify_file_hashes now validates the whole document first (see
        # test_verify_file_hashes_rejects_an_invalid_manifest below), so
        # this must be a fully schema-valid manifest -- built from the
        # golden fixture with file_hashes replaced by exactly the one
        # identifier this test supplies an on-disk file for, since the
        # supplied and recorded identifier sets must now match exactly.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            file_a = tmp_path / "a.bin"
            file_a.write_bytes(b"synthetic-fixture-bytes-a")
            doc = copy.deepcopy(_fixture())
            doc["file_hashes"] = {"synthetic-file-a": manifest.sha256_of_file(file_a)}
            manifest.verify_file_hashes(doc, {"synthetic-file-a": file_a})

    def test_verify_file_hashes_rejects_a_changed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            file_a = tmp_path / "a.bin"
            file_a.write_bytes(b"synthetic-fixture-bytes-a")
            doc = copy.deepcopy(_fixture())
            doc["file_hashes"] = {"synthetic-file-a": manifest.sha256_of_file(file_a)}
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

    def test_verify_file_hashes_rejects_an_invalid_manifest(self):
        # A document that fails schema validation (here: empty, missing
        # every required field) must never be able to "pass" verification
        # simply because it has no file_hashes entries left to check.
        with self.assertRaises(manifest.DatasetManifestError):
            manifest.verify_file_hashes({}, {})

    def test_verify_file_hashes_rejects_an_unexpected_supplied_identifier(self):
        # The supplied identifier set must match the manifest's recorded
        # file_hashes exactly -- an extra identifier the manifest never
        # claimed is just as much an inconsistency as a missing one, even
        # when every identifier the manifest *does* record checks out.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            file_a = tmp_path / "a.bin"
            file_a.write_bytes(b"synthetic-fixture-bytes-a")
            doc = copy.deepcopy(_fixture())
            doc["file_hashes"] = {"synthetic-file-a": manifest.sha256_of_file(file_a)}
            with self.assertRaises(manifest.DatasetManifestError):
                manifest.verify_file_hashes(
                    doc, {"synthetic-file-a": file_a, "unexpected-identifier": file_a}
                )

    def test_iter_group_ids_used_in_splits(self):
        doc = _fixture()
        self.assertEqual(
            sorted(manifest.iter_group_ids_used_in_splits(doc)),
            ["synthetic-group-01", "synthetic-group-02"],
        )


if __name__ == "__main__":
    unittest.main()
