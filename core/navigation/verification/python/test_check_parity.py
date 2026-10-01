#!/usr/bin/env python3
"""Focused tests for deterministic S2 parity reporting."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from check_parity import (
    TOLERANCES,
    canonical_fixture_sha256,
    maximum_check,
    relative_difference,
    scalar_record,
    update_max,
    vector_record,
)
from compare_parity_runs import ARTIFACTS, compare


class ParityReportingTest(unittest.TestCase):
    def test_canonical_fixture_hash_is_line_ending_independent(self) -> None:
        expected = hashlib.sha256(b"a,b\r\n1,2\r\n").hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture.csv"
            fixture.write_bytes(b"a,b\r\n1,2\r\n")
            self.assertEqual(expected, canonical_fixture_sha256(fixture))

    def test_relative_difference_handles_zero_and_exact_values(self) -> None:
        self.assertEqual(0.0, relative_difference(0.0, 0.0))
        self.assertEqual(0.0, relative_difference(2.0, 2.0))
        self.assertAlmostEqual(0.5, relative_difference(2.0, 1.0))

    def test_vector_record_preserves_values_and_differences(self) -> None:
        record = vector_record(
            "position",
            np.array([1.0, -2.0, 0.0]),
            np.array([1.0, -1.0, 0.0]),
            tolerance=1.0,
        )
        self.assertEqual([1.0, -2.0, 0.0], record["python"])
        self.assertEqual([1.0, -1.0, 0.0], record["cpp"])
        self.assertEqual([0.0, 1.0, 0.0], record["absolute_difference"])
        self.assertEqual(1.0, record["maximum_absolute_difference"])
        self.assertEqual("passed", record["status"])

    def test_zero_dimension_record_is_valid_for_duplicate_decisions(self) -> None:
        record = vector_record("innovation", np.array([]), np.array([]), tolerance=2.0e-9)
        self.assertEqual(0.0, record["maximum_absolute_difference"])
        self.assertEqual("passed", record["status"])

    def test_non_finite_vector_fails_closed_and_emits_strict_json(self) -> None:
        for invalid in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(invalid=invalid):
                record = vector_record(
                    "position",
                    np.array([1.0, invalid]),
                    np.array([1.0, 2.0]),
                    tolerance=2.0e-9,
                )
                self.assertEqual("failed", record["status"])
                self.assertIsNone(record["maximum_absolute_difference"])
                self.assertEqual([[1]], record["non_finite_values"]["python_indices"])
                json.dumps(record, allow_nan=False)

    def test_non_finite_maximum_cannot_leave_aggregate_passed(self) -> None:
        maxima = {
            "position_component_m": {
                "value": 0.0,
                "timestamp_ns": 0,
                "non_finite_count": 0,
            }
        }
        update_max(
            maxima,
            "position_component_m",
            float("nan"),
            {"timestamp_ns": 123},
        )
        check = maximum_check("position_component_m", maxima["position_component_m"])
        self.assertEqual(1, check["non_finite_count"])
        self.assertEqual("failed", check["status"])
        json.dumps({"maxima": maxima, "check": check}, allow_nan=False)

    def test_nis_finiteness_mismatch_fails_closed(self) -> None:
        mismatch = scalar_record(
            "nis", float("nan"), 1.0, TOLERANCES["nis_absolute"]
        )
        self.assertEqual("failed", mismatch["status"])
        self.assertIsNone(mismatch["python"])
        self.assertEqual(1.0, mismatch["cpp"])
        both_invalid_but_required = scalar_record(
            "nis", float("nan"), float("nan"), TOLERANCES["nis_absolute"]
        )
        self.assertEqual("failed", both_invalid_but_required["status"])
        duplicate = scalar_record(
            "nis",
            float("nan"),
            float("nan"),
            TOLERANCES["nis_absolute"],
            applicable=False,
        )
        self.assertEqual("not_applicable", duplicate["status"])
        json.dumps([mismatch, both_invalid_but_required, duplicate], allow_nan=False)

    def test_zero_dimension_with_supplied_finite_nis_fails_closed(self) -> None:
        record = scalar_record(
            "nis",
            0.0,
            0.0,
            TOLERANCES["nis_absolute"],
            applicable=False,
        )
        self.assertEqual("failed", record["status"])
        self.assertEqual(0.0, record["python"])
        self.assertEqual(0.0, record["cpp"])
        json.dumps(record, allow_nan=False)

    def test_parity_lock_is_hash_verified_for_windows_python_312(self) -> None:
        root = Path(__file__).resolve().parents[4]
        lock = (root / "core/navigation/verification/requirements-parity.txt").read_text(
            encoding="utf-8"
        )
        workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("numpy==2.5.3", lock)
        self.assertIn("--hash=sha256:", lock)
        self.assertIn("--require-hashes", workflow)
        self.assertIn("--only-binary=:all:", workflow)

    def test_determinism_comparison_detects_one_changed_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            for name in ARTIFACTS:
                (first / name).write_text("same\n", encoding="utf-8")
                (second / name).write_text("same\n", encoding="utf-8")
            self.assertEqual("passed", compare(first, second)["status"])
            (second / ARTIFACTS[0]).write_text("changed\n", encoding="utf-8")
            self.assertEqual("failed", compare(first, second)["status"])


if __name__ == "__main__":
    unittest.main()
