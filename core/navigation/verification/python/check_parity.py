#!/usr/bin/env python3
"""Compare independent C++ and NumPy replays of identical fixtures.

The C++ executable must be run separately before this script. This script reads
its ordinary CSV output; it never invokes or imports the C++ implementation.
"""

from __future__ import annotations

import csv
import hashlib
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

STATE_ORDERING = (
    "position_n[0:3], velocity_n[0:3], attitude_error[0:3], "
    "accel_bias_b[0:3], gyro_bias_b[0:3]"
)


def canonical_fixture_sha256(path: Path) -> str:
    """Hash fixtures in the accepted S2 package representation.

    The imported CSV is normalized to LF by Git while the accepted S2 manifest
    records the original CRLF package bytes. Reconstructing CRLF makes the
    provenance check independent of the checkout's line-ending policy.
    """
    content = path.read_bytes().replace(b"\r\n", b"\n")
    if path.suffix.lower() == ".csv":
        content = content.replace(b"\n", b"\r\n")
    return hashlib.sha256(content).hexdigest()


def relative_difference(actual: float, expected: float) -> float | None:
    if not math.isfinite(actual) or not math.isfinite(expected):
        return None
    absolute = abs(actual - expected)
    scale = max(abs(actual), abs(expected))
    return 0.0 if absolute == 0.0 else absolute / scale if scale else math.inf


def strict_json_numbers(value: np.ndarray) -> list:
    """Return nested JSON values without permitting NaN or infinity."""

    def sanitize(item):
        if isinstance(item, list):
            return [sanitize(child) for child in item]
        number = float(item)
        return number if math.isfinite(number) else None

    return sanitize(np.asarray(value).tolist())


def non_finite_indices(value: np.ndarray) -> list[list[int]]:
    return [[int(index) for index in location]
            for location in np.argwhere(~np.isfinite(value))]


def vector_record(
    name: str,
    python_value: np.ndarray,
    cpp_value: np.ndarray,
    tolerance: float,
) -> dict:
    python_value = np.asarray(python_value, dtype=np.float64)
    cpp_value = np.asarray(cpp_value, dtype=np.float64)
    if python_value.shape != cpp_value.shape:
        raise ValueError(f"{name} shapes differ: {python_value.shape} != {cpp_value.shape}")
    finite = np.isfinite(python_value) & np.isfinite(cpp_value)
    with np.errstate(invalid="ignore"):
        absolute = np.abs(python_value - cpp_value)
    scale = np.maximum(np.abs(python_value), np.abs(cpp_value))
    relative = np.full_like(absolute, np.nan)
    relative = np.divide(
        absolute,
        scale,
        out=relative,
        where=finite & (scale != 0.0),
    )
    relative[finite & (absolute == 0.0)] = 0.0
    maximum = float(np.max(absolute)) if absolute.size and np.all(finite) else (
        0.0 if not absolute.size else None
    )
    return {
        "field": name,
        "python": strict_json_numbers(python_value),
        "cpp": strict_json_numbers(cpp_value),
        "absolute_difference": strict_json_numbers(absolute),
        "relative_difference": strict_json_numbers(relative),
        "maximum_absolute_difference": maximum,
        "non_finite_values": {
            "python_indices": non_finite_indices(python_value),
            "cpp_indices": non_finite_indices(cpp_value),
        },
        "tolerance": tolerance,
        "status": "passed" if maximum is not None and maximum <= tolerance else "failed",
    }


