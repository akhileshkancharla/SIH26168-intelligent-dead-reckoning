#!/usr/bin/env python3
"""Deterministic test suite for the independent NumPy oracle."""

from __future__ import annotations

import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

from reference_oracle import (
    ATTITUDE,
    ACCEL_BIAS,
    GYRO_BIAS,
    CoreConfig,
    GnssMeasurement,
    ImuSample,
    MeasurementKind,
    NavigationCore,
    NominalState,
    default_initial_covariance,
    inject_error,
    quat_exp,
    quat_multiply,
    quat_to_rot,
    reset_jacobian,
    right_jacobian_so3,
    rot_to_quat,
    rotation_distance,
    so3_exp,
    state_error,
)


def zero_noise_config() -> CoreConfig:
    return replace(
        CoreConfig(), accel_noise_density=0.0, gyro_noise_density=0.0,
        accel_bias_rw_density=0.0, gyro_bias_rw_density=0.0
    )


def zero_state(covariance: float = 0.0) -> NominalState:
    return NominalState(covariance=np.eye(15) * covariance)


def propagate_constant(
    core: NavigationCore, steps: int, dt_s: float, force: np.ndarray, rate: np.ndarray
) -> None:
    timestamp = core.state.timestamp_ns
    increment = round(dt_s * 1.0e9)
    for _ in range(steps):
        timestamp += increment
        result = core.propagate(ImuSample(timestamp, force.copy(), rate.copy()))
        assert result["accepted"], result


def measurement(
    identifier: str, timestamp_ns: int, kind: MeasurementKind,
    value: np.ndarray, variance: np.ndarray
) -> GnssMeasurement:
    return GnssMeasurement(identifier, timestamp_ns, kind, np.asarray(value), np.diag(variance))


def assert_close(actual, expected, tolerance: float, label: str) -> None:
    error = float(np.linalg.norm(np.asarray(actual) - np.asarray(expected)))
    if not np.isfinite(error) or error > tolerance:
        raise AssertionError(f"{label}: norm error {error:.17g} > {tolerance:.17g}")


