"""WP-02.6 S1 acquisition fixture schema and round-trip verification."""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import unittest
from pathlib import Path

import jsonschema


class S1FixtureRoundTripTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[3]
        cls.fixture_path = (
            cls.root
            / "contracts/fixtures/s1_acquisition_round_trip_v1_fixture.json"
        )
        cls.raw_schema_path = (
            cls.root
            / "contracts/schemas/raw_sensor_sample_v1.schema.json"
        )
        cls.gnss_schema_path = (
            cls.root
            / "contracts/schemas/location_gnss_fix_v1.schema.json"
        )
        harness_path = (
            cls.root
            / "tools/acquisition/s1_fixture_roundtrip.py"
        )

        spec = importlib.util.spec_from_file_location(
            "s1_fixture_roundtrip",
            harness_path,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(
                f"cannot load S1 fixture harness from {harness_path}"
            )

        cls.harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.harness)
        cls.document = cls.harness.load_json(cls.fixture_path)

    def _copy(self):
        return copy.deepcopy(self.document)

    def assert_fixture_rejected(
        self,
        document,
        message_fragment=None,
    ):
        with self.assertRaises(
            self.harness.FixtureValidationError
        ) as context:
            self.harness.validate_document(document)

        if message_fragment:
            self.assertIn(
                message_fragment,
                str(context.exception),
            )

    def test_i01_and_i02_schemas_match_contract_v1_identity_and_required_keys(
        self,
    ):
        raw_schema = json.loads(
            self.raw_schema_path.read_text(encoding="utf-8")
        )
        gnss_schema = json.loads(
            self.gnss_schema_path.read_text(encoding="utf-8")
        )

        jsonschema.Draft202012Validator.check_schema(raw_schema)
        jsonschema.Draft202012Validator.check_schema(gnss_schema)

        self.assertEqual(
            raw_schema["$id"],
            (
                "https://sih26168.invalid/contracts/schemas/"
                "raw_sensor_sample_v1.schema.json"
            ),
        )
        self.assertEqual(
            gnss_schema["$id"],
            (
                "https://sih26168.invalid/contracts/schemas/"
                "location_gnss_fix_v1.schema.json"
            ),
        )
        self.assertTrue(
            raw_schema["additionalProperties"],
            "I-01 must remain Tier B",
        )
        self.assertTrue(
            gnss_schema["additionalProperties"],
            "I-02 must remain Tier B",
        )

        self.assertEqual(
            set(raw_schema["required"]),
            {
                "schema_version",
                "evidence_id",
                "session_id",
                "stream_id",
                "sequence",
                "source_timestamp_ns",
                "arrival_elapsed_realtime_ns",
                "sensor_type",
                "values",
                "accuracy",
                "source_metadata",
            },
        )
        self.assertEqual(
            set(gnss_schema["required"]),
            {
                "schema_version",
                "evidence_id",
                "provider",
                "source_timestamp_ns",
                "arrival_elapsed_realtime_ns",
                "lat_deg",
                "lon_deg",
                "alt_m",
                "hacc_m",
                "vacc_m",
                "speed_mps",
                "speed_acc_mps",
                "bearing_deg",
                "bearing_acc_deg",
                "is_mock",
                "field_mask",
            },
        )

    def test_fixture_validates_and_round_trips_without_fidelity_loss(
        self,
    ):
        first = self.harness.validate_document(self._copy())
        second = self.harness.validate_document(self._copy())

        self.assertEqual(first, second)
        self.assertEqual(
            first["fixture_id"],
            "s1-acquisition-round-trip-v1",
        )
        self.assertEqual(first["record_count"], 6)
        self.assertEqual(first["raw_sensor_sample_count"], 4)
        self.assertEqual(first["location_gnss_fix_count"], 2)
        self.assertRegex(first["sha256"], r"^[0-9a-f]{64}$")

        canonical = self.harness.canonical_json_bytes(
            self.document
        )
        restored = json.loads(canonical.decode("utf-8"))
        self.assertEqual(restored, self.document)

    def test_fixture_is_explicitly_synthetic_and_contains_no_private_route(
        self,
    ):
        self.assertEqual(
            self.document["classification"],
            "SYNTHETIC_PUBLIC_TEST_ONLY",
        )
        self.assertIn(
            "synthetic equatorial",
            self.document["description"].lower(),
        )

        for record in self.document["records"]:
            with self.subTest(
                evidence=record["provenance"]["evidence_id"]
            ):
                self.assertTrue(
                    record["provenance"]["synthetic"]
                )
                self.assertEqual(
                    record["provenance"]["provenance_type"],
                    "DETERMINISTIC_REPLAY",
                )
                self.assertEqual(
                    record["timestamp"]["clock_id"],
                    "CLOCK_BOOTTIME",
                )

                if record["payload_type"] == "LocationGnssFix":
                    self.assertEqual(
                        record["payload"]["lat_deg"],
                        0.0,
                    )
                    self.assertEqual(
                        record["payload"]["lon_deg"],
                        0.0,
                    )

    def test_raw_axes_accuracy_and_sensor_hardware_types_survive_round_trip(
        self,
    ):
        expected_android_types = {
            "ACCELEROMETER": 1,
            "GYROSCOPE": 4,
        }

        for record in self.document["records"]:
            if record["payload_type"] != "RawSensorSample":
                continue

            with self.subTest(
                evidence=record["payload"]["evidence_id"]
            ):
                before = copy.deepcopy(record["payload"])
                encoded = self.harness.canonical_json_bytes(
                    record
                )
                after = json.loads(
                    encoded.decode("utf-8")
                )["payload"]

                self.assertEqual(after, before)
                self.assertEqual(len(after["values"]), 3)
                self.assertTrue(
                    all(
                        math.isfinite(value)
                        for value in after["values"]
                    )
                )
                self.assertIn(
                    after["accuracy"],
                    range(4),
                )
                self.assertEqual(
                    after["source_metadata"][
                        "android_sensor_type"
                    ],
                    expected_android_types[
                        after["sensor_type"]
                    ],
                )

    def test_missing_required_i01_field_is_rejected(self):
        document = self._copy()
        del document["records"][0]["payload"][
            "source_metadata"
        ]
        self.assert_fixture_rejected(
            document,
            "source_metadata",
        )

    def test_unknown_sensor_hardware_type_is_rejected(self):
        document = self._copy()
        document["records"][0]["payload"][
            "sensor_type"
        ] = "ROTATION_VECTOR"
        self.assert_fixture_rejected(
            document,
            "ROTATION_VECTOR",
        )

    def test_sensor_type_and_android_hardware_type_mismatch_is_rejected(
        self,
    ):
        document = self._copy()
        document["records"][0]["payload"][
            "source_metadata"
        ]["android_sensor_type"] = 4
        self.assert_fixture_rejected(
            document,
            "Android hardware type",
        )

    def test_non_finite_sensor_value_is_rejected(self):
        document = self._copy()
        document["records"][0]["payload"][
            "values"
        ][0] = float("nan")
        self.assert_fixture_rejected(
            document,
            "finite",
        )

    def test_envelope_and_payload_timestamp_mismatch_is_rejected(
        self,
    ):
        document = self._copy()
        document["records"][0]["timestamp"][
            "source_timestamp_ns"
        ] += 1
        self.assert_fixture_rejected(
            document,
            "source timestamps differ",
        )

    def test_callback_arrival_before_source_timestamp_is_rejected(
        self,
    ):
        document = self._copy()
        record = document["records"][0]
        arrival = (
            record["payload"]["source_timestamp_ns"] - 1
        )
        record["payload"][
            "arrival_elapsed_realtime_ns"
        ] = arrival
        record["timestamp"][
            "arrival_elapsed_realtime_ns"
        ] = arrival

        self.assert_fixture_rejected(
            document,
            "callback arrival precedes",
        )

    def test_non_monotonic_i01_sequence_is_rejected(self):
        document = self._copy()
        document["records"][1]["payload"]["sequence"] = 0
        self.assert_fixture_rejected(
            document,
            "sequence is not strictly increasing",
        )

    def test_non_monotonic_i01_source_time_is_rejected(
        self,
    ):
        document = self._copy()
        record = document["records"][1]
        prior_timestamp = document["records"][0][
            "payload"
        ]["source_timestamp_ns"]

        record["payload"][
            "source_timestamp_ns"
        ] = prior_timestamp
        record["timestamp"][
            "source_timestamp_ns"
        ] = prior_timestamp
        record["timestamp"]["epoch_ns"] = prior_timestamp

        self.assert_fixture_rejected(
            document,
            "source timestamp is not strictly increasing",
        )

    def test_non_monotonic_i02_provider_time_is_rejected(
        self,
    ):
        document = self._copy()
        first = document["records"][4]["payload"][
            "source_timestamp_ns"
        ]
        record = document["records"][5]

        record["payload"]["source_timestamp_ns"] = first
        record["timestamp"]["source_timestamp_ns"] = first
        record["timestamp"]["epoch_ns"] = first

        self.assert_fixture_rejected(
            document,
            "I-02 source timestamp is not strictly increasing",
        )

    def test_provenance_evidence_mismatch_is_rejected(
        self,
    ):
        document = self._copy()
        document["records"][0]["provenance"][
            "evidence_id"
        ] = "different-evidence-id"
        self.assert_fixture_rejected(
            document,
            "evidence IDs differ",
        )

    def test_duplicate_evidence_id_is_rejected(self):
        document = self._copy()
        duplicate = document["records"][0][
            "provenance"
        ]["evidence_id"]

        document["records"][1]["provenance"][
            "evidence_id"
        ] = duplicate
        document["records"][1]["payload"][
            "evidence_id"
        ] = duplicate

        self.assert_fixture_rejected(
            document,
            "duplicate evidence_id",
        )

    def test_synthetic_fixture_cannot_claim_live_provenance(
        self,
    ):
        document = self._copy()
        document["records"][0]["provenance"][
            "provenance_type"
        ] = "LIVE_DEVICE"
        self.assert_fixture_rejected(
            document,
            "DETERMINISTIC_REPLAY",
        )

    def test_gnss_field_mask_must_match_nullable_values(
        self,
    ):
        document = self._copy()
        gnss = document["records"][5]["payload"]
        gnss["field_mask"].append("speed_mps")

        self.assertIsNone(gnss["speed_mps"])
        self.assert_fixture_rejected(
            document,
            "field_mask and nullable value disagree",
        )

    def test_invalid_gnss_range_and_accuracy_are_rejected_by_schema(
        self,
    ):
        invalid_values = (
            ("lat_deg", 90.1),
            ("lon_deg", -180.1),
            ("hacc_m", 0.01),
        )

        for field, value in invalid_values:
            with self.subTest(field=field):
                document = self._copy()
                document["records"][4]["payload"][
                    field
                ] = value
                self.assert_fixture_rejected(
                    document,
                    field,
                )


if __name__ == "__main__":
    unittest.main()