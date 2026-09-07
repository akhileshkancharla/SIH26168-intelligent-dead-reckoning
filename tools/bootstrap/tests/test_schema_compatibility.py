"""WP-01.6 (Issue #30): machine-enforced schema compatibility tests and
synthetic golden fixtures.

Enforces the contract evolution policy from
contracts/INTERFACE_SCHEMA_PLAN.md section 2:
  - 2.2 Additive Optional Fields: an unrecognized/novel field must not
    break validation of a Tier B (additionalProperties: true) schema.
  - 2.2 Adding a mandatory field is a breaking change: removing any
    currently-required field from a golden fixture must fail validation,
    proving the schema actually enforces what it declares required.
  - 2.3 Tier A vs Tier B unknown-field handling: every common schema this
    repository ships today is Tier B (additionalProperties: true); this
    suite records that fact per-schema so a future Tier A schema is a
    deliberate, reviewed choice rather than a silent default.

Also exercises golden fixtures round-tripping through the placed Python
contract bindings (tools/contracts/sih26168_contracts), tying the
schemas, fixtures, and generated bindings together.
"""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

import jsonschema
from referencing import Registry, Resource


class SchemaCompatibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[3]
        cls.schemas_dir = cls.root / "contracts/schemas/common"
        cls.fixtures_dir = cls.root / "contracts/fixtures"
        cls.python_contracts_dir = cls.root / "tools/contracts/sih26168_contracts"

        cls.timestamp_schema = cls._load_schema("timestamp_v1.schema.json")
        cls.provenance_schema = cls._load_schema("provenance_v1.schema.json")
        cls.envelope_schema = cls._load_schema("evidence_envelope_v1.schema.json")

        cls.registry = (
            Registry()
            .with_resource("timestamp_v1.schema.json", Resource.from_contents(cls.timestamp_schema))
            .with_resource("provenance_v1.schema.json", Resource.from_contents(cls.provenance_schema))
            .with_resource(cls.timestamp_schema["$id"], Resource.from_contents(cls.timestamp_schema))
            .with_resource(cls.provenance_schema["$id"], Resource.from_contents(cls.provenance_schema))
        )

        # (schema, fixture filename, needs $ref registry) for every golden
        # fixture this suite knows about.
        cls.schema_fixture_pairs = [
            (cls.timestamp_schema, "timestamp_v1_fixture.json", False),
            (cls.timestamp_schema, "timestamp_v1_minimal_fixture.json", False),
            (cls.provenance_schema, "provenance_v1_fixture.json", False),
            (cls.provenance_schema, "provenance_v1_minimal_fixture.json", False),
            (cls.envelope_schema, "common_envelope_v1_fixture.json", True),
        ]

    @classmethod
    def _load_schema(cls, name):
        return json.loads((cls.schemas_dir / name).read_text(encoding="utf-8"))

    def _load_fixture(self, name):
        path = self.fixtures_dir / name
        self.assertTrue(path.is_file(), f"{name} must exist under contracts/fixtures/")
        return json.loads(path.read_text(encoding="utf-8"))

    def _validator_for(self, schema, needs_registry):
        if needs_registry:
            return jsonschema.Draft202012Validator(schema, registry=self.registry)
        return jsonschema.Draft202012Validator(schema)

    # -- Meta-schema validity -------------------------------------------------

    def test_common_schemas_are_valid_draft_2020_12(self):
        for schema in (self.timestamp_schema, self.provenance_schema, self.envelope_schema):
            jsonschema.Draft202012Validator.check_schema(schema)

    # -- Golden fixtures validate -------------------------------------------

    def test_golden_fixtures_validate_against_their_schema(self):
        for schema, fixture_name, needs_registry in self.schema_fixture_pairs:
            with self.subTest(fixture=fixture_name):
                fixture = self._load_fixture(fixture_name)
                validator = self._validator_for(schema, needs_registry)
                validator.validate(fixture)

    # -- 2.2 Additive optional fields: forward compatibility -----------------

    def test_unrecognized_field_does_not_break_tier_b_validation(self):
        for schema, fixture_name, needs_registry in self.schema_fixture_pairs:
            with self.subTest(fixture=fixture_name):
                self.assertTrue(
                    schema.get("additionalProperties"),
                    f"{fixture_name}'s schema must be Tier B for this additive-compatibility guarantee to apply",
                )
                fixture = copy.deepcopy(self._load_fixture(fixture_name))
                fixture["x_future_additive_field_not_yet_defined"] = True
                validator = self._validator_for(schema, needs_registry)
                validator.validate(fixture)  # must not raise

    # -- 2.2 Adding a mandatory field is a breaking change: required fields
    #    must actually be enforced, not silently optional -------------------

    def test_removing_a_required_field_is_rejected(self):
        for schema, fixture_name, needs_registry in self.schema_fixture_pairs:
            required = schema.get("required", [])
            for field in required:
                with self.subTest(fixture=fixture_name, missing=field):
                    fixture = copy.deepcopy(self._load_fixture(fixture_name))
                    if field not in fixture:
                        continue  # fixture didn't carry this optional-but-required-elsewhere combination
                    del fixture[field]
                    validator = self._validator_for(schema, needs_registry)
                    with self.assertRaises(
                        jsonschema.ValidationError,
                        msg=f"removing required field {field!r} from {fixture_name} should fail validation",
                    ):
                        validator.validate(fixture)

    # -- Fixtures round-trip through the placed Python bindings --------------

    def _load_placed_python_models(self):
        enums_spec = importlib.util.spec_from_file_location(
            "sih26168_contracts.enums", self.python_contracts_dir / "enums.py"
        )
        enums_mod = importlib.util.module_from_spec(enums_spec)
        sys.modules["sih26168_contracts.enums"] = enums_mod
        enums_spec.loader.exec_module(enums_mod)

        models_spec = importlib.util.spec_from_file_location(
            "sih26168_contracts.models", self.python_contracts_dir / "models.py"
        )
        models_mod = importlib.util.module_from_spec(models_spec)
        sys.modules["sih26168_contracts.models"] = models_mod
        models_spec.loader.exec_module(models_mod)
        return models_mod

    def test_timestamp_fixtures_round_trip_through_generated_bindings(self):
        # "Full" fixtures carry every field, so from_dict/to_dict must
        # reproduce them exactly. "Minimal" fixtures omit optional fields,
        # so to_dict() legitimately adds their defaults back in (that's the
        # point of a default); the correct round-trip property there is
        # object-level idempotency: parsing what you just serialized gives
        # back an equal object, not a byte-identical dict.
        models = self._load_placed_python_models()
        full = self._load_fixture("timestamp_v1_fixture.json")
        self.assertEqual(models.TimestampV1.from_dict(full).to_dict(), full)

        minimal = self._load_fixture("timestamp_v1_minimal_fixture.json")
        ts = models.TimestampV1.from_dict(minimal)
        self.assertEqual(models.TimestampV1.from_dict(ts.to_dict()), ts)

    def test_provenance_fixtures_round_trip_through_generated_bindings(self):
        models = self._load_placed_python_models()
        full = self._load_fixture("provenance_v1_fixture.json")
        self.assertEqual(models.ProvenanceV1.from_dict(full).to_dict(), full)

        minimal = self._load_fixture("provenance_v1_minimal_fixture.json")
        prov = models.ProvenanceV1.from_dict(minimal)
        self.assertEqual(models.ProvenanceV1.from_dict(prov.to_dict()), prov)

    def test_envelope_fixture_round_trips_through_generated_bindings(self):
        models = self._load_placed_python_models()
        fixture = self._load_fixture("common_envelope_v1_fixture.json")
        envelope = models.EvidenceEnvelopeV1.from_dict(fixture)
        self.assertEqual(envelope.to_dict(), fixture)


if __name__ == "__main__":
    unittest.main()
