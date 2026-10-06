"""Contract tests for the frozen S3 alignment and mount-slip protocol."""

import copy
import json
import unittest
from pathlib import Path

import jsonschema


class S3AlignmentProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[3]
        cls.protocol_path = cls.root / "docs/protocols/s3_alignment_protocol_v1.json"
        cls.schema_path = (
            cls.root / "docs/protocols/s3_alignment_protocol_v1.schema.json"
        )
        cls.prose_path = (
            cls.root
            / "docs/protocols/SIH26168_S3_ALIGNMENT_AND_MOUNT_SLIP_PROTOCOL_v1.md"
        )
        cls.enum_path = cls.root / "contracts/enums/alignment_status_v1.json"
        cls.protocol = cls._load(cls.protocol_path)
        cls.schema = cls._load(cls.schema_path)
        cls.validator = jsonschema.Draft202012Validator(cls.schema)

    @staticmethod
    def _load(path):
        def reject_duplicate_keys(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"duplicate JSON key {key!r} in {path}")
                result[key] = value
            return result

        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )

    def assert_invalid_at(self, document, expected_path):
        errors = list(self.validator.iter_errors(document))
        self.assertTrue(errors)
        self.assertTrue(
            any(list(error.absolute_path) == expected_path for error in errors),
            [list(error.absolute_path) for error in errors],
        )

    def test_schema_and_frozen_instance_are_valid(self):
        jsonschema.Draft202012Validator.check_schema(self.schema)
        self.validator.validate(self.protocol)

    def test_ids_and_scenario_floor_are_exact(self):
        self.assertEqual(
            {item["id"] for item in self.protocol["invariants"]},
            {f"S3-I{i:02d}" for i in range(1, 7)},
        )
        self.assertEqual(
            {item["id"] for item in self.protocol["hypotheses"]},
            {f"S3-H{i}" for i in range(5)},
        )
        self.assertEqual(
            {item["id"] for item in self.protocol["candidate_methods"]},
            {"S3-M0", "S3-M1", "S3-M2"},
        )
        self.assertEqual(
            {item["id"] for item in self.protocol["scenarios"]},
            {f"S3-S{i:02d}" for i in range(1, 9)},
        )
        self.assertEqual(
            {item["id"] for item in self.protocol["metrics"]},
            {f"S3-K{i:02d}" for i in range(1, 13)},
        )
        self.assertEqual(
            {
                item["id"]: item["minimum_runs"]
                for item in self.protocol["scenarios"]
            },
            {
                "S3-S01": 9,
                "S3-S02": 6,
                "S3-S03": 6,
                "S3-S04": 6,
                "S3-S05": 6,
                "S3-S06": 12,
                "S3-S07": 6,
                "S3-S08": 1,
            },
        )

    def test_statuses_match_authoritative_enum_and_fail_closed(self):
        statuses = self._load(self.enum_path)["values"]
        policy = self.protocol["status_policy"]
        self.assertEqual(policy["allowed_statuses"], statuses)
        self.assertEqual(
            policy["dependent_aids_enabled"],
            {
                "UNINITIALIZED": False,
                "VALID": True,
                "UNCERTAIN": False,
                "SLIP_SUSPECTED": False,
            },
        )
        self.assertEqual(
            policy["slip_transition"],
            "atomic_disable_before_or_with_SLIP_SUSPECTED",
        )

    def test_candidate_selection_excludes_negative_control(self):
        candidates = {
            item["id"]: item for item in self.protocol["candidate_methods"]
        }
        self.assertEqual(candidates["S3-M0"]["role"], "negative_control")
        self.assertFalse(candidates["S3-M0"]["selection_eligible"])
        self.assertEqual(candidates["S3-M1"]["magnetometer_policy"], "forbidden")
        self.assertEqual(
            candidates["S3-M2"]["magnetometer_policy"],
            "optional_non_authoritative",
        )
        rank_order = self.protocol["outcome_policy"]["rank_order"]
        self.assertEqual(rank_order, ["S3-M1", "S3-M2"])
        self.assertTrue(all(candidates[item]["selection_eligible"] for item in rank_order))

    def test_thresholds_and_design_are_predeclared(self):
        self.assertEqual(
            self.protocol["design"],
            {
                "minimum_named_devices": 2,
                "minimum_mounts_per_device": 3,
                "minimum_vehicles": 1,
                "run_order": "preassigned_and_seeded_before_collection",
                "run_count_scope": (
                    "per_candidate_per_named_device_balanced_across_mounts"
                ),
                "candidate_progression": (
                    "complete_M1_then_execute_preassigned_M2_only_if_M1_fails"
                ),
                "percentile_method": "nearest_rank",
                "reference_rotation_uncertainty_deg_max": 1.0,
                "motion_speed_mps_min": 3.0,
                "gnss_bearing_accuracy_deg_max": 5.0,
                "gnss_speed_accuracy_mps_max": 0.5,
                "motion_segment_s_min": 10.0,
                "turn_heading_change_deg_min": 30.0,
                "valid_sustain_s_min": 2.0,
                "no_slip_observation_s_min": 60.0,
            },
        )
        self.assertEqual(
            self.protocol["thresholds"],
            {
                "rotation_error_median_deg_max": 5.0,
                "rotation_error_p95_deg_max": 10.0,
                "roll_pitch_error_p95_deg_max": 5.0,
                "yaw_error_p95_deg_max": 10.0,
                "time_to_valid_p95_s_max": 15.0,
                "covariance_95_coverage_min": 0.9,
                "invalid_i06_count_max": 0,
                "stationary_false_valid_count_max": 0,
                "slip_rotation_deg_min": 15.0,
                "slip_detection_rate_min": 1.0,
                "slip_detection_latency_p95_s_max": 1.0,
                "no_slip_false_positive_count_max": 0,
                "dependent_aid_unsafe_enable_count_max": 0,
                "replay_mismatch_count_max": 0,
            },
        )

    def test_claims_and_change_control_do_not_turn_protocol_into_evidence(self):
        prohibited = " ".join(self.protocol["claims_boundary"]["prohibited"])
        self.assertIn("executes or passes S3", prohibited)
        self.assertIn("alignment-dependent aid claim", prohibited)
        self.assertEqual(
            self.protocol["outcome_policy"]["failure_rule"],
            "reject_all_methods_and_keep_S3_unresolved",
        )
        self.assertEqual(
            self.protocol["change_control"],
            {
                "before_first_run": "signed_reviewed_commit_required",
                "after_first_run": "new_protocol_id_and_separate_evidence_required",
            },
        )

    def test_schema_rejects_safety_weakening(self):
        cases = [
            (
                ("thresholds", "rotation_error_p95_deg_max", 11.0),
                ["thresholds", "rotation_error_p95_deg_max"],
            ),
            (
                ("status_policy", "dependent_aids_enabled", "UNCERTAIN", True),
                ["status_policy", "dependent_aids_enabled", "UNCERTAIN"],
            ),
            (
                ("change_control", "after_first_run", "edit_in_place"),
                ["change_control", "after_first_run"],
            ),
        ]
        for mutation, expected_path in cases:
            with self.subTest(path=expected_path):
                altered = copy.deepcopy(self.protocol)
                target = altered
                for key in mutation[:-2]:
                    target = target[key]
                target[mutation[-2]] = mutation[-1]
                self.assert_invalid_at(altered, expected_path)

        altered = copy.deepcopy(self.protocol)
        altered["execution_result"] = "PASS"
        self.assert_invalid_at(altered, [])

    def test_prose_and_machine_protocol_share_frozen_identity(self):
        prose = self.prose_path.read_text(encoding="utf-8")
        self.assertIn(self.protocol["protocol_id"], prose)
        self.assertIn(self.protocol["frozen_against"]["base_commit"], prose)
        self.assertIn("This freeze is not execution evidence", prose)
        self.assertIn("S3\nand OD-04 remain explicitly unresolved", prose)
        for status in self.protocol["status_policy"]["allowed_statuses"]:
            self.assertIn(f"`{status}`", prose)


if __name__ == "__main__":
    unittest.main()
