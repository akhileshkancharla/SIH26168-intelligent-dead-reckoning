"""Synthetic tests for the WP-11.3 frozen GNSS-blackout protocol."""
from __future__ import annotations

from dataclasses import replace
import copy
import json
from pathlib import Path
import unittest

from tools.training.blackout_masking import (
    APPROVED_GNSS_FEATURES,
    BlackoutMaskError,
    FrozenBlackoutProtocol,
    assert_no_withheld_features,
    freeze_protocol,
    mask_records,
    verify_protocol_identity,
)


def protocol_document() -> dict:
    return {
        "schema_version": 1,
        "protocol_id": "synthetic-blackout-protocol-v1",
        "clock_id": "synthetic.monotonic_ns",
        "status": "FROZEN",
        "intervals": [
            {
                "event_id": "synthetic-event-1",
                "mask_id": "synthetic-mask-1",
                "start_ns": 100,
                "end_ns": 200,
                "type": "SOFTWARE_SIMULATED",
                "reason": "synthetic tunnel interval",
                "hidden_fields": ["gnss.speed_mps", "gnss.lat_deg", "gnss.lon_deg"],
            }
        ],
    }


def record(record_id: str, epoch_ns: int, speed: float) -> dict:
    return {
        "record_id": record_id,
        "epoch_ns": epoch_ns,
        "clock_id": "synthetic.monotonic_ns",
        "features": {
            "imu.accel.x": 1.0,
            "gnss.lat_deg": 12.34,
            "gnss.lon_deg": 56.78,
            "gnss.speed_mps": speed,
        },
    }


class FrozenProtocolTests(unittest.TestCase):
    def test_approved_fields_match_i02_measurement_contract(self):
        schema_path = (
            Path(__file__).resolve().parents[3]
            / "contracts"
            / "schemas"
            / "location_gnss_fix_v1.schema.json"
        )
        properties = set(json.loads(schema_path.read_text(encoding="utf-8"))["properties"])
        non_measurement_fields = {
            "schema_version",
            "evidence_id",
            "provider",
            "source_timestamp_ns",
            "arrival_elapsed_realtime_ns",
            "is_mock",
            "field_mask",
        }
        expected = {f"gnss.{name}" for name in properties - non_measurement_fields}
        self.assertEqual(APPROVED_GNSS_FEATURES, expected)

    def test_identity_is_deterministic_across_interval_and_field_order(self):
        document = protocol_document()
        second = copy.deepcopy(document["intervals"][0])
        second.update(
            event_id="synthetic-event-2",
            mask_id="synthetic-mask-2",
            start_ns=300,
            end_ns=400,
        )
        document["intervals"].append(second)
        reordered = copy.deepcopy(document)
        reordered["intervals"].reverse()
        for interval in reordered["intervals"]:
            interval["hidden_fields"].reverse()

        first = freeze_protocol(document)
        again = freeze_protocol(reordered)
        self.assertEqual(first.sha256, again.sha256)
        self.assertEqual(first.intervals, again.intervals)
        verify_protocol_identity(first, first.sha256.upper())

    def test_rejects_unfrozen_malformed_or_ambiguous_protocols(self):
        mutations = []
        for key, value in (
            ("status", "DRAFT"),
            ("schema_version", 2),
            ("clock_id", ""),
            ("intervals", []),
        ):
            changed = protocol_document()
            changed[key] = value
            mutations.append(changed)

        invalid_interval_patches = (
            {"start_ns": 200},
            {"end_ns": 100},
            {"start_ns": True},
            {"type": "NATURAL"},
            {"hidden_fields": []},
            {"hidden_fields": ["gnss.lat_deg", "gnss.lat_deg"]},
        )
        for patch in invalid_interval_patches:
            changed = protocol_document()
            changed["intervals"][0].update(patch)
            mutations.append(changed)

        for changed in mutations:
            with self.subTest(changed=changed):
                with self.assertRaises(BlackoutMaskError):
                    freeze_protocol(changed)

        boolean_version = protocol_document()
        boolean_version["schema_version"] = True
        with self.assertRaises(BlackoutMaskError):
            freeze_protocol(boolean_version)

    def test_rejects_overlap_and_duplicate_identity(self):
        for patch in (
            {"event_id": "synthetic-event-1", "mask_id": "synthetic-mask-2", "start_ns": 200, "end_ns": 300},
            {"event_id": "synthetic-event-2", "mask_id": "synthetic-mask-1", "start_ns": 200, "end_ns": 300},
            {"event_id": "synthetic-event-2", "mask_id": "synthetic-mask-2", "start_ns": 199, "end_ns": 300},
        ):
            changed = protocol_document()
            second = copy.deepcopy(changed["intervals"][0])
            second.update(patch)
            changed["intervals"].append(second)
            with self.subTest(patch=patch):
                with self.assertRaises(BlackoutMaskError):
                    freeze_protocol(changed)

    def test_rejects_non_gnss_hidden_fields(self):
        for hidden_field in (
            "imu.accel.x",
            "label.residual_m",
            "target",
            "gnss.unknown",
            "lat_deg",
        ):
            changed = protocol_document()
            changed["intervals"][0]["hidden_fields"] = [hidden_field]
            with self.subTest(hidden_field=hidden_field):
                with self.assertRaisesRegex(BlackoutMaskError, "approved I-02 GNSS"):
                    freeze_protocol(changed)

    def test_accepts_every_approved_i02_measurement_field(self):
        approved_fields = (
            "gnss.lat_deg",
            "gnss.lon_deg",
            "gnss.alt_m",
            "gnss.hacc_m",
            "gnss.vacc_m",
            "gnss.speed_mps",
            "gnss.speed_acc_mps",
            "gnss.bearing_deg",
            "gnss.bearing_acc_deg",
        )
        changed = protocol_document()
        changed["intervals"][0]["hidden_fields"] = list(approved_fields)
        protocol = freeze_protocol(changed)
        self.assertEqual(protocol.intervals[0].hidden_fields, tuple(sorted(approved_fields)))

    def test_rejects_protocol_hash_mismatch(self):
        protocol = freeze_protocol(protocol_document())
        with self.assertRaises(BlackoutMaskError):
            verify_protocol_identity(protocol, "0" * 64)
        for malformed in ("short", "z" * 64):
            with self.assertRaises(BlackoutMaskError):
                verify_protocol_identity(protocol, malformed)

    def test_rejects_manually_forged_protocol_object(self):
        protocol = freeze_protocol(protocol_document())
        forged = FrozenBlackoutProtocol(
            protocol_id=protocol.protocol_id,
            clock_id=protocol.clock_id,
            intervals=protocol.intervals,
            sha256="0" * 64,
        )
        with self.assertRaises(BlackoutMaskError):
            mask_records([record("sample", 100, 1.0)], forged)


