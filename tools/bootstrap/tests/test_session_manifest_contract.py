"""Executable acceptance tests for the owner-approved I-18 SessionManifest v1 contract."""

import copy
import json
import unittest
from pathlib import Path

import jsonschema


class SessionManifestContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[3]
        cls.schema = json.loads(
            (cls.root / "contracts/schemas/session_manifest_v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        cls.complete = cls._load_fixture("session_manifest_v1_complete_fixture.json")
        cls.incomplete = cls._load_fixture("session_manifest_v1_incomplete_fixture.json")
        cls.validator = jsonschema.Draft202012Validator(cls.schema)

    @classmethod
    def _load_fixture(cls, name):
        return json.loads(
            (cls.root / "contracts/fixtures" / name).read_text(encoding="utf-8")
        )

    def assert_invalid(self, document):
        with self.assertRaises(jsonschema.ValidationError):
            self.validator.validate(document)

    def test_schema_is_valid_draft_2020_12(self):
        jsonschema.Draft202012Validator.check_schema(self.schema)

    def test_complete_and_incomplete_golden_fixtures_validate(self):
        self.validator.validate(self.complete)
        self.validator.validate(self.incomplete)

    def test_every_top_level_contract_field_is_mandatory(self):
        for field in self.schema["required"]:
            with self.subTest(field=field):
                document = copy.deepcopy(self.complete)
                del document[field]
                self.assert_invalid(document)

    def test_tier_a_rejects_unknown_fields(self):
        document = copy.deepcopy(self.complete)
        document["legacy_complete"] = True
        self.assert_invalid(document)

    def test_complete_session_requires_at_least_one_chunk(self):
        document = copy.deepcopy(self.complete)
        document["chunks"] = []
        self.assert_invalid(document)

    def test_unsafe_chunk_paths_and_invalid_hashes_are_rejected(self):
        drive_absolute_path = "C:" + "/private/chunk.jsonl"
        for path in ("../escape.jsonl", "/absolute.jsonl", drive_absolute_path):
            with self.subTest(path=path):
                document = copy.deepcopy(self.complete)
                document["chunks"][0]["path"] = path
                self.assert_invalid(document)

        document = copy.deepcopy(self.complete)
        document["chunks"][0]["sha256"] = "not-a-sha256"
        self.assert_invalid(document)

    def test_legacy_complete_boolean_alone_cannot_enter_i18(self):
        legacy = {
            "session_id": "legacy-session",
            "complete": True,
            "chunks": [],
        }
        self.assert_invalid(legacy)

    def test_status_vocabulary_is_closed(self):
        document = copy.deepcopy(self.complete)
        document["status"] = "RECOVERED"
        self.assert_invalid(document)


if __name__ == "__main__":
    unittest.main()