def main() -> int:
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("python_test_results.json")
    tests: list[tuple[str, callable]] = []

    def register(name: str):
        def decorator(function):
            tests.append((name, function))
            return function
        return decorator

    @register("frame.identity_rotation")
    def _():
        assert_close(quat_to_rot(quat_exp(np.zeros(3))), np.eye(3), 1.0e-15, "identity")

    @register("frame.known_90_degree_rotations")
    def _():
        assert_close(so3_exp(np.array([0.0, 0.0, np.pi / 2])) @ np.array([1.0, 0.0, 0.0]),
                     np.array([0.0, 1.0, 0.0]), 1.0e-12, "z90")

    @register("frame.composition_order")
    def _():
        first = quat_exp(np.array([0.2, 0.0, 0.0]))
        second = quat_exp(np.array([0.0, 0.0, -0.4]))
        assert_close(quat_to_rot(quat_multiply(first, second)),
                     quat_to_rot(first) @ quat_to_rot(second), 1.0e-14, "composition")

    @register("frame.inverse_transformation")
    def _():
        rotation = so3_exp(np.array([0.4, -0.2, 0.7]))
        vector = np.array([1.2, -4.0, 0.5])
        assert_close(rotation.T @ (rotation @ vector), vector, 1.0e-12, "inverse")

    @register("frame.quaternion_matrix_roundtrip")
    def _():
        rotation = so3_exp(np.array([-0.5, 0.3, 1.0]))
        assert_close(quat_to_rot(rot_to_quat(rotation)), rotation, 1.0e-12, "roundtrip")

    @register("frame.small_angle_injection")
    def _():
        nominal = zero_state()
        nominal.q_n_b = quat_exp(np.array([0.3, -0.2, 0.5]))
        injected = nominal.copy()
        correction = np.zeros(15)
        correction[ATTITUDE] = np.array([1.0e-5, -2.0e-5, 0.5e-5])
        inject_error(injected, correction)
        assert_close(state_error(nominal, injected)[ATTITUDE], correction[ATTITUDE],
                     1.0e-11, "injection")

    @register("frame.reset_consistency")
    def _():
        original = zero_state()
        original.q_n_b = quat_exp(np.array([0.2, 0.1, -0.3]))
        correction = np.array([0.04, -0.03, 0.02])
        residual = np.array([2.0e-6, -1.0e-6, 3.0e-6])
        updated = original.copy()
        correction15 = np.zeros(15); correction15[ATTITUDE] = correction
        inject_error(updated, correction15)
        truth = original.copy()
        truth_error = np.zeros(15); truth_error[ATTITUDE] = correction + residual
        inject_error(truth, truth_error)
        assert_close(state_error(updated, truth)[ATTITUDE],
                     right_jacobian_so3(correction) @ residual, 2.0e-10, "reset")

    @register("mechanization.stationary_specific_force_cancellation")
    def _():
        core = NavigationCore(zero_state(), zero_noise_config())
        propagate_constant(core, 500, 0.01, np.array([0.0, 0.0, -9.80665]), np.zeros(3))
        assert np.linalg.norm(core.state.position_n) < 1.0e-12
        assert np.linalg.norm(core.state.velocity_n) < 1.0e-12

    @register("mechanization.constant_velocity")
    def _():
        state = zero_state(); state.velocity_n = np.array([7.0, -1.0, 0.2])
        core = NavigationCore(state, zero_noise_config())
        propagate_constant(core, 300, 0.01, np.array([0.0, 0.0, -9.80665]), np.zeros(3))
        assert_close(core.state.position_n, state.velocity_n * 3.0, 1.0e-10, "position")

    @register("mechanization.constant_acceleration")
    def _():
        core = NavigationCore(zero_state(), zero_noise_config())
        propagate_constant(core, 200, 0.01, np.array([1.0, 0.0, -9.80665]), np.zeros(3))
        assert abs(core.state.velocity_n[0] - 2.0) < 1.0e-10
        assert abs(core.state.position_n[0] - 2.0) < 1.0e-10

    @register("mechanization.constant_radius_turn")
    def _():
        state = zero_state(); state.velocity_n = np.array([5.0, 0.0, 0.0])
        core = NavigationCore(state, zero_noise_config())
        propagate_constant(core, 800, 0.005, np.array([0.0, 1.25, -9.80665]),
                           np.array([0.0, 0.0, 0.25]))
        expected_p = np.array([20.0 * np.sin(1.0), 20.0 * (1.0 - np.cos(1.0)), 0.0])
        expected_v = np.array([5.0 * np.cos(1.0), 5.0 * np.sin(1.0), 0.0])
        assert_close(core.state.position_n, expected_p, 3.0e-5, "turn position")
        assert_close(core.state.velocity_n, expected_v, 3.0e-6, "turn velocity")

    @register("mechanization.known_constant_biases")
    def _():
        state = zero_state()
        state.accel_bias_b = np.array([0.04, -0.02, 0.03])
        state.gyro_bias_b = np.array([0.002, -0.001, 0.003])
        core = NavigationCore(state, zero_noise_config())
        propagate_constant(core, 400, 0.01,
                           np.array([0.04, -0.02, -9.80665 + 0.03]), state.gyro_bias_b)
        assert np.linalg.norm(core.state.position_n) < 1.0e-10

    @register("mechanization.irregular_dt")
    def _():
        core = NavigationCore(zero_state(), zero_noise_config())
        intervals = [0.007, 0.011, 0.009, 0.013, 0.008, 0.012]
        timestamp = 0; elapsed = 0.0
        for _repeat in range(30):
            for interval in intervals:
                timestamp += round(interval * 1.0e9); elapsed += interval
                assert core.propagate(ImuSample(timestamp, np.array([0.6, 0.0, -9.80665]),
                                                np.zeros(3)))["accepted"]
        assert abs(core.state.position_n[0] - 0.3 * elapsed**2) < 1.0e-10

    @register("mechanization.quaternion_norm")
    def _():
        core = NavigationCore(zero_state(), zero_noise_config())
        propagate_constant(core, 5000, 0.001, np.array([0.0, 0.0, -9.80665]),
                           np.array([0.3, -0.2, 0.8]))
        assert abs(np.linalg.norm(core.state.q_n_b) - 1.0) < 2.0e-15

    @register("mechanization.invalid_timestamp_rejection")
    def _():
        core = NavigationCore(zero_state(), zero_noise_config())
        assert core.propagate(ImuSample(10_000_000, np.array([0.0, 0.0, -9.80665]),
                                             np.zeros(3)))["accepted"]
        assert not core.propagate(ImuSample(10_000_000, np.zeros(3), np.zeros(3)))["accepted"]
        assert not core.propagate(ImuSample(9_000_000, np.zeros(3), np.zeros(3)))["accepted"]
        assert not core.propagate(ImuSample(500_000_000, np.zeros(3), np.zeros(3)))["accepted"]

    @register("mechanization.missing_gap_flag")
    def _():
        core = NavigationCore(zero_state(), zero_noise_config())
        result = core.propagate(ImuSample(40_000_000, np.array([0.0, 0.0, -9.80665]),
                                         np.zeros(3)))
        assert result["accepted"] and result["gap_detected"]

    @register("mechanization.deterministic_replay")
    def _():
        first = NavigationCore(zero_state())
        second = NavigationCore(zero_state())
        timestamp = 0
        for index in range(200):
            timestamp += 10_000_000
            force = np.array([0.01 * np.sin(index), 0.02 * np.cos(index), -9.80665])
            rate = np.array([0.001, -0.002, 0.01 * np.sin(0.2 * index)])
            first.propagate(ImuSample(timestamp, force, rate))
            second.propagate(ImuSample(timestamp, force, rate))
        assert np.array_equal(first.state.position_n, second.state.position_n)
        assert np.array_equal(first.state.covariance, second.state.covariance)

    @register("covariance.symmetry_and_psd")
    def _():
        core = NavigationCore(zero_state(0.1))
        propagate_constant(core, 300, 0.01, np.array([0.2, 0.1, -9.8]),
                           np.array([0.02, -0.01, 0.03]))
        assert np.max(np.abs(core.state.covariance - core.state.covariance.T)) < 1.0e-14
        assert np.min(np.linalg.eigvalsh(core.state.covariance)) >= -1.0e-12

    @register("covariance.correct_growth")
    def _():
        core = NavigationCore(zero_state(1.0e-6))
        initial = np.trace(core.state.covariance)
        propagate_constant(core, 100, 0.01, np.array([0.0, 0.0, -9.80665]), np.zeros(3))
        assert np.trace(core.state.covariance) > initial

    @register("covariance.bias_random_walk_growth")
    def _():
        config = replace(zero_noise_config(), accel_bias_rw_density=0.002,
                         gyro_bias_rw_density=0.0003)
        core = NavigationCore(zero_state(), config)
        assert core.propagate(ImuSample(100_000_000, np.array([0.0, 0.0, -9.80665]),
                                             np.zeros(3)))["accepted"]
        assert abs(core.state.covariance[9, 9] - 0.002**2 * 0.1) < 1.0e-18
        assert abs(core.state.covariance[12, 12] - 0.0003**2 * 0.1) < 1.0e-20

    @register("covariance.joseph_update_behavior")
    def _():
        state = zero_state(1.0); state.timestamp_ns = 100
        core = NavigationCore(state, zero_noise_config())
        result = core.update(measurement("p", 100, MeasurementKind.POSITION,
                                         np.array([0.2, -0.1, 0.05, 0, 0, 0]), np.ones(6)))
        assert result["accepted"]
        assert core.state.covariance[0, 0] < 1.0
        assert np.min(np.linalg.eigvalsh(core.state.covariance)) >= -1.0e-13

    @register("covariance.reset_covariance_behavior")
    def _():
        covariance = np.eye(15)
        covariance[0:3, 6:9] = np.eye(3) * 0.1
        covariance[6:9, 0:3] = np.eye(3) * 0.1
        reset = reset_jacobian(np.array([0.1, -0.08, 0.04]))
        transformed = reset @ covariance @ reset.T
        assert np.max(np.abs(transformed - transformed.T)) < 1.0e-14
        assert np.min(np.linalg.eigvalsh(transformed)) >= -1.0e-13
        assert np.linalg.norm(transformed - covariance) > 1.0e-4

    @register("covariance.no_nonfinite_or_negative_variance")
    def _():
        core = NavigationCore(zero_state(0.01))
        propagate_constant(core, 500, 0.005, np.array([0.3, -0.1, -9.5]),
                           np.array([0.1, 0.05, -0.2]))
        assert np.all(np.isfinite(core.state.covariance))
        assert np.min(np.diag(core.state.covariance)) >= -1.0e-14

    @register("measurement.position_update")
    def _():
        state = zero_state(1.0); state.timestamp_ns = 100
        core = NavigationCore(state, zero_noise_config())
        result = core.update(measurement("p", 100, MeasurementKind.POSITION,
                                         np.array([0.5, -0.2, 0.1, 0, 0, 0]), np.ones(6)))
        assert result["accepted"] and result["dimension"] == 3

    @register("measurement.velocity_update")
    def _():
        state = zero_state(1.0); state.timestamp_ns = 100
        core = NavigationCore(state, zero_noise_config())
        result = core.update(measurement("v", 100, MeasurementKind.VELOCITY,
                                         np.array([0.3, 0.1, -0.1, 0, 0, 0]), np.ones(6)))
        assert result["accepted"] and result["dimension"] == 3

    @register("measurement.combined_update_and_nis_dimension")
    def _():
        state = zero_state(1.0); state.timestamp_ns = 100
        core = NavigationCore(state, zero_noise_config())
        result = core.update(measurement("pv", 100, MeasurementKind.POSITION_VELOCITY,
                                         np.array([0.2, -0.1, 0, 0.3, 0.1, 0]), np.ones(6)))
        assert result["accepted"] and result["dimension"] == 6

    @register("measurement.inlier_and_outlier_gating")
    def _():
        state = zero_state(0.01); state.timestamp_ns = 100
        inlier_core = NavigationCore(state, zero_noise_config())
        inlier = inlier_core.update(measurement("i", 100, MeasurementKind.POSITION,
                                               np.array([0.02, 0, 0, 0, 0, 0]), np.ones(6)))
        outlier_core = NavigationCore(state, zero_noise_config())
        outlier = outlier_core.update(measurement("o", 100, MeasurementKind.POSITION,
                                                 np.array([100, -100, 30, 0, 0, 0]),
                                                 np.full(6, 0.01)))
        assert inlier["accepted"] and not outlier["accepted"]
        assert outlier["status"] == "rejected_nis_gate"

    @register("measurement.duplicate_id_rejection")
    def _():
        state = zero_state(1.0); state.timestamp_ns = 100
        core = NavigationCore(state, zero_noise_config())
        item = measurement("same", 100, MeasurementKind.POSITION, np.zeros(6), np.ones(6))
        assert core.update(item)["accepted"]
        duplicate = core.update(item)
        assert duplicate["duplicate"] and not duplicate["accepted"]

    @register("measurement.reacquisition_and_biased_return")
    def _():
        state = zero_state(0.05)
        good_core = NavigationCore(state, zero_noise_config())
        bad_core = NavigationCore(state, zero_noise_config())
        for core in (good_core, bad_core):
            propagate_constant(core, 50, 0.02, np.array([0.0, 0.0, -9.80665]), np.zeros(3))
        good = good_core.update(measurement("good", good_core.state.timestamp_ns,
                                           MeasurementKind.POSITION_VELOCITY,
                                           np.zeros(6), np.ones(6)))
        bad = bad_core.update(measurement("bad", bad_core.state.timestamp_ns,
                                         MeasurementKind.POSITION_VELOCITY,
                                         np.array([40, -30, 10, 8, -5, 2]), np.full(6, 0.1)))
        assert good["accepted"] and not bad["accepted"]

    records = []
    for name, function in tests:
        try:
            function()
            record = {"name": name, "status": "passed", "detail": "all assertions satisfied"}
            print(f"PASS {name}")
        except Exception as exception:  # test harness must record every failure
            record = {"name": name, "status": "failed", "detail": str(exception)}
            print(f"FAIL {name}: {exception}")
        records.append(record)

    passed = sum(record["status"] == "passed" for record in records)
    result = {
        "schema_version": 1,
        "language": f"Python {sys.version.split()[0]} / NumPy {np.__version__}",
        "total": len(records),
        "passed": passed,
        "failed": len(records) - passed,
        "skipped": 0,
        "tests": records,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Python tests: total={len(records)} passed={passed} failed={len(records)-passed} skipped=0")
    return 0 if passed == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