class MaskingTests(unittest.TestCase):
    def setUp(self):
        self.protocol = freeze_protocol(protocol_document())

    def test_half_open_interval_hides_gnss_but_preserves_reference(self):
        source = [
            record("before", 99, 1.0),
            record("at-start", 100, 2.0),
            record("inside", 150, 3.0),
            record("at-end", 200, 4.0),
        ]
        original = copy.deepcopy(source)
        result = mask_records(source, self.protocol, expected_protocol_sha256=self.protocol.sha256)

        self.assertEqual(source, original, "masking must not mutate raw/source evidence")
        self.assertEqual(set(result.records[0].inference_features), set(source[0]["features"]))
        self.assertEqual(set(result.records[3].inference_features), set(source[3]["features"]))
        for masked in result.records[1:3]:
            self.assertEqual(masked.inference_features, {"imu.accel.x": 1.0})
            self.assertEqual(
                set(masked.reference_features),
                {"gnss.lat_deg", "gnss.lon_deg", "gnss.speed_mps"},
            )
            self.assertEqual(masked.active_mask_id, "synthetic-mask-1")
        self.assertEqual([event.record_id for event in result.audit_events], ["at-start", "inside"])

    def test_future_and_withheld_gnss_canary_never_reaches_inference(self):
        source = [record("blackout-a", 100, 111.0), record("blackout-b", 199, 999.0)]
        result = mask_records(source, self.protocol)
        for masked in result.records:
            serialized_inference = repr(dict(masked.inference_features))
            self.assertNotIn("gnss.", serialized_inference)
            self.assertNotIn("111.0", serialized_inference)
            self.assertNotIn("999.0", serialized_inference)
        assert_no_withheld_features(result, self.protocol)

    def test_missing_hidden_field_is_not_synthesized_or_filled(self):
        source = record("partial", 150, 3.0)
        del source["features"]["gnss.speed_mps"]
        result = mask_records([source], self.protocol)
        self.assertNotIn("gnss.speed_mps", result.records[0].reference_features)
        self.assertEqual(result.audit_events[0].hidden_fields, ("gnss.lat_deg", "gnss.lon_deg"))

    def test_outputs_are_immutable_views(self):
        result = mask_records([record("masked", 150, 3.0)], self.protocol)
        with self.assertRaises(TypeError):
            result.records[0].inference_features["gnss.speed_mps"] = 3.0

    def test_rejects_clock_order_identity_and_shape_failures(self):
        valid = record("valid", 100, 1.0)
        cases = []

        wrong_clock = copy.deepcopy(valid)
        wrong_clock["clock_id"] = "utc"
        cases.append([wrong_clock])

        duplicate_id = [copy.deepcopy(valid), record("valid", 101, 2.0)]
        cases.append(duplicate_id)

        not_increasing = [record("later", 101, 1.0), record("earlier", 100, 2.0)]
        cases.append(not_increasing)

        extra_field = copy.deepcopy(valid)
        extra_field["unexpected"] = True
        cases.append([extra_field])

        nonfinite = copy.deepcopy(valid)
        nonfinite["features"]["imu.accel.x"] = float("nan")
        cases.append([nonfinite])

        for records in cases:
            with self.subTest(records=records):
                with self.assertRaises(BlackoutMaskError):
                    mask_records(records, self.protocol)

        with self.assertRaises(BlackoutMaskError):
            mask_records([], self.protocol)

    def test_defense_in_depth_detects_tampered_result(self):
        result = mask_records([record("masked", 150, 3.0)], self.protocol)
        tampered_record = replace(
            result.records[0],
            inference_features={"imu.accel.x": 1.0, "gnss.speed_mps": 3.0},
        )
        tampered = replace(result, records=(tampered_record,))
        with self.assertRaises(BlackoutMaskError):
            assert_no_withheld_features(tampered, self.protocol)


if __name__ == "__main__":
    unittest.main()
