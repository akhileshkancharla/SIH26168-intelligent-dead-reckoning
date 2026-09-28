import csv
import json
from pathlib import Path
import tempfile
import unittest

from experiments.wp11_2.train import TrainingConfig, train


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "synthetic.csv"
        self.fieldnames = [
            "session_id",
            "timestamp_ns",
            "accelerometer_x",
            "gyroscope_z",
            "residual_m",
        ]
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames)
            writer.writeheader()
            for session in range(4):
                for sample in range(5):
                    value = session * 5 + sample
                    writer.writerow(
                        {
                            "session_id": f"synthetic-{session}",
                            "timestamp_ns": session * 1_000_000 + sample + 1,
                            "accelerometer_x": value / 10,
                            "gyroscope_z": value / 20,
                            "residual_m": 2 + 3 * value,
                        }
                    )
        self.config = TrainingConfig(
            ("accelerometer_x", "gyroscope_z"), "residual_m", 1e-3
        )

    def test_deterministic_group_safe_output(self) -> None:
        first = train(self.path, self.config)
        second = train(self.path, self.config)
        self.assertEqual(
            json.dumps(first, sort_keys=True, allow_nan=False),
            json.dumps(second, sort_keys=True, allow_nan=False),
        )
        split = first["split"]
        self.assertEqual(split["method"], "ordered-journey-group-holdout")
        self.assertEqual(split["train_rows"], 15)
        self.assertEqual(split["validation_rows"], 5)
        self.assertTrue(
            set(split["train_group_sha256"]).isdisjoint(
                split["validation_group_sha256"]
            )
        )

    def test_evidence_is_bounded_and_identifiers_are_hashed(self) -> None:
        artifact = train(self.path, self.config)
        self.assertEqual(artifact["status"], "exploratory-not-promoted")
        self.assertEqual(artifact["pipeline_version"], "wp11.2-v2")
        serialized = json.dumps(artifact, sort_keys=True)
        self.assertNotIn("synthetic-0", serialized)
        self.assertEqual(artifact["input"]["groups"], 4)

    def test_rejects_leaky_features_and_target_feature(self) -> None:
        with self.assertRaisesRegex(ValueError, "forbidden/leaky"):
            train(
                self.path,
                TrainingConfig(("accelerometer_x", "speed_mps"), "residual_m"),
            )
        with self.assertRaisesRegex(ValueError, "target cannot"):
            train(self.path, TrainingConfig(("residual_m",), "residual_m"))

    def test_rejects_single_group_and_non_monotonic_time(self) -> None:
        single_group = Path(self.temporary.name) / "single.csv"
        with single_group.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames)
            writer.writeheader()
            for index in range(3):
                writer.writerow(
                    {
                        "session_id": "only",
                        "timestamp_ns": index + 1,
                        "accelerometer_x": index,
                        "gyroscope_z": index,
                        "residual_m": index,
                    }
                )
        with self.assertRaisesRegex(ValueError, "at least two journey groups"):
            train(single_group, self.config)

        non_monotonic = Path(self.temporary.name) / "non-monotonic.csv"
        with non_monotonic.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames)
            writer.writeheader()
            for group, timestamp in (("a", 2), ("a", 1), ("b", 3)):
                writer.writerow(
                    {
                        "session_id": group,
                        "timestamp_ns": timestamp,
                        "accelerometer_x": 1,
                        "gyroscope_z": 1,
                        "residual_m": 1,
                    }
                )
        with self.assertRaisesRegex(ValueError, "timestamps must increase"):
            train(non_monotonic, self.config)

    def test_group_order_does_not_compare_boot_scoped_clocks(self) -> None:
        path = Path(self.temporary.name) / "boot-clocks.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames)
            writer.writeheader()
            for group, timestamp in (("first", 900), ("first", 901), ("second", 1)):
                writer.writerow(
                    {
                        "session_id": group,
                        "timestamp_ns": timestamp,
                        "accelerometer_x": timestamp,
                        "gyroscope_z": timestamp,
                        "residual_m": timestamp,
                    }
                )
        artifact = train(
            path,
            TrainingConfig(("accelerometer_x",), "residual_m", 1e-3, 0.5),
        )
        self.assertEqual(artifact["split"]["train_rows"], 2)
        self.assertEqual(artifact["split"]["validation_rows"], 1)


    def test_rejects_reappearing_closed_journey_group(self) -> None:
        path = Path(self.temporary.name) / "interleaved-groups.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames)
            writer.writeheader()
            for group, timestamp in (("a", 1), ("b", 1), ("a", 2)):
                writer.writerow(
                    {
                        "session_id": group,
                        "timestamp_ns": timestamp,
                        "accelerometer_x": timestamp,
                        "gyroscope_z": timestamp,
                        "residual_m": timestamp,
                    }
                )
        with self.assertRaisesRegex(ValueError, "one contiguous block"):
            train(path, self.config)


if __name__ == "__main__":
    unittest.main()
