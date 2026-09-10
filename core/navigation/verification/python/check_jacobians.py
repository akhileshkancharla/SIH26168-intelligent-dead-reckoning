#!/usr/bin/env python3
"""Manifold-aware finite-difference verification for both oracle implementations."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

from reference_oracle import (
    ATTITUDE,
    CoreConfig,
    ImuSample,
    MeasurementKind,
    NominalState,
    inject_error,
    linearize_propagation,
    measurement_jacobian,
    propagate_nominal_only,
    quat_exp,
    right_jacobian_so3,
    state_error,
)


ABS_TOL_PROPAGATION = 5.0e-7
REL_TOL_PROPAGATION = 5.0e-4
ABS_TOL_MEASUREMENT = 2.0e-9
REL_TOL_MEASUREMENT = 2.0e-5
ABS_TOL_RESET = 5.0e-9
SIGNIFICANT_ELEMENT_FLOOR = 1.0e-6


def block(index: int) -> str:
    return ("position" if index < 3 else "velocity" if index < 6 else
            "attitude" if index < 9 else "accel_bias" if index < 12 else "gyro_bias")


def step(column: int) -> float:
    if column < 6:
        return 1.0e-6
    if column < 9:
        return 1.0e-7
    return 1.0e-6


def error_summary(analytic: np.ndarray, numeric: np.ndarray) -> dict:
    absolute = np.abs(analytic - numeric)
    maximum = np.maximum(np.abs(analytic), np.abs(numeric))
    significant = maximum >= SIGNIFICANT_ELEMENT_FLOOR
    relative = np.zeros_like(absolute)
    relative[significant] = absolute[significant] / maximum[significant]
    max_index = np.unravel_index(int(np.argmax(absolute)), absolute.shape)
    return {
        "max_absolute_error": float(np.max(absolute)),
        "max_relative_error": float(np.max(relative)),
        "max_error_index": [int(index) for index in max_index],
        "analytic_at_max": float(analytic[max_index]),
        "finite_difference_at_max": float(numeric[max_index]),
    }


def propagation_checks() -> dict:
    orientations = [
        np.array([0.0, 0.0, 0.0]), np.array([0.35, -0.42, 0.71]),
        np.array([-0.60, 0.25, 1.20]), np.array([0.10, 0.80, -1.00]),
        np.array([-0.30, -0.55, 2.00]),
    ]
    intervals = [0.005, 0.010, 0.020, 0.013, 0.008]
    config = replace(CoreConfig(), accel_noise_density=0.0, gyro_noise_density=0.0,
                     accel_bias_rw_density=0.0, gyro_bias_rw_density=0.0)
    cases = []
    for case_index, (orientation, dt_s) in enumerate(zip(orientations, intervals, strict=True)):
        state = NominalState(
            position_n=np.array([4.0, -2.0, 0.5]),
            velocity_n=np.array([7.0, 1.5, -0.2]),
            q_n_b=quat_exp(orientation),
            accel_bias_b=np.array([0.02, -0.03, 0.015]),
            gyro_bias_b=np.array([0.001, -0.002, 0.0007]),
            covariance=np.zeros((15, 15)),
        )
        sample = ImuSample(round(dt_s * 1.0e9), np.array([0.6, -0.4, -9.3]),
                           np.array([0.08, -0.04, 0.22]))
        analytic = linearize_propagation(state, sample, dt_s, config)[0]
        nominal_output = propagate_nominal_only(state, sample, dt_s, config)
        numeric = np.zeros((15, 15))
        for column in range(15):
            epsilon = step(column)
            plus_error = np.zeros(15); plus_error[column] = epsilon
            minus_error = np.zeros(15); minus_error[column] = -epsilon
            plus_state = state.copy(); inject_error(plus_state, plus_error)
            minus_state = state.copy(); inject_error(minus_state, minus_error)
            plus_output = propagate_nominal_only(plus_state, sample, dt_s, config)
            minus_output = propagate_nominal_only(minus_state, sample, dt_s, config)
            numeric[:, column] = (
                state_error(nominal_output, plus_output)
                - state_error(nominal_output, minus_output)
            ) / (2.0 * epsilon)
        summary = error_summary(analytic, numeric)
        row, column = summary.pop("max_error_index")
        summary["max_error_element"] = {
            "row": row, "column": column, "row_block": block(row),
            "column_block": block(column),
            "analytic": summary.pop("analytic_at_max"),
            "finite_difference": summary.pop("finite_difference_at_max"),
        }
        summary.update({"case": case_index, "orientation_rotation_vector_rad": orientation.tolist(),
                        "dt_s": dt_s})
        cases.append(summary)

    max_abs_case = max(cases, key=lambda item: item["max_absolute_error"])
    max_rel_case = max(cases, key=lambda item: item["max_relative_error"])
    passed = (max_abs_case["max_absolute_error"] < ABS_TOL_PROPAGATION
              and max_rel_case["max_relative_error"] < REL_TOL_PROPAGATION)
    return {
        "cases": cases,
        "case_count": len(cases),
        "max_absolute_error": max_abs_case["max_absolute_error"],
        "max_relative_error": max_rel_case["max_relative_error"],
        "max_error_element": max_abs_case["max_error_element"],
        "failing_state_block": None if passed else max_abs_case["max_error_element"]["row_block"],
        "passed": passed,
    }


def measurement_checks() -> dict:
    orientations = [
        np.array([0.0, 0.0, 0.0]), np.array([0.35, -0.42, 0.71]),
        np.array([-0.60, 0.25, 1.20]), np.array([0.10, 0.80, -1.00]),
        np.array([-0.30, -0.55, 2.00]),
    ]
    cases = []
    for kind in (MeasurementKind.POSITION, MeasurementKind.VELOCITY,
                 MeasurementKind.POSITION_VELOCITY):
        for orientation in orientations:
            state = NominalState(position_n=np.array([2.0, -1.0, 0.3]),
                                 velocity_n=np.array([4.0, 0.5, -0.1]),
                                 q_n_b=quat_exp(orientation), covariance=np.zeros((15, 15)))
            analytic = measurement_jacobian(kind)
            dimension = analytic.shape[0]
            numeric = np.zeros_like(analytic)

            def value(input_state: NominalState) -> np.ndarray:
                if kind == MeasurementKind.POSITION:
                    return input_state.position_n
                if kind == MeasurementKind.VELOCITY:
                    return input_state.velocity_n
                return np.concatenate((input_state.position_n, input_state.velocity_n))

            for column in range(15):
                epsilon = step(column)
                plus_error = np.zeros(15); plus_error[column] = epsilon
                minus_error = np.zeros(15); minus_error[column] = -epsilon
                plus = state.copy(); inject_error(plus, plus_error)
                minus = state.copy(); inject_error(minus, minus_error)
                numeric[:, column] = (value(plus) - value(minus)) / (2.0 * epsilon)
            summary = error_summary(analytic, numeric)
            row, column = summary.pop("max_error_index")
            summary["max_error_element"] = {
                "row": row, "column": column, "column_block": block(column),
                "analytic": summary.pop("analytic_at_max"),
                "finite_difference": summary.pop("finite_difference_at_max"),
            }
            summary.update({"kind": kind.value, "dimension": dimension,
                            "orientation_rotation_vector_rad": orientation.tolist()})
            cases.append(summary)

    max_abs_case = max(cases, key=lambda item: item["max_absolute_error"])
    max_rel_case = max(cases, key=lambda item: item["max_relative_error"])
    passed = (max_abs_case["max_absolute_error"] < ABS_TOL_MEASUREMENT
              and max_rel_case["max_relative_error"] < REL_TOL_MEASUREMENT)
    return {
        "cases": cases, "case_count": len(cases),
        "max_absolute_error": max_abs_case["max_absolute_error"],
        "max_relative_error": max_rel_case["max_relative_error"],
        "max_error_element": {"kind": max_abs_case["kind"], **max_abs_case["max_error_element"]},
        "failing_measurement_block": None if passed else max_abs_case["kind"],
        "passed": passed,
    }


def reset_checks() -> dict:
    corrections = [
        np.array([0.0, 0.0, 0.0]), np.array([0.04, -0.03, 0.02]),
        np.array([-0.2, 0.1, 0.05]), np.array([0.3, -0.15, 0.25]),
    ]
    cases = []
    epsilon = 1.0e-7
    for correction in corrections:
        analytic = right_jacobian_so3(correction)
        numeric = np.zeros((3, 3))
        original = NominalState(covariance=np.zeros((15, 15)))
        updated = original.copy()
        update_error = np.zeros(15); update_error[ATTITUDE] = correction
        inject_error(updated, update_error)
        for column in range(3):
            perturb = np.zeros(3); perturb[column] = epsilon
            plus = original.copy(); plus_error = np.zeros(15); plus_error[ATTITUDE] = correction + perturb
            minus = original.copy(); minus_error = np.zeros(15); minus_error[ATTITUDE] = correction - perturb
            inject_error(plus, plus_error); inject_error(minus, minus_error)
            numeric[:, column] = (state_error(updated, plus)[ATTITUDE]
                                  - state_error(updated, minus)[ATTITUDE]) / (2.0 * epsilon)
        summary = error_summary(analytic, numeric)
        summary["correction_rad"] = correction.tolist()
        cases.append(summary)
    max_case = max(cases, key=lambda item: item["max_absolute_error"])
    return {"cases": cases, "case_count": len(cases),
            "max_absolute_error": max_case["max_absolute_error"],
            "passed": max_case["max_absolute_error"] < ABS_TOL_RESET}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    cpp_path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "results/cpp_jacobian_results.json"
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "results/jacobian_results.json"
    cpp = json.loads(cpp_path.read_text(encoding="utf-8"))
    python_propagation = propagation_checks()
    python_measurement = measurement_checks()
    python_reset = reset_checks()
    cpp_passed = (
        cpp["propagation"]["max_absolute_error"] < ABS_TOL_PROPAGATION
        and cpp["propagation"]["max_relative_error"] < REL_TOL_PROPAGATION
        and cpp["measurement"]["max_absolute_error"] < ABS_TOL_MEASUREMENT
        and cpp["measurement"]["max_relative_error"] < REL_TOL_MEASUREMENT
    )
    overall_passed = (cpp_passed and python_propagation["passed"]
                      and python_measurement["passed"] and python_reset["passed"])
    result = {
        "schema_version": 1,
        "overall_status": "passed" if overall_passed else "failed",
        "perturbation_convention": (
            "True state = nominal state injected on the right by delta-theta; p, v, and biases "
            "are additive. Central differences use the same injection and rotation-log error map."
        ),
        "step_sizes": {"position_m": 1.0e-6, "velocity_mps": 1.0e-6,
                       "attitude_rad": 1.0e-7, "accel_bias_mps2": 1.0e-6,
                       "gyro_bias_radps": 1.0e-6},
        "relative_error_definition": (
            "Absolute error / max(|analytic|, |numeric|) for elements whose denominator is at "
            "least 1e-6. Absolute error is evaluated over all elements."
        ),
        "predeclared_tolerances": {
            "propagation_max_absolute": ABS_TOL_PROPAGATION,
            "propagation_max_relative_significant": REL_TOL_PROPAGATION,
            "measurement_max_absolute": ABS_TOL_MEASUREMENT,
            "measurement_max_relative_significant": REL_TOL_MEASUREMENT,
            "reset_max_absolute": ABS_TOL_RESET,
        },
        "cpp": {**cpp, "passed": cpp_passed},
        "python_numpy": {
            "propagation": python_propagation,
            "measurement": python_measurement,
            "reset": python_reset,
        },
    }
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"overall_status": result["overall_status"],
                      "cpp_propagation_max_abs": cpp["propagation"]["max_absolute_error"],
                      "python_propagation_max_abs": python_propagation["max_absolute_error"],
                      "python_measurement_max_abs": python_measurement["max_absolute_error"],
                      "python_reset_max_abs": python_reset["max_absolute_error"]}, indent=2))
    return 0 if overall_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
