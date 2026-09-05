import json
import unittest
from pathlib import Path

class EnumsContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[3]
        cls.enums_dir = cls.root / "contracts/enums"

    def test_navigation_states_v1(self):
        file_path = self.enums_dir / "navigation_states_v1.json"
        self.assertTrue(file_path.is_file())
        data = json.loads(file_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("schema_version"), 1)
        self.assertNotIn("note", data, "Scaffold note must be removed")
        expected_states = ["INITIALIZING", "GNSS_AIDED", "DEGRADED", "BLACKOUT_DR", "REACQUIRING", "FAULT"]
        self.assertEqual(data.get("navigation_states"), expected_states)
        expected_provenance = ["LIVE_DEVICE", "DETERMINISTIC_REPLAY"]
        self.assertEqual(data.get("provenance"), expected_provenance)
        self.assertNotIn("SYNTHETIC", data.get("provenance", []))

    def test_navigation_mode_v1(self):
        file_path = self.enums_dir / "navigation_mode_v1.json"
        self.assertTrue(file_path.is_file())
        data = json.loads(file_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("enum_name"), "NavigationModeV1")
        expected = ["INITIALIZING", "GNSS_AIDED", "DEGRADED", "BLACKOUT_DR", "REACQUIRING", "FAULT"]
        self.assertEqual(data.get("values"), expected)
        for mode in expected:
            self.assertIn(mode, data.get("definitions", {}))

    def test_health_integrity_v1(self):
        file_path = self.enums_dir / "health_integrity_v1.json"
        self.assertTrue(file_path.is_file())
        data = json.loads(file_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("enum_name"), "HealthIntegrityStateV1")
        expected = ["HEALTHY", "DEGRADED", "UNAVAILABLE", "CANDIDATE_RETURN"]
        self.assertEqual(data.get("values"), expected)

    def test_alignment_status_v1(self):
        file_path = self.enums_dir / "alignment_status_v1.json"
        self.assertTrue(file_path.is_file())
        data = json.loads(file_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("enum_name"), "AlignmentStatusV1")
        expected = ["UNINITIALIZED", "VALID", "UNCERTAIN", "SLIP_SUSPECTED"]
        self.assertEqual(data.get("values"), expected)

    def test_display_mode_v1(self):
        file_path = self.enums_dir / "display_mode_v1.json"
        self.assertTrue(file_path.is_file())
        data = json.loads(file_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("enum_name"), "DisplayModeV1")
        expected = ["LIVE_DEVICE", "DETERMINISTIC_REPLAY"]
        self.assertEqual(data.get("values"), expected)

    def test_sensor_status_v1(self):
        file_path = self.enums_dir / "sensor_status_v1.json"
        self.assertTrue(file_path.is_file())
        data = json.loads(file_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("enum_name"), "SensorStatusV1")
        expected = ["AVAILABLE", "PARTIAL", "GAP", "MISSING_MANDATORY", "FAILED"]
        self.assertEqual(data.get("values"), expected)
        for s in expected:
            self.assertIn(s, data.get("definitions", {}))

    def test_model_status_v1(self):
        file_path = self.enums_dir / "model_status_v1.json"
        self.assertTrue(file_path.is_file())
        data = json.loads(file_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("enum_name"), "ModelStatusV1")
        expected = ["DISABLED", "LOADING", "SHADOW", "ELIGIBLE", "REJECTED", "FAILED"]
        self.assertEqual(data.get("values"), expected)
        for s in expected:
            self.assertIn(s, data.get("definitions", {}))

    def test_map_status_v1(self):
        file_path = self.enums_dir / "map_status_v1.json"
        self.assertTrue(file_path.is_file())
        data = json.loads(file_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("enum_name"), "MapStatusV1")
        expected = ["MISSING", "NO_CANDIDATE", "AMBIGUOUS", "CLEAR", "FAILED"]
        self.assertEqual(data.get("values"), expected)
        for s in expected:
            self.assertIn(s, data.get("definitions", {}))

    def test_reacquisition_status_v1(self):
        file_path = self.enums_dir / "reacquisition_status_v1.json"
        self.assertTrue(file_path.is_file())
        data = json.loads(file_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("enum_name"), "ReacquisitionStatusV1")
        expected = ["IDLE", "SCREENING", "DWELL", "ACCEPTED", "REJECTED"]
        self.assertEqual(data.get("values"), expected)
        for s in expected:
            self.assertIn(s, data.get("definitions", {}))

    def test_recording_status_v1(self):
        file_path = self.enums_dir / "recording_status_v1.json"
        self.assertTrue(file_path.is_file())
        data = json.loads(file_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("enum_name"), "RecordingStatusV1")
        expected = ["STARTING", "HEALTHY", "EVIDENCE_DEGRADED", "LOW_STORAGE", "INCOMPLETE", "COMPLETE"]
        self.assertEqual(data.get("values"), expected)
        for s in expected:
            self.assertIn(s, data.get("definitions", {}))

    def test_axes_separation(self):
        # Verify all nine Architecture Revision 3 supervisory axes remain distinct and orthogonal
        nav_mode = set(json.loads((self.enums_dir / "navigation_mode_v1.json").read_text(encoding="utf-8"))["values"])
        gnss_avail = set(json.loads((self.enums_dir / "health_integrity_v1.json").read_text(encoding="utf-8"))["values"])
        align = set(json.loads((self.enums_dir / "alignment_status_v1.json").read_text(encoding="utf-8"))["values"])
        display = set(json.loads((self.enums_dir / "display_mode_v1.json").read_text(encoding="utf-8"))["values"])
        sensor = set(json.loads((self.enums_dir / "sensor_status_v1.json").read_text(encoding="utf-8"))["values"])
        model = set(json.loads((self.enums_dir / "model_status_v1.json").read_text(encoding="utf-8"))["values"])
        map_status = set(json.loads((self.enums_dir / "map_status_v1.json").read_text(encoding="utf-8"))["values"])
        reacq = set(json.loads((self.enums_dir / "reacquisition_status_v1.json").read_text(encoding="utf-8"))["values"])
        recording = set(json.loads((self.enums_dir / "recording_status_v1.json").read_text(encoding="utf-8"))["values"])

        self.assertEqual(nav_mode, {"INITIALIZING", "GNSS_AIDED", "DEGRADED", "BLACKOUT_DR", "REACQUIRING", "FAULT"})
        self.assertEqual(gnss_avail, {"HEALTHY", "DEGRADED", "UNAVAILABLE", "CANDIDATE_RETURN"})
        self.assertEqual(align, {"UNINITIALIZED", "VALID", "UNCERTAIN", "SLIP_SUSPECTED"})
        self.assertEqual(display, {"LIVE_DEVICE", "DETERMINISTIC_REPLAY"})
        self.assertEqual(sensor, {"AVAILABLE", "PARTIAL", "GAP", "MISSING_MANDATORY", "FAILED"})
        self.assertEqual(model, {"DISABLED", "LOADING", "SHADOW", "ELIGIBLE", "REJECTED", "FAILED"})
        self.assertEqual(map_status, {"MISSING", "NO_CANDIDATE", "AMBIGUOUS", "CLEAR", "FAILED"})
        self.assertEqual(reacq, {"IDLE", "SCREENING", "DWELL", "ACCEPTED", "REJECTED"})
        self.assertEqual(recording, {"STARTING", "HEALTHY", "EVIDENCE_DEGRADED", "LOW_STORAGE", "INCOMPLETE", "COMPLETE"})

    def test_enum_invariants(self):
        for json_file in self.enums_dir.glob("*.json"):
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if "values" in data:
                values = data["values"]
                self.assertIsInstance(values, list)
                self.assertEqual(len(values), len(set(values)), f"Duplicate enum values in {json_file.name}")
                for val in values:
                    self.assertIsInstance(val, str)
                    self.assertTrue(val.isupper(), f"Enum {val} in {json_file.name} must be uppercase")

if __name__ == "__main__":
    unittest.main()
