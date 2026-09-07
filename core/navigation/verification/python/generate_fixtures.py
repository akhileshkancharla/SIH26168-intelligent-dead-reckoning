#!/usr/bin/env python3
"""Generate deterministic, rights-clean synthetic S2 fixtures."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from reference_oracle import CoreConfig, quat_exp, quat_to_rot


SEED = 2_616_802
GRAVITY = 9.80665


def _first_at_or_after(rows: list[dict], time_s: float) -> int:
    return next(index for index, row in enumerate(rows) if row["time_s"] >= time_s)


def generate_trajectory(rng: np.random.Generator) -> list[dict]:
    config = CoreConfig()
    rows: list[dict] = []
    timestamp_ns = 0
    time_s = 0.0
    position = np.zeros(3)
    speed = 0.0
    yaw = 0.0
    accel_bias = np.array([0.030, -0.020, 0.040], dtype=np.float64)
    gyro_bias = np.array([0.0010, -0.0008, 0.0015], dtype=np.float64)
    inserted_missing_gap = False

    while time_s < 18.0 - 1.0e-12:
        dt_s = float(rng.uniform(0.008, 0.012))
        gap = False
        if not inserted_missing_gap and time_s >= 9.0:
            dt_s = 0.040
            gap = True
            inserted_missing_gap = True
        if time_s + dt_s > 18.0:
            dt_s = 18.0 - time_s

        if time_s < 2.0:
            phase, longitudinal_acceleration, yaw_rate = "stationary", 0.0, 0.0
        elif time_s < 5.0:
            phase, longitudinal_acceleration, yaw_rate = "accelerate", 1.5, 0.0
        elif time_s < 7.0:
            phase, longitudinal_acceleration, yaw_rate = "constant_velocity", 0.0, 0.0
        elif time_s < 12.0:
            phase, longitudinal_acceleration, yaw_rate = "constant_radius_turn", 0.0, 0.18
        elif time_s < 15.0:
            phase, longitudinal_acceleration, yaw_rate = "decelerate", -1.5, 0.0
        else:
            phase, longitudinal_acceleration, yaw_rate = "stationary_final", 0.0, 0.0

        if speed <= 0.0 and longitudinal_acceleration < 0.0:
            longitudinal_acceleration = 0.0
        if speed + longitudinal_acceleration * dt_s < 0.0:
            longitudinal_acceleration = -speed / dt_s

        speed_mid = speed + 0.5 * longitudinal_acceleration * dt_s
        yaw_mid = yaw + 0.5 * yaw_rate * dt_s
        rotation_mid = quat_to_rot(quat_exp(np.array([0.0, 0.0, yaw_mid])))
        ideal_specific_force = np.array(
            [longitudinal_acceleration, speed_mid * yaw_rate, -GRAVITY], dtype=np.float64
        )
        ideal_angular_rate = np.array([0.0, 0.0, yaw_rate], dtype=np.float64)

        accel_noise = rng.normal(0.0, config.accel_noise_density / np.sqrt(dt_s), 3)
        gyro_noise = rng.normal(0.0, config.gyro_noise_density / np.sqrt(dt_s), 3)
        observed_specific_force = ideal_specific_force + accel_bias + accel_noise
        observed_angular_rate = ideal_angular_rate + gyro_bias + gyro_noise

        acceleration_n = rotation_mid @ ideal_specific_force + np.array([0.0, 0.0, GRAVITY])
        velocity_before = np.array([speed * np.cos(yaw), speed * np.sin(yaw), 0.0])
        position = position + velocity_before * dt_s + 0.5 * acceleration_n * dt_s**2
        speed = max(0.0, speed + longitudinal_acceleration * dt_s)
        yaw = yaw + yaw_rate * dt_s
        velocity = np.array([speed * np.cos(yaw), speed * np.sin(yaw), 0.0])
        truth_quaternion = quat_exp(np.array([0.0, 0.0, yaw]))

        timestamp_ns += int(round(dt_s * 1.0e9))
        time_s = timestamp_ns * 1.0e-9
        row = {
            "timestamp_ns": timestamp_ns,
            "time_s": time_s,
            "dt_s": dt_s,
            "phase": phase,
            "missing_sample_gap": int(gap),
            **{f"p_{axis}": position[i] for i, axis in enumerate("ned")},
            **{f"v_{axis}": velocity[i] for i, axis in enumerate("ned")},
            **{f"q_{name}": truth_quaternion[i] for i, name in enumerate(("w", "x", "y", "z"))},
            **{f"ideal_acc_{axis}": ideal_specific_force[i] for i, axis in enumerate("xyz")},
            **{f"ideal_gyro_{axis}": ideal_angular_rate[i] for i, axis in enumerate("xyz")},
            **{f"observed_acc_{axis}": observed_specific_force[i] for i, axis in enumerate("xyz")},
            **{f"observed_gyro_{axis}": observed_angular_rate[i] for i, axis in enumerate("xyz")},
            **{f"true_ba_{axis}": accel_bias[i] for i, axis in enumerate("xyz")},
            **{f"true_bg_{axis}": gyro_bias[i] for i, axis in enumerate("xyz")},
        }
        rows.append(row)

        accel_bias = accel_bias + rng.normal(
            0.0, config.accel_bias_rw_density * np.sqrt(dt_s), 3
        )
        gyro_bias = gyro_bias + rng.normal(
            0.0, config.gyro_bias_rw_density * np.sqrt(dt_s), 3
        )

    return rows


def generate_measurements(rows: list[dict], rng: np.random.Generator) -> list[dict]:
    measurements: list[dict] = []
    schedule = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 12.0, 12.8, 13.8, 14.8, 15.8, 16.8, 17.8]
    kinds = ["position", "velocity", "position_velocity"]
    duplicate_source_id: str | None = None

    for ordinal, requested_time in enumerate(schedule):
        row = rows[_first_at_or_after(rows, requested_time)]
        position = np.array([row["p_n"], row["p_e"], row["p_d"]])
        velocity = np.array([row["v_n"], row["v_e"], row["v_d"]])
        kind = kinds[ordinal % len(kinds)]
        measurement_id = f"gnss_{ordinal:03d}"
        expected = "accept"
        event = "normal"

        if requested_time == 12.0:
            kind = "position_velocity"
            position = position + np.array([35.0, -28.0, 12.0])
            velocity = velocity + np.array([8.0, -6.0, 3.0])
            measurement_id = "gnss_return_biased"
            expected = "reject"
            event = "biased_return"
        else:
            position = position + rng.normal(0.0, 0.8, 3)
            velocity = velocity + rng.normal(0.0, 0.20, 3)
            if requested_time == 12.8:
                event = "good_reacquisition"

        value = np.zeros(6)
        covariance_diagonal = np.zeros(6)
        if kind == "position":
            value[:3] = position
            covariance_diagonal[:3] = 0.8**2
        elif kind == "velocity":
            value[:3] = velocity
            covariance_diagonal[:3] = 0.20**2
        else:
            value[:3] = position
            value[3:] = velocity
            covariance_diagonal[:3] = 0.8**2
            covariance_diagonal[3:] = 0.20**2

        record = {
            "timestamp_ns": row["timestamp_ns"],
            "measurement_id": measurement_id,
            "kind": kind,
            "event": event,
            "expected_decision": expected,
            **{f"z{i}": value[i] for i in range(6)},
            **{f"r{i}": covariance_diagonal[i] for i in range(6)},
        }
        measurements.append(record)

        if requested_time == 13.8:
            duplicate_source_id = measurement_id
            duplicate = dict(record)
            duplicate["event"] = "duplicate_id"
            duplicate["expected_decision"] = "duplicate"
            measurements.append(duplicate)

    assert duplicate_source_id is not None
    return measurements


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {key: format(value, ".17g") if isinstance(value, float) else value
                 for key, value in row.items()}
            )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    fixtures = root / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    trajectory_rows = generate_trajectory(rng)
    measurement_rows = generate_measurements(trajectory_rows, rng)
    trajectory_path = fixtures / "trajectory_fixture.csv"
    measurement_path = fixtures / "gnss_measurements.csv"
    write_csv(trajectory_path, trajectory_rows)
    write_csv(measurement_path, measurement_rows)

    initial_state = {
        "timestamp_ns": 0,
        "position_n_m": [0.40, -0.30, 0.10],
        "velocity_n_mps": [0.10, -0.05, 0.00],
        "q_n_b_wxyz": quat_exp(np.deg2rad(np.array([0.5, -0.7, 1.0]))).tolist(),
        "accel_bias_b_mps2": [0.0, 0.0, 0.0],
        "gyro_bias_b_radps": [0.0, 0.0, 0.0],
        "covariance_standard_deviations": {
            "position_m": 1.0,
            "velocity_mps": 0.5,
            "attitude_rad": float(np.deg2rad(5.0)),
            "accel_bias_mps2": 0.05,
            "gyro_bias_radps": 0.005,
        },
    }
    initial_path = fixtures / "initial_state.json"
    initial_path.write_text(json.dumps(initial_state, indent=2) + "\n", encoding="utf-8")
    initial_csv_path = fixtures / "initial_state.csv"
    initial_csv_row = {
        "timestamp_ns": initial_state["timestamp_ns"],
        **{f"p{i}": initial_state["position_n_m"][i] for i in range(3)},
        **{f"v{i}": initial_state["velocity_n_mps"][i] for i in range(3)},
        **{f"q{i}": initial_state["q_n_b_wxyz"][i] for i in range(4)},
        **{f"ba{i}": initial_state["accel_bias_b_mps2"][i] for i in range(3)},
        **{f"bg{i}": initial_state["gyro_bias_b_radps"][i] for i in range(3)},
        "sigma_position": initial_state["covariance_standard_deviations"]["position_m"],
        "sigma_velocity": initial_state["covariance_standard_deviations"]["velocity_mps"],
        "sigma_attitude": initial_state["covariance_standard_deviations"]["attitude_rad"],
        "sigma_accel_bias": initial_state["covariance_standard_deviations"]["accel_bias_mps2"],
        "sigma_gyro_bias": initial_state["covariance_standard_deviations"]["gyro_bias_radps"],
    }
    write_csv(initial_csv_path, [initial_csv_row])

    scenario_manifest = {
        "schema_version": 1,
        "generator": "python/generate_fixtures.py",
        "random_generator": "NumPy PCG64",
        "seed": SEED,
        "rights_basis": "Generated synthetic data; no IO-VNBD bytes or derived values used.",
        "distinctions": {
            "true_motion": "p_*, v_*, q_*",
            "ideal_imu": "ideal_acc_*, ideal_gyro_*",
            "noisy_bias_corrupted_imu": "observed_acc_*, observed_gyro_*",
            "true_sensor_bias": "true_ba_*, true_bg_*",
            "measurement_observations": "gnss_measurements.csv z0..z5",
            "estimator_outputs": "generated during replay; compared in parity_results.json",
        },
        "required_scenarios": [
            {"id": 1, "name": "stationary_level_imu", "evidence": "phase=stationary"},
            {"id": 2, "name": "constant_velocity_straight", "evidence": "phase=constant_velocity"},
            {"id": 3, "name": "constant_longitudinal_acceleration", "evidence": "phase=accelerate"},
            {"id": 4, "name": "constant_radius_turn", "evidence": "phase=constant_radius_turn"},
            {"id": 5, "name": "stop_accelerate_turn_stop", "evidence": "complete 18 s fixture"},
            {"id": 6, "name": "known_accel_and_gyro_biases", "evidence": "true_ba_*, true_bg_*"},
            {"id": 7, "name": "bias_random_walk", "evidence": "seeded evolving bias columns"},
            {"id": 8, "name": "irregular_valid_sampling", "evidence": "dt_s in [0.008,0.012] except gap"},
            {"id": 9, "name": "one_missing_sample_gap", "evidence": "missing_sample_gap=1 at one row"},
            {"id": 10, "name": "gnss_position_updates", "evidence": "kind=position"},
            {"id": 11, "name": "gnss_velocity_updates", "evidence": "kind=velocity"},
            {"id": 12, "name": "combined_position_velocity_updates", "evidence": "kind=position_velocity"},
            {"id": 13, "name": "gnss_outage_and_reacquisition", "evidence": "no updates 7-12 s; good_reacquisition"},
            {"id": 14, "name": "biased_returning_gnss", "evidence": "event=biased_return"},
            {"id": 15, "name": "duplicate_measurement_id", "evidence": "event=duplicate_id"},
        ],
        "files": {},
    }
    manifest_path = fixtures / "scenario_manifest.json"
    for path in (trajectory_path, measurement_path, initial_path, initial_csv_path):
        scenario_manifest["files"][path.name] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    manifest_path.write_text(json.dumps(scenario_manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"seed": SEED, "trajectory_rows": len(trajectory_rows),
                      "measurement_rows": len(measurement_rows),
                      "manifest": str(manifest_path)}, indent=2))


if __name__ == "__main__":
    main()
