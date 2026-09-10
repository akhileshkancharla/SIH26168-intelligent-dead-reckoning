#!/usr/bin/env python3
"""Compare independent C++ and NumPy replays of identical fixtures.

The C++ executable must be run separately before this script. This script reads
its ordinary CSV output; it never invokes or imports the C++ implementation.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from reference_oracle import (
    GnssMeasurement,
    ImuSample,
    MeasurementKind,
    NavigationCore,
    NominalState,
    rotation_distance,
)


TOLERANCES = {
    "position_component_m": 2.0e-9,
    "velocity_component_mps": 2.0e-9,
    "rotation_error_rad": 2.0e-10,
    "accel_bias_component_mps2": 2.0e-10,
    "gyro_bias_component_radps": 2.0e-10,
    "covariance_element": 2.0e-9,
    "innovation_component": 2.0e-9,
    "nis_absolute": 2.0e-9,
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def initial_state(path: Path) -> NominalState:
    row = read_csv(path)[0]
    covariance = np.zeros((15, 15))
    sigmas = [float(row["sigma_position"]), float(row["sigma_velocity"]),
              float(row["sigma_attitude"]), float(row["sigma_accel_bias"]),
              float(row["sigma_gyro_bias"])]
    for block, sigma in enumerate(sigmas):
        start = block * 3
        covariance[start:start + 3, start:start + 3] = np.eye(3) * sigma**2
    return NominalState(
        timestamp_ns=int(row["timestamp_ns"]),
        position_n=np.array([float(row[f"p{i}"]) for i in range(3)]),
        velocity_n=np.array([float(row[f"v{i}"]) for i in range(3)]),
        q_n_b=np.array([float(row[f"q{i}"]) for i in range(4)]),
        accel_bias_b=np.array([float(row[f"ba{i}"]) for i in range(3)]),
        gyro_bias_b=np.array([float(row[f"bg{i}"]) for i in range(3)]),
        covariance=covariance,
    )


def parse_measurement(row: dict[str, str]) -> GnssMeasurement:
    kind = MeasurementKind(row["kind"])
    value = np.array([float(row[f"z{i}"]) for i in range(6)])
    covariance = np.diag([float(row[f"r{i}"]) for i in range(6)])
    return GnssMeasurement(row["measurement_id"], int(row["timestamp_ns"]),
                           kind, value, covariance)


def cpp_state(row: dict[str, str]) -> NominalState:
    covariance = np.array(
        [[float(row[f"P{r}_{c}"]) for c in range(15)] for r in range(15)]
    )
    return NominalState(
        timestamp_ns=int(row["timestamp_ns"]),
        position_n=np.array([float(row[f"p{i}"]) for i in range(3)]),
        velocity_n=np.array([float(row[f"v{i}"]) for i in range(3)]),
        q_n_b=np.array([float(row[f"q{i}"]) for i in range(4)]),
        accel_bias_b=np.array([float(row[f"ba{i}"]) for i in range(3)]),
        gyro_bias_b=np.array([float(row[f"bg{i}"]) for i in range(3)]),
        covariance=covariance,
    )


def update_max(record: dict, name: str, value: float, timestamp_ns: int) -> None:
    if value > record[name]["value"]:
        record[name] = {"value": float(value), "timestamp_ns": timestamp_ns}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    cpp_states_path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "build/cpp_replay_states.csv"
    cpp_measurements_path = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "build/cpp_replay_measurements.csv"
    output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else root / "results/parity_results.json"

    trajectory = read_csv(root / "fixtures/trajectory_fixture.csv")
    measurement_rows = read_csv(root / "fixtures/gnss_measurements.csv")
    cpp_state_rows = read_csv(cpp_states_path)
    cpp_measurement_rows = read_csv(cpp_measurements_path)
    if len(trajectory) != len(cpp_state_rows):
        raise RuntimeError("C++ state row count does not match fixture row count")

    by_timestamp: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in measurement_rows:
        by_timestamp[int(row["timestamp_ns"])].append(row)

    core = NavigationCore(initial_state(root / "fixtures/initial_state.csv"))
    python_measurements: list[dict] = []
    maxima = {
        "position_component_m": {"value": 0.0, "timestamp_ns": 0},
        "velocity_component_mps": {"value": 0.0, "timestamp_ns": 0},
        "rotation_error_rad": {"value": 0.0, "timestamp_ns": 0},
        "accel_bias_component_mps2": {"value": 0.0, "timestamp_ns": 0},
        "gyro_bias_component_radps": {"value": 0.0, "timestamp_ns": 0},
        "covariance_element": {"value": 0.0, "timestamp_ns": 0},
    }

    gap_count = 0
    for fixture_row, cpp_row in zip(trajectory, cpp_state_rows, strict=True):
        timestamp_ns = int(fixture_row["timestamp_ns"])
        force = np.array([float(fixture_row[f"observed_acc_{axis}"]) for axis in "xyz"])
        rate = np.array([float(fixture_row[f"observed_gyro_{axis}"]) for axis in "xyz"])
        propagation = core.propagate(ImuSample(timestamp_ns, force, rate))
        if not propagation["accepted"]:
            raise RuntimeError(f"Python fixture propagation rejected: {propagation}")
        gap_count += int(propagation["gap_detected"])
        for measurement_row in by_timestamp.get(timestamp_ns, []):
            update = core.update(parse_measurement(measurement_row))
            python_measurements.append({
                "timestamp_ns": timestamp_ns,
                "measurement_id": measurement_row["measurement_id"],
                **update,
            })

        cpp = cpp_state(cpp_row)
        update_max(maxima, "position_component_m",
                   float(np.max(np.abs(core.state.position_n - cpp.position_n))), timestamp_ns)
        update_max(maxima, "velocity_component_mps",
                   float(np.max(np.abs(core.state.velocity_n - cpp.velocity_n))), timestamp_ns)
        update_max(maxima, "rotation_error_rad",
                   rotation_distance(core.state.q_n_b, cpp.q_n_b), timestamp_ns)
        update_max(maxima, "accel_bias_component_mps2",
                   float(np.max(np.abs(core.state.accel_bias_b - cpp.accel_bias_b))), timestamp_ns)
        update_max(maxima, "gyro_bias_component_radps",
                   float(np.max(np.abs(core.state.gyro_bias_b - cpp.gyro_bias_b))), timestamp_ns)
        update_max(maxima, "covariance_element",
                   float(np.max(np.abs(core.state.covariance - cpp.covariance))), timestamp_ns)

    if len(python_measurements) != len(cpp_measurement_rows):
        raise RuntimeError("C++ and Python measurement-log counts differ")

    measurement_maxima = {
        "innovation_component": {"value": 0.0, "measurement_id": ""},
        "nis_absolute": {"value": 0.0, "measurement_id": ""},
    }
    decision_mismatches = []
    for python_row, cpp_row in zip(python_measurements, cpp_measurement_rows, strict=True):
        identifier = python_row["measurement_id"]
        cpp_accepted = cpp_row["accepted"] == "1"
        cpp_duplicate = cpp_row["duplicate"] == "1"
        cpp_dimension = int(cpp_row["dimension"])
        cpp_status = cpp_row["status"]
        if (python_row["accepted"] != cpp_accepted or python_row["duplicate"] != cpp_duplicate
                or python_row["dimension"] != cpp_dimension or python_row["status"] != cpp_status):
            decision_mismatches.append({
                "measurement_id": identifier,
                "python": {key: python_row[key] for key in ("accepted", "duplicate", "dimension", "status")},
                "cpp": {"accepted": cpp_accepted, "duplicate": cpp_duplicate,
                        "dimension": cpp_dimension, "status": cpp_status},
            })
        dimension = python_row["dimension"]
        if dimension:
            cpp_innovation = np.array([float(cpp_row[f"innovation{i}"]) for i in range(6)])
            innovation_error = float(np.max(np.abs(python_row["innovation"] - cpp_innovation)))
            if innovation_error > measurement_maxima["innovation_component"]["value"]:
                measurement_maxima["innovation_component"] = {
                    "value": innovation_error, "measurement_id": identifier}
        python_nis = python_row["nis"]
        cpp_nis = float(cpp_row["nis"])
        if np.isfinite(python_nis) and np.isfinite(cpp_nis):
            nis_error = abs(float(python_nis) - cpp_nis)
            if nis_error > measurement_maxima["nis_absolute"]["value"]:
                measurement_maxima["nis_absolute"] = {"value": nis_error,
                                                       "measurement_id": identifier}

    checks = []
    for name, maximum in {**maxima, **measurement_maxima}.items():
        checks.append({"name": name, "maximum": maximum["value"],
                       "tolerance": TOLERANCES[name],
                       "status": "passed" if maximum["value"] <= TOLERANCES[name] else "failed"})
    checks.append({"name": "acceptance_decision_comparison",
                   "mismatch_count": len(decision_mismatches),
                   "status": "passed" if not decision_mismatches else "failed"})
    overall_passed = all(check["status"] == "passed" for check in checks)
    result = {
        "schema_version": 1,
        "overall_status": "passed" if overall_passed else "failed",
        "independence_statement": (
            "The NumPy oracle did not import, bind, or invoke C++. The separately executed C++ "
            "replay and Python replay consumed identical generated CSV fixtures."
        ),
        "fixture_rows": len(trajectory),
        "measurement_instances": len(python_measurements),
        "valid_gap_count": gap_count,
        "predeclared_tolerances": TOLERANCES,
        "maxima": maxima,
        "measurement_maxima": measurement_maxima,
        "decision_mismatches": decision_mismatches,
        "checks": checks,
        "accepted_measurements": sum(row["accepted"] for row in python_measurements),
        "rejected_measurements": sum(not row["accepted"] and not row["duplicate"]
                                     for row in python_measurements),
        "duplicate_measurements": sum(row["duplicate"] for row in python_measurements),
    }
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"overall_status": result["overall_status"],
                      "fixture_rows": result["fixture_rows"],
                      "max_position_component_m": maxima["position_component_m"]["value"],
                      "max_rotation_error_rad": maxima["rotation_error_rad"]["value"],
                      "max_covariance_element": maxima["covariance_element"]["value"],
                      "decision_mismatches": len(decision_mismatches)}, indent=2))
    return 0 if overall_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
