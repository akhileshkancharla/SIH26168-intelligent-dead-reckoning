"""WP-10.5 (Issue #83): tests for tools/dataset/feature_firewall.py.

Uses synthetic names for malformed-input coverage and exact structural IDs from
the accepted sanitized audit for the shipped configuration.
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


firewall_mod = _load_module("wp10_feature_firewall", REPO_ROOT / "tools" / "dataset" / "feature_firewall.py")


def _synthetic_active_document() -> dict:
    return {
        "schema_version": 1,
        "status": "ACTIVE",
        "runtime_allowed_features": [
            "synthetic_feature_accel_x",
            "synthetic_feature_accel_y",
            "synthetic_feature_gnss_speed",
        ],
        "forbidden_labels": [
            "synthetic_label_can_speed",
            "synthetic_label_reference_position",
        ],
    }


class FirewallConfigSchemaTest(unittest.TestCase):
    def test_config_schema_is_valid_draft_2020_12(self):
        import jsonschema

        jsonschema.Draft202012Validator.check_schema(firewall_mod.load_firewall_config_schema())

    def test_synthetic_active_document_validates(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firewall.json"
            path.write_text(json.dumps(_synthetic_active_document()), encoding="utf-8")
            loaded = firewall_mod.load_firewall_document(path)
            self.assertEqual(loaded, _synthetic_active_document())

    def test_empty_runtime_allowed_features_is_rejected(self):
        import json
        import tempfile

        doc = copy.deepcopy(_synthetic_active_document())
        doc["runtime_allowed_features"] = []
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firewall.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(firewall_mod.FeatureFirewallError):
                firewall_mod.load_firewall_document(path)

    def test_empty_forbidden_labels_is_rejected(self):
        import json
        import tempfile

        doc = copy.deepcopy(_synthetic_active_document())
        doc["forbidden_labels"] = []
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firewall.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(firewall_mod.FeatureFirewallError):
                firewall_mod.load_firewall_document(path)

    def test_duplicate_entries_within_a_list_are_rejected(self):
        import json
        import tempfile

        doc = copy.deepcopy(_synthetic_active_document())
        doc["runtime_allowed_features"][1] = doc["runtime_allowed_features"][0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firewall.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(firewall_mod.FeatureFirewallError):
                firewall_mod.load_firewall_document(path)

    def test_unknown_status_is_rejected(self):
        import json
        import tempfile

        doc = copy.deepcopy(_synthetic_active_document())
        doc["status"] = "APPROVED"  # not a recognized enum value
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firewall.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(firewall_mod.FeatureFirewallError):
                firewall_mod.load_firewall_document(path)

    def test_name_present_in_both_lists_is_rejected(self):
        import json
        import tempfile

        doc = copy.deepcopy(_synthetic_active_document())
        doc["forbidden_labels"].append(doc["runtime_allowed_features"][0])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firewall.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(firewall_mod.FeatureFirewallError):
                firewall_mod.load_firewall_document(path)


class ShippedFirewallTest(unittest.TestCase):
    EXPECTED_RUNTIME = [
        "imu.accel.x", "imu.accel.y", "imu.accel.z",
        "imu.gyro.x", "imu.gyro.y", "imu.gyro.z",
        "imu.dt", "imu.gap_mask", "imu.valid_mask",
    ]
    EXPECTED_FORBIDDEN = [
        "V29_MAIN.no_of_gps_satellites_available", "V29_MAIN.time_since_start_of_day",
        "V29_MAIN.latitude", "V29_MAIN.longitude", "V29_MAIN.velocity",
        "V29_MAIN.heading", "V29_MAIN.height", "V29_MAIN.vertical_velocity",
        "V29_MAIN.sample_period", "V29_MAIN.steering_angle",
        "V29_MAIN.wheel_speed_front_left", "V29_MAIN.wheel_speed_front_right",
        "V29_MAIN.wheel_speed_rear_left", "V29_MAIN.wheel_speed_rear_right",
        "V29_MAIN.yaw_rate", "V29_MAIN.indicated_vehicle_speed",
        "V29_MAIN.indicated_longitudinal_acceleration",
        "V29_MAIN.indicated_lateral_acceleration", "V29_MAIN.handbrake",
        "V29_MAIN.gear_requested", "V29_MAIN.gear", "V29_MAIN.engine_speed",
        "V29_MAIN.coolant_temperature", "V29_MAIN.clutch_position",
        "V29_MAIN.brake_pressure", "V29_MAIN.brake_position",
        "V29_MAIN.battery_voltage", "V29_MAIN.air_temperature",
        "V29_MAIN.accelerator_pedal_position",
    ]

    def test_shipped_firewall_is_structurally_valid(self):
        firewall_mod.load_firewall_document(firewall_mod.DEFAULT_FIREWALL_CONFIG_PATH)

    def test_shipped_firewall_has_exact_audited_values(self):
        document = firewall_mod.load_firewall_document(firewall_mod.DEFAULT_FIREWALL_CONFIG_PATH)
        self.assertEqual(document["status"], "ACTIVE")
        self.assertEqual(document["runtime_allowed_features"], self.EXPECTED_RUNTIME)
        self.assertEqual(document["forbidden_labels"], self.EXPECTED_FORBIDDEN)
        self.assertFalse(firewall_mod.is_template_firewall(document))

    def test_shipped_firewall_accepts_only_the_runtime_inventory(self):
        document = firewall_mod.load_firewall_document(firewall_mod.DEFAULT_FIREWALL_CONFIG_PATH)
        firewall_mod.enforce_feature_set(self.EXPECTED_RUNTIME, document)

    def test_every_v29_field_is_rejected_as_runtime_leakage(self):
        document = firewall_mod.load_firewall_document(firewall_mod.DEFAULT_FIREWALL_CONFIG_PATH)
        for field in self.EXPECTED_FORBIDDEN:
            with self.subTest(field=field):
                self.assertEqual(
                    firewall_mod.audit_feature_set([field], document)[field],
                    firewall_mod.FORBIDDEN_LABEL,
                )
                with self.assertRaises(firewall_mod.FeatureFirewallError):
                    firewall_mod.enforce_feature_set([self.EXPECTED_RUNTIME[0], field], document)


class TemplateDetectionTest(unittest.TestCase):
    def test_active_status_with_placeholder_features_is_still_a_template(self):
        doc = {
            "schema_version": 1,
            "status": "ACTIVE",
            "runtime_allowed_features": [f"PENDING_FEATURE_{i}_REPLACE_FROM_RUNTIME_SPEC" for i in range(1, 4)],
            "forbidden_labels": _synthetic_active_document()["forbidden_labels"],
        }
        self.assertTrue(firewall_mod.is_template_firewall(doc))
        with self.assertRaises(firewall_mod.FeatureFirewallError):
            firewall_mod.require_active_firewall(doc)

    def test_active_status_with_placeholder_labels_is_still_a_template(self):
        doc = {
            "schema_version": 1,
            "status": "ACTIVE",
            "runtime_allowed_features": _synthetic_active_document()["runtime_allowed_features"],
            "forbidden_labels": [f"PENDING_LABEL_{i}_REPLACE_FROM_S0_AUDIT" for i in range(1, 3)],
        }
        self.assertTrue(firewall_mod.is_template_firewall(doc))
        with self.assertRaises(firewall_mod.FeatureFirewallError):
            firewall_mod.require_active_firewall(doc)

    def test_active_with_real_looking_entries_on_both_sides_is_not_a_template(self):
        self.assertFalse(firewall_mod.is_template_firewall(_synthetic_active_document()))

    def test_active_with_one_remaining_placeholder_feature_among_real_entries_is_still_a_template(self):
        # The bug this regression test guards against: is_template_firewall
        # previously required EVERY entry on a side to be a placeholder
        # (all(...)), so real names plus one leftover PENDING_FEATURE_* was
        # missed. Must reject as soon as ANY entry on either side is still
        # a placeholder.
        doc = copy.deepcopy(_synthetic_active_document())
        doc["runtime_allowed_features"].append("PENDING_FEATURE_1_REPLACE_FROM_RUNTIME_SPEC")
        self.assertTrue(firewall_mod.is_template_firewall(doc))
        with self.assertRaises(firewall_mod.FeatureFirewallError):
            firewall_mod.require_active_firewall(doc)

    def test_active_with_one_remaining_placeholder_label_among_real_entries_is_still_a_template(self):
        doc = copy.deepcopy(_synthetic_active_document())
        doc["forbidden_labels"].append("PENDING_LABEL_1_REPLACE_FROM_S0_AUDIT")
        self.assertTrue(firewall_mod.is_template_firewall(doc))
        with self.assertRaises(firewall_mod.FeatureFirewallError):
            firewall_mod.require_active_firewall(doc)


class RequireActiveFirewallTest(unittest.TestCase):
    def test_active_synthetic_document_returns_both_lists(self):
        runtime_allowed, forbidden_labels = firewall_mod.require_active_firewall(_synthetic_active_document())
        self.assertEqual(sorted(runtime_allowed), sorted(_synthetic_active_document()["runtime_allowed_features"]))
        self.assertEqual(sorted(forbidden_labels), sorted(_synthetic_active_document()["forbidden_labels"]))

    def test_in_memory_malformed_active_document_is_rejected(self):
        # require_active_firewall is the public enforcement gate and must
        # structurally validate its input itself -- a hand-built in-memory
        # document that never passed through load_firewall_document (and
        # so never had jsonschema.Draft202012Validator applied to it) must
        # still be rejected here for missing a required field, not
        # accepted just because its status says ACTIVE.
        doc = {"schema_version": 1, "status": "ACTIVE", "runtime_allowed_features": ["a"]}  # forbidden_labels missing
        with self.assertRaises(firewall_mod.FeatureFirewallError):
            firewall_mod.require_active_firewall(doc)

    def test_in_memory_overlapping_active_document_is_rejected(self):
        # Same reasoning: the allowed/forbidden contradiction guard that
        # load_firewall_document performs must also run inside
        # require_active_firewall itself, not only for documents loaded
        # from disk.
        doc = copy.deepcopy(_synthetic_active_document())
        doc["forbidden_labels"].append(doc["runtime_allowed_features"][0])
        with self.assertRaises(firewall_mod.FeatureFirewallError):
            firewall_mod.require_active_firewall(doc)


class ClassifyFeatureTest(unittest.TestCase):
    def test_allowed_feature_is_allowed(self):
        result = firewall_mod.classify_feature("a", runtime_allowed=["a", "b"], forbidden_labels=["c"])
        self.assertEqual(result, firewall_mod.ALLOWED)

    def test_forbidden_label_is_forbidden(self):
        result = firewall_mod.classify_feature("c", runtime_allowed=["a", "b"], forbidden_labels=["c"])
        self.assertEqual(result, firewall_mod.FORBIDDEN_LABEL)

    def test_unknown_name_is_not_runtime_available(self):
        result = firewall_mod.classify_feature("z", runtime_allowed=["a", "b"], forbidden_labels=["c"])
        self.assertEqual(result, firewall_mod.NOT_RUNTIME_AVAILABLE)

    def test_forbidden_wins_if_a_name_is_on_both_lists(self):
        # Defense in depth: even if a caller assembles lists in memory
        # that overlap (load_firewall_document would normally reject
        # this), forbidden must still win.
        result = firewall_mod.classify_feature("x", runtime_allowed=["x"], forbidden_labels=["x"])
        self.assertEqual(result, firewall_mod.FORBIDDEN_LABEL)


class AuditFeatureSetTest(unittest.TestCase):
    def test_audit_classifies_every_proposed_feature(self):
        doc = _synthetic_active_document()
        result = firewall_mod.audit_feature_set(
            ["synthetic_feature_accel_x", "synthetic_label_can_speed", "totally_unknown_field"], doc
        )
        self.assertEqual(
            result,
            {
                "synthetic_feature_accel_x": firewall_mod.ALLOWED,
                "synthetic_label_can_speed": firewall_mod.FORBIDDEN_LABEL,
                "totally_unknown_field": firewall_mod.NOT_RUNTIME_AVAILABLE,
            },
        )

    def test_audit_against_template_firewall_is_rejected(self):
        template = {
            "schema_version": 1,
            "status": "TEMPLATE_PENDING_REVIEW",
            "runtime_allowed_features": ["PENDING_FEATURE_1_REPLACE_FROM_RUNTIME_SPEC"],
            "forbidden_labels": ["PENDING_LABEL_1_REPLACE_FROM_S0_AUDIT"],
        }
        with self.assertRaises(firewall_mod.FeatureFirewallError):
            firewall_mod.audit_feature_set(["anything"], template)


class EnforceFeatureSetTest(unittest.TestCase):
    def test_feature_set_of_only_allowed_names_passes(self):
        doc = _synthetic_active_document()
        firewall_mod.enforce_feature_set(["synthetic_feature_accel_x", "synthetic_feature_accel_y"], doc)

    def test_feature_set_containing_a_forbidden_label_is_rejected(self):
        doc = _synthetic_active_document()
        with self.assertRaises(firewall_mod.FeatureFirewallError):
            firewall_mod.enforce_feature_set(["synthetic_feature_accel_x", "synthetic_label_can_speed"], doc)

    def test_feature_set_containing_an_unknown_name_is_rejected(self):
        doc = _synthetic_active_document()
        with self.assertRaises(firewall_mod.FeatureFirewallError):
            firewall_mod.enforce_feature_set(["synthetic_feature_accel_x", "not_a_known_feature"], doc)

    def test_feature_set_against_template_firewall_is_rejected(self):
        # Even if the proposed features happen to overlap the template's
        # placeholder text, a template firewall can never be used to pass
        # enforcement -- require_active_firewall must fire first.
        template = {
            "schema_version": 1,
            "status": "TEMPLATE_PENDING_REVIEW",
            "runtime_allowed_features": ["PENDING_FEATURE_1_REPLACE_FROM_RUNTIME_SPEC"],
            "forbidden_labels": ["PENDING_LABEL_1_REPLACE_FROM_S0_AUDIT"],
        }
        with self.assertRaises(firewall_mod.FeatureFirewallError):
            firewall_mod.enforce_feature_set([template["runtime_allowed_features"][0]], template)


if __name__ == "__main__":
    unittest.main()
