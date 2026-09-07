"""WP-10.2 (Issue #80): tests for tools/dataset/schema_allowlist.py.

Uses only synthetic allowlist documents constructed in-test -- never the
shipped template config's real intended purpose, and never a real IO-VNBD
schema name.
"""
from __future__ import annotations

import copy
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


allowlist_mod = _load_module("wp10_schema_allowlist", REPO_ROOT / "tools" / "dataset" / "schema_allowlist.py")


def _synthetic_active_document() -> dict:
    return {
        "schema_version": 1,
        "status": "ACTIVE",
        "allowlist": [
            "synthetic_schema_1",
            "synthetic_schema_2",
            "synthetic_schema_3",
            "synthetic_schema_4",
            "synthetic_schema_5",
            "synthetic_schema_6",
        ],
    }


class AllowlistConfigSchemaTest(unittest.TestCase):
    def test_config_schema_is_valid_draft_2020_12(self):
        import jsonschema

        jsonschema.Draft202012Validator.check_schema(allowlist_mod.load_allowlist_config_schema())

    def test_synthetic_active_document_validates(self):
        # Structural validity only -- exercised via load through a temp
        # file to keep parity with how the real loader is used.
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allowlist.json"
            path.write_text(json.dumps(_synthetic_active_document()), encoding="utf-8")
            loaded = allowlist_mod.load_allowlist_document(path)
            self.assertEqual(loaded, _synthetic_active_document())

    def test_wrong_item_count_is_rejected(self):
        import json
        import tempfile

        doc = copy.deepcopy(_synthetic_active_document())
        doc["allowlist"].pop()  # five entries: must be exactly six
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allowlist.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(allowlist_mod.SchemaAllowlistError):
                allowlist_mod.load_allowlist_document(path)

    def test_duplicate_entries_are_rejected(self):
        import json
        import tempfile

        doc = copy.deepcopy(_synthetic_active_document())
        doc["allowlist"][1] = doc["allowlist"][0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allowlist.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(allowlist_mod.SchemaAllowlistError):
                allowlist_mod.load_allowlist_document(path)

    def test_unknown_status_is_rejected(self):
        import json
        import tempfile

        doc = copy.deepcopy(_synthetic_active_document())
        doc["status"] = "APPROVED"  # not a recognized enum value
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allowlist.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(allowlist_mod.SchemaAllowlistError):
                allowlist_mod.load_allowlist_document(path)


class ShippedTemplateTest(unittest.TestCase):
    """The actual config/io_vnbd_schema_allowlist.json shipped by this PR
    must always be recognized as a template -- these tests fail loudly if
    someone edits it to claim ACTIVE without replacing the placeholders,
    which is exactly the mistake require_active_allowlist must catch.
    """

    def test_shipped_template_is_structurally_valid(self):
        allowlist_mod.load_allowlist_document(allowlist_mod.DEFAULT_ALLOWLIST_CONFIG_PATH)

    def test_shipped_template_is_recognized_as_a_template(self):
        document = allowlist_mod.load_allowlist_document(allowlist_mod.DEFAULT_ALLOWLIST_CONFIG_PATH)
        self.assertTrue(allowlist_mod.is_template_allowlist(document))

    def test_shipped_template_is_refused_for_enforcement(self):
        document = allowlist_mod.load_allowlist_document(allowlist_mod.DEFAULT_ALLOWLIST_CONFIG_PATH)
        with self.assertRaises(allowlist_mod.SchemaAllowlistError):
            allowlist_mod.require_active_allowlist(document)


class TemplateDetectionTest(unittest.TestCase):
    def test_active_status_with_placeholder_entries_is_still_a_template(self):
        # Guards against a shallow "just flip the status field" mistake:
        # a document claiming ACTIVE while every entry still carries the
        # placeholder prefix must still be treated as a template.
        doc = {
            "schema_version": 1,
            "status": "ACTIVE",
            "allowlist": [f"PENDING_SCHEMA_{i}_REPLACE_FROM_S0_AUDIT" for i in range(1, 7)],
        }
        self.assertTrue(allowlist_mod.is_template_allowlist(doc))
        with self.assertRaises(allowlist_mod.SchemaAllowlistError):
            allowlist_mod.require_active_allowlist(doc)

    def test_active_with_real_looking_entries_is_not_a_template(self):
        self.assertFalse(allowlist_mod.is_template_allowlist(_synthetic_active_document()))


class RequireActiveAllowlistTest(unittest.TestCase):
    def test_active_synthetic_document_returns_its_allowlist(self):
        result = allowlist_mod.require_active_allowlist(_synthetic_active_document())
        self.assertEqual(sorted(result), sorted(_synthetic_active_document()["allowlist"]))


class ClassifySchemasTest(unittest.TestCase):
    def test_classify_partitions_allowed_and_unknown(self):
        allowlist = ["a", "b", "c", "d", "e", "f"]
        allowed, unknown = allowlist_mod.classify_schemas(["a", "z", "c"], allowlist)
        self.assertEqual(allowed, ["a", "c"])
        self.assertEqual(unknown, ["z"])

    def test_classify_all_allowed(self):
        allowlist = ["a", "b"]
        allowed, unknown = allowlist_mod.classify_schemas(["a", "b"], allowlist)
        self.assertEqual(allowed, ["a", "b"])
        self.assertEqual(unknown, [])


class EnforceManifestAgainstAllowlistTest(unittest.TestCase):
    def test_manifest_with_only_allowed_schemas_passes(self):
        manifest_doc = {"schemas": ["synthetic_schema_1", "synthetic_schema_2"]}
        allowlist_mod.enforce_manifest_against_allowlist(manifest_doc, _synthetic_active_document())

    def test_manifest_with_unknown_schema_is_rejected(self):
        manifest_doc = {"schemas": ["synthetic_schema_1", "not_on_the_allowlist"]}
        with self.assertRaises(allowlist_mod.SchemaAllowlistError):
            allowlist_mod.enforce_manifest_against_allowlist(manifest_doc, _synthetic_active_document())

    def test_manifest_against_template_allowlist_is_rejected(self):
        # Even if the manifest's schemas happen to overlap the template's
        # placeholder text, a template allowlist can never be used to pass
        # enforcement -- require_active_allowlist must fire first.
        template = allowlist_mod.load_allowlist_document(allowlist_mod.DEFAULT_ALLOWLIST_CONFIG_PATH)
        manifest_doc = {"schemas": [template["allowlist"][0]]}
        with self.assertRaises(allowlist_mod.SchemaAllowlistError):
            allowlist_mod.enforce_manifest_against_allowlist(manifest_doc, template)


if __name__ == "__main__":
    unittest.main()
