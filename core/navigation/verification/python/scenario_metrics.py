#!/usr/bin/env python3
"""Record deterministic scenario errors as machine-readable evidence."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

from reference_oracle import CoreConfig, ImuSample, NavigationCore, NominalState


def config() -> CoreConfig:
    return replace(CoreConfig(), accel_noise_density=0.0, gyro_noise_density=0.0,
                   accel_bias_rw_density=0.0, gyro_bias_rw_density=0.0)


def run(state: NominalState, steps: int, dt_s: float,
        force: np.ndarray, rate: np.ndarray) -> NavigationCore:
    core = NavigationCore(state, config())
    timestamp = state.timestamp_ns
    increment = round(dt_s * 1.0e9)
    for _ in range(steps):
        timestamp += increment
        outcome = core.propagate(ImuSample(timestamp, force, rate))
        if not outcome["accepted"]:
            raise RuntimeError(str(outcome))
    return core


def main() -> int:
    output = (Path(sys.argv[1]) if len(sys.argv) > 1
              else Path(__file__).resolve().parents[1] / "results/scenario_metrics.json")
    zero = NominalState(covariance=np.zeros((15, 15)))
    static = run(zero, 500, 0.01, np.array([0.0, 0.0, -9.80665]), np.zeros(3))
    velocity_state = zero.copy(); velocity_state.velocity_n = np.array([7.0, -1.0, 0.2])
    straight = run(velocity_state, 300, 0.01,
                   np.array([0.0, 0.0, -9.80665]), np.zeros(3))
    acceleration = run(zero, 200, 0.01,
                       np.array([1.0, 0.0, -9.80665]), np.zeros(3))
    turn_state = zero.copy(); turn_state.velocity_n = np.array([5.0, 0.0, 0.0])
    turn = run(turn_state, 800, 0.005,
               np.array([0.0, 1.25, -9.80665]), np.array([0.0, 0.0, 0.25]))
    expected_turn_position = np.array([20.0 * np.sin(1.0), 20.0 * (1.0 - np.cos(1.0)), 0.0])
    expected_turn_velocity = np.array([5.0 * np.cos(1.0), 5.0 * np.sin(1.0), 0.0])
    bias_state = zero.copy()
    bias_state.accel_bias_b = np.array([0.04, -0.02, 0.03])
    bias_state.gyro_bias_b = np.array([0.002, -0.001, 0.003])
    biased = run(bias_state, 400, 0.01,
                 np.array([0.04, -0.02, -9.80665 + 0.03]), bias_state.gyro_bias_b)
    result = {
        "schema_version": 1,
        "implementation": "independent Python/NumPy oracle",
        "scenarios": {
            "stationary_level_5s": {
                "position_error_norm_m": float(np.linalg.norm(static.state.position_n)),
                "velocity_error_norm_mps": float(np.linalg.norm(static.state.velocity_n)),
            },
            "constant_velocity_3s": {
                "position_error_norm_m": float(np.linalg.norm(
                    straight.state.position_n - velocity_state.velocity_n * 3.0)),
                "velocity_error_norm_mps": float(np.linalg.norm(
                    straight.state.velocity_n - velocity_state.velocity_n)),
            },
            "constant_acceleration_2s": {
                "position_error_norm_m": float(np.linalg.norm(
                    acceleration.state.position_n - np.array([2.0, 0.0, 0.0]))),
                "velocity_error_norm_mps": float(np.linalg.norm(
                    acceleration.state.velocity_n - np.array([2.0, 0.0, 0.0]))),
            },
            "constant_radius_turn_4s": {
                "position_error_norm_m": float(np.linalg.norm(
                    turn.state.position_n - expected_turn_position)),
                "velocity_error_norm_mps": float(np.linalg.norm(
                    turn.state.velocity_n - expected_turn_velocity)),
                "quaternion_norm_error": abs(float(np.linalg.norm(turn.state.q_n_b)) - 1.0),
            },
            "known_bias_cancellation_4s": {
                "position_error_norm_m": float(np.linalg.norm(biased.state.position_n)),
                "velocity_error_norm_mps": float(np.linalg.norm(biased.state.velocity_n)),
            },
        },
    }
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