def scalar_record(
    name: str,
    python_value: float,
    cpp_value: float,
    tolerance: float,
    *,
    applicable: bool = True,
) -> dict:
    """Compare a scalar while failing closed on applicable non-finite values."""

    python_finite = math.isfinite(float(python_value))
    cpp_finite = math.isfinite(float(cpp_value))
    both_finite = python_finite and cpp_finite
    if not applicable and not python_finite and not cpp_finite:
        return {
            "field": name,
            "python": None,
            "cpp": None,
            "absolute_difference": None,
            "relative_difference": None,
            "tolerance": tolerance,
            "status": "not_applicable",
        }
    absolute = abs(float(python_value) - float(cpp_value)) if both_finite else None
    return {
        "field": name,
        "python": float(python_value) if python_finite else None,
        "cpp": float(cpp_value) if cpp_finite else None,
        "absolute_difference": absolute,
        "relative_difference": relative_difference(float(python_value), float(cpp_value)),
        "tolerance": tolerance,
        "status": (
            "passed"
            if applicable and absolute is not None and absolute <= tolerance
            else "failed"
        ),
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


def update_max(record: dict, name: str, value: float | None, location: dict) -> None:
    target = record[name]
    if value is None or not math.isfinite(float(value)):
        target["non_finite_count"] += 1
        target.setdefault("first_non_finite", location)
        return
    if value > target["value"]:
        target.update({"value": float(value), **location})


def maximum_check(name: str, maximum: dict) -> dict:
    return {
        "name": name,
        "maximum": maximum["value"],
        "non_finite_count": maximum["non_finite_count"],
        "tolerance": TOLERANCES[name],
        "status": "passed"
        if maximum["non_finite_count"] == 0 and maximum["value"] <= TOLERANCES[name]
        else "failed",
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    cpp_states_path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "build/cpp_replay_states.csv"
    cpp_measurements_path = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "build/cpp_replay_measurements.csv"
    output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else root / "results/parity_results.json"
    details_path = Path(sys.argv[4]) if len(sys.argv) > 4 else output_path.with_name("parity_details.jsonl")
    report_path = Path(sys.argv[5]) if len(sys.argv) > 5 else output_path.with_name("PARITY_REPORT.md")

    trajectory_path = root / "fixtures/trajectory_fixture.csv"
    measurements_path = root / "fixtures/gnss_measurements.csv"
    initial_state_path = root / "fixtures/initial_state.csv"
    initial_state_json_path = root / "fixtures/initial_state.json"
    manifest_path = root / "fixtures/scenario_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    accepted_paths = (
        trajectory_path,
        measurements_path,
        initial_state_path,
        initial_state_json_path,
    )
    fixture_hashes = {path.name: canonical_fixture_sha256(path) for path in accepted_paths}
    for name, expected in manifest["files"].items():
        if fixture_hashes.get(name) != expected["sha256"]:
            raise RuntimeError(
                f"Accepted fixture hash mismatch for {name}: "
                f"expected {expected['sha256']}, got {fixture_hashes.get(name)}"
            )
    trajectory = read_csv(trajectory_path)
    measurement_rows = read_csv(measurements_path)
    cpp_state_rows = read_csv(cpp_states_path)
    cpp_measurement_rows = read_csv(cpp_measurements_path)
    if len(trajectory) != len(cpp_state_rows):
        raise RuntimeError("C++ state row count does not match fixture row count")
    fixture_timestamps = [int(row["timestamp_ns"]) for row in trajectory]
    cpp_timestamps = [int(row["timestamp_ns"]) for row in cpp_state_rows]
    if fixture_timestamps != cpp_timestamps:
        raise RuntimeError("C++ state timestamps/order do not exactly match the fixture")
    fixture_measurement_ids = [row["measurement_id"] for row in measurement_rows]
    cpp_measurement_ids = [row["measurement_id"] for row in cpp_measurement_rows]
    if fixture_measurement_ids != cpp_measurement_ids:
        raise RuntimeError("C++ measurement evidence IDs/order do not exactly match the fixture")
    fixture_measurement_timestamps = [int(row["timestamp_ns"]) for row in measurement_rows]
    cpp_measurement_timestamps = [int(row["timestamp_ns"]) for row in cpp_measurement_rows]
    if fixture_measurement_timestamps != cpp_measurement_timestamps:
        raise RuntimeError("C++ measurement timestamps/order do not exactly match the fixture")

    by_timestamp: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in measurement_rows:
        by_timestamp[int(row["timestamp_ns"])].append(row)

    core = NavigationCore(initial_state(initial_state_path))
    python_measurements: list[dict] = []
    detail_records: list[dict] = []
    maxima = {
        name: {"value": 0.0, "timestamp_ns": 0, "non_finite_count": 0}
        for name in (
            "position_component_m",
            "velocity_component_mps",
            "rotation_error_rad",
            "accel_bias_component_mps2",
            "gyro_bias_component_radps",
            "covariance_element",
        )
    }

    gap_count = 0
    for fixture_index, (fixture_row, cpp_row) in enumerate(
        zip(trajectory, cpp_state_rows, strict=True)
    ):
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
        state_comparisons = [
            vector_record(
                "position_n_m",
                core.state.position_n,
                cpp.position_n,
                TOLERANCES["position_component_m"],
            ),
            vector_record(
                "velocity_n_mps",
                core.state.velocity_n,
                cpp.velocity_n,
                TOLERANCES["velocity_component_mps"],
            ),
            vector_record(
                "accel_bias_b_mps2",
                core.state.accel_bias_b,
                cpp.accel_bias_b,
                TOLERANCES["accel_bias_component_mps2"],
            ),
            vector_record(
                "gyro_bias_b_radps",
                core.state.gyro_bias_b,
                cpp.gyro_bias_b,
                TOLERANCES["gyro_bias_component_radps"],
            ),
        ]
        rotation_inputs_finite = bool(
            np.all(np.isfinite(core.state.q_n_b)) and np.all(np.isfinite(cpp.q_n_b))
        )
        rotation_error = (
            float(rotation_distance(core.state.q_n_b, cpp.q_n_b))
            if rotation_inputs_finite else None
        )
        covariance_difference = np.abs(core.state.covariance - cpp.covariance)
        covariance_finite = bool(
            np.all(np.isfinite(core.state.covariance))
            and np.all(np.isfinite(cpp.covariance))
            and np.all(np.isfinite(covariance_difference))
        )
        covariance_index = (
            np.unravel_index(int(np.argmax(covariance_difference)), covariance_difference.shape)
            if covariance_finite else None
        )
        covariance_maximum = (
            float(covariance_difference[covariance_index])
            if covariance_index is not None else None
        )
        state_comparisons.extend([
            {
                "field": "attitude_q_n_b",
                "python": strict_json_numbers(core.state.q_n_b),
                "cpp": strict_json_numbers(cpp.q_n_b),
                "quaternion_sign_equivalence": True,
                "rotation_error_rad": rotation_error,
                "non_finite_values": {
                    "python_indices": non_finite_indices(core.state.q_n_b),
                    "cpp_indices": non_finite_indices(cpp.q_n_b),
                },
                "tolerance": TOLERANCES["rotation_error_rad"],
                "status": "passed" if rotation_error is not None
                and math.isfinite(rotation_error)
                and rotation_error <= TOLERANCES["rotation_error_rad"] else "failed",
            },
            {
                "field": "covariance_15x15",
                "ordering": STATE_ORDERING,
                "shape": [15, 15],
                "full_matrix_compared": True,
                "python_diagonal": strict_json_numbers(np.diag(core.state.covariance)),
                "cpp_diagonal": strict_json_numbers(np.diag(cpp.covariance)),
                "python_max_symmetry_error": float(np.max(np.abs(
                    core.state.covariance - core.state.covariance.T
                ))) if covariance_finite else None,
                "cpp_max_symmetry_error": float(np.max(np.abs(
                    cpp.covariance - cpp.covariance.T
                ))) if covariance_finite else None,
                "maximum_absolute_difference": covariance_maximum,
                "maximum_difference_index": [int(index) for index in covariance_index]
                if covariance_index is not None else None,
                "python_at_maximum": float(core.state.covariance[covariance_index])
                if covariance_index is not None else None,
                "cpp_at_maximum": float(cpp.covariance[covariance_index])
                if covariance_index is not None else None,
                "relative_difference_at_maximum": relative_difference(
                    float(core.state.covariance[covariance_index]),
                    float(cpp.covariance[covariance_index]),
                ) if covariance_index is not None else None,
                "non_finite_values": {
                    "python_indices": non_finite_indices(core.state.covariance),
                    "cpp_indices": non_finite_indices(cpp.covariance),
                },
                "tolerance": TOLERANCES["covariance_element"],
                "status": "passed" if covariance_maximum is not None
                and covariance_maximum <= TOLERANCES["covariance_element"] else "failed",
            },
        ])
        detail_records.append({
            "record_type": "state",
            "input_order": fixture_index,
            "timestamp_ns": timestamp_ns,
            "comparisons": state_comparisons,
        })
        comparison_by_field = {comparison["field"]: comparison for comparison in state_comparisons}
        for maximum_name, comparison_name in (
            ("position_component_m", "position_n_m"),
            ("velocity_component_mps", "velocity_n_mps"),
            ("accel_bias_component_mps2", "accel_bias_b_mps2"),
            ("gyro_bias_component_radps", "gyro_bias_b_radps"),
        ):
            update_max(
                maxima,
                maximum_name,
                comparison_by_field[comparison_name]["maximum_absolute_difference"],
                {"timestamp_ns": timestamp_ns},
            )
        update_max(maxima, "rotation_error_rad", rotation_error, {"timestamp_ns": timestamp_ns})
        update_max(maxima, "covariance_element", covariance_maximum, {"timestamp_ns": timestamp_ns})

    if len(python_measurements) != len(cpp_measurement_rows):
        raise RuntimeError("C++ and Python measurement-log counts differ")

    measurement_maxima = {
        "innovation_component": {"value": 0.0, "measurement_id": "", "non_finite_count": 0},
        "nis_absolute": {"value": 0.0, "measurement_id": "", "non_finite_count": 0},
    }
    decision_mismatches = []
    for measurement_index, (python_row, cpp_row) in enumerate(
        zip(python_measurements, cpp_measurement_rows, strict=True)
    ):
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
        python_nis = python_row["nis"]
        cpp_nis = float(cpp_row["nis"])
        dimension = python_row["dimension"]
        python_innovation = np.asarray(python_row["innovation"], dtype=np.float64)[:dimension]
        cpp_innovation = np.array(
            [float(cpp_row[f"innovation{index}"]) for index in range(dimension)]
        )
        innovation_record = vector_record(
            "innovation",
            python_innovation,
            cpp_innovation,
            TOLERANCES["innovation_component"],
        )
        nis_record = scalar_record(
            "nis",
            float(python_nis),
            cpp_nis,
            TOLERANCES["nis_absolute"],
            applicable=dimension > 0,
        )
        update_max(
            measurement_maxima,
            "innovation_component",
            innovation_record["maximum_absolute_difference"],
            {"measurement_id": identifier},
        )
        if nis_record["status"] != "not_applicable":
            update_max(
                measurement_maxima,
                "nis_absolute",
                nis_record["absolute_difference"],
                {"measurement_id": identifier},
            )
        detail_records.append({
            "record_type": "measurement",
            "input_order": measurement_index,
            "timestamp_ns": int(python_row["timestamp_ns"]),
            "evidence_id": identifier,
            "python_decision": {
                key: python_row[key] for key in ("accepted", "duplicate", "dimension", "status")
            },
            "cpp_decision": {
                "accepted": cpp_accepted,
                "duplicate": cpp_duplicate,
                "dimension": cpp_dimension,
                "status": cpp_status,
            },
            "innovation": innovation_record,
            "nis": nis_record,
        })

    checks = [maximum_check(name, maximum)
              for name, maximum in {**maxima, **measurement_maxima}.items()]
    detail_failure_count = sum(
        comparison.get("status") == "failed"
        for record in detail_records
        for comparison in (
            record["comparisons"] if record["record_type"] == "state"
            else (record["innovation"], record["nis"])
        )
    )
    checks.append({
        "name": "per_record_comparison",
        "failure_count": detail_failure_count,
        "status": "passed" if detail_failure_count == 0 else "failed",
    })
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
        "fixture_identity": {
            **fixture_hashes,
            manifest_path.name: canonical_fixture_sha256(manifest_path),
        },
        "input_order_exact": True,
        "timestamp_order_exact": True,
        "evidence_id_order_exact": True,
        "state_ordering": STATE_ORDERING,
        "covariance_shape": [15, 15],
        "covariance_full_matrix_compared": True,
        "detail_record_count": len(detail_records),
        "detail_file": details_path.name,
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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    details_path.write_text(
        "".join(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n"
                for record in detail_records),
        encoding="utf-8",
    )
    report_path.write_text(
        "# S2 C++ and NumPy parity report\n\n"
        f"- Verdict: **{result['overall_status'].upper()}**\n"
        f"- Fixture rows: {result['fixture_rows']}\n"
        f"- Measurement instances: {result['measurement_instances']} "
        f"({result['accepted_measurements']} accepted, {result['rejected_measurements']} rejected, "
        f"{result['duplicate_measurements']} duplicate)\n"
        f"- Valid gap count: {result['valid_gap_count']}\n"
        f"- Decision mismatches: {len(decision_mismatches)}\n"
        f"- Maximum position component difference: {maxima['position_component_m']['value']:.17g} m "
        f"(tolerance {TOLERANCES['position_component_m']:.1e})\n"
        f"- Maximum velocity component difference: {maxima['velocity_component_mps']['value']:.17g} m/s "
        f"(tolerance {TOLERANCES['velocity_component_mps']:.1e})\n"
        f"- Maximum orientation error: {maxima['rotation_error_rad']['value']:.17g} rad "
        f"(tolerance {TOLERANCES['rotation_error_rad']:.1e})\n"
        f"- Maximum covariance element difference: {maxima['covariance_element']['value']:.17g} "
        f"(tolerance {TOLERANCES['covariance_element']:.1e})\n\n"
        "Quaternion comparison uses sign-equivalent rotation distance. The complete 15x15 covariance "
        "is compared in the frozen S2 error-state ordering; per-record values and differences are in "
        f"`{details_path.name}`. This is synthetic bounded parity evidence, not device accuracy evidence.\n",
        encoding="utf-8",
    )
    print(json.dumps({"overall_status": result["overall_status"],
                      "fixture_rows": result["fixture_rows"],
                      "max_position_component_m": maxima["position_component_m"]["value"],
                      "max_rotation_error_rad": maxima["rotation_error_rad"]["value"],
                      "max_covariance_element": maxima["covariance_element"]["value"],
                      "decision_mismatches": len(decision_mismatches)}, indent=2, allow_nan=False))
    return 0 if overall_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
