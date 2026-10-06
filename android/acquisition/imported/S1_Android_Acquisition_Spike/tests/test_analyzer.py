import json
import tempfile
import unittest
from pathlib import Path

from analyzer.s1_analyzer import (
    analyze_session, analyze_stream, battery_summary, burst_sizes, describe,
    materialize_input, percentile, state_at,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "deterministic_session"


class AnalyzerTests(unittest.TestCase):
    def test_percentile_interpolates(self):
        self.assertEqual(percentile([0.0, 10.0], 0.5), 5.0)

    def test_describe_empty(self):
        self.assertIsNone(describe([])["mean"])

    def test_duplicate_and_reorder_detected_without_sorting(self):
        rows = [
            {"source_timestamp_ns": t, "callback_arrival_timestamp_ns": a, "sequence": i + 1}
            for i, (t, a) in enumerate([(10, 20), (20, 30), (20, 40), (15, 50)])
        ]
        result = analyze_stream("sensor:test", rows, 100.0)
        self.assertEqual(result["duplicate_timestamps"], 1)
        self.assertEqual(result["non_monotonic_timestamps"], 1)

    def test_gap_detection(self):
        rows = [{"source_timestamp_ns": t, "callback_arrival_timestamp_ns": t + 5, "sequence": i + 1}
                for i, t in enumerate([0, 10_000_000, 20_000_000, 600_000_000])]
        self.assertEqual(analyze_stream("sensor:test", rows, 100.0)["gaps"]["count"], 1)

    def test_sequence_anomaly(self):
        rows = [{"source_timestamp_ns": i * 10, "callback_arrival_timestamp_ns": i * 10 + 1, "sequence": seq}
                for i, seq in enumerate([1, 2, 4])]
        self.assertEqual(analyze_stream("x", rows, None)["sequence_anomalies"], 1)

    def test_burst_sizes(self):
        self.assertEqual(burst_sizes([0, 1_000_000, 2_000_000, 10_000_000]), [3, 1])

    def test_state_at(self):
        self.assertEqual(state_at([(10, "on"), (20, "off")], 15), "on")

    def test_battery_insufficient(self):
        self.assertFalse(battery_summary([])["evidence_sufficient"])

    def test_fixture_is_complete_and_hash_valid(self):
        result = analyze_session(FIXTURE)
        self.assertTrue(result["session_complete"])
        self.assertEqual(result["manifest_and_parse_errors"], [])

    def test_fixture_preserves_anomaly(self):
        result = analyze_session(FIXTURE)
        sensor = result["streams"]["sensor:fixture"]
        self.assertEqual(sensor["duplicate_timestamps"], 1)
        self.assertEqual(sensor["non_monotonic_timestamps"], 1)

    def test_zip_path_traversal_rejected(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            archive = Path(d) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("../escape", "x")
            with self.assertRaises(ValueError):
                materialize_input(archive, Path(d) / "out")

    def test_fixture_location_summary(self):
        result = analyze_session(FIXTURE)
        self.assertEqual(result["gnss_location"]["provider_distribution"], {"gps": 2})


if __name__ == "__main__":
    unittest.main()
