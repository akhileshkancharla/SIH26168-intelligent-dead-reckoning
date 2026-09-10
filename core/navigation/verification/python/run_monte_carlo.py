#!/usr/bin/env python3
"""Bounded NEES/NIS Monte Carlo consistency experiment for S2."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import chi2

from reference_oracle import (
    CoreConfig,
    GnssMeasurement,
    ImuSample,
    MeasurementKind,
    NavigationCore,
    NominalState,
    inject_error,
    quat_exp,
    quat_to_rot,
    state_error,
)


TRIALS = 250
STEPS = 300
DT_S = 0.01
MEASUREMENT_EVERY_STEPS = 25
BASE_SEED = 261_680_200
POSITION_MEASUREMENT_SIGMA_M = 0.8
VELOCITY_MEASUREMENT_SIGMA_MPS = 0.2
CONSISTENCY_PROBABILITY = 0.95


def interval(degrees_of_freedom: int, probability: float = CONSISTENCY_PROBABILITY) -> list[float]:
    alpha = 1.0 - probability
    return [float(chi2.ppf(alpha / 2.0, degrees_of_freedom)),
            float(chi2.ppf(1.0 - alpha / 2.0, degrees_of_freedom))]


def mean_interval(sample_count: int, dimension: int) -> list[float]:
    bounds = interval(sample_count * dimension)
    return [bounds[0] / sample_count, bounds[1] / sample_count]


def initial_covariance() -> np.ndarray:
    sigmas = np.array([
        *([0.5] * 3), *([0.2] * 3), *([0.01] * 3),
        *([0.02] * 3), *([0.002] * 3),
    ])
    return np.diag(sigmas**2)


def run_trial(trial_index: int, seed_sequence: np.random.SeedSequence) -> dict:
    rng = np.random.default_rng(seed_sequence)
    config = CoreConfig()
    covariance0 = initial_covariance()
    nominal = NominalState(
        timestamp_ns=0,
        position_n=np.zeros(3),
        velocity_n=np.array([4.0, 0.5, 0.0]),
        q_n_b=quat_exp(np.array([0.02, -0.01, 0.15])),
        accel_bias_b=np.zeros(3),
        gyro_bias_b=np.zeros(3),
        covariance=covariance0,
    )
    true_state = nominal.copy()
    initial_error = rng.multivariate_normal(np.zeros(15), covariance0)
    inject_error(true_state, initial_error)
    core = NavigationCore(nominal, config)
    gravity_n = np.asarray(config.gravity_n)
    measurement_covariance = np.diag([
        *([POSITION_MEASUREMENT_SIGMA_M**2] * 3),
        *([VELOCITY_MEASUREMENT_SIGMA_MPS**2] * 3),
    ])
    nis_values: list[float] = []
    accepted = 0
    rejected = 0

    timestamp_ns = 0
    increment_ns = round(DT_S * 1.0e9)
    for step_index in range(1, STEPS + 1):
        ideal_force_b = quat_to_rot(true_state.q_n_b).T @ (-gravity_n)
        accel_noise = rng.normal(0.0, config.accel_noise_density / np.sqrt(DT_S), 3)
        gyro_noise = rng.normal(0.0, config.gyro_noise_density / np.sqrt(DT_S), 3)
        observed_force = ideal_force_b + true_state.accel_bias_b + accel_noise
        observed_rate = true_state.gyro_bias_b + gyro_noise

        timestamp_ns += increment_ns
        propagation = core.propagate(ImuSample(timestamp_ns, observed_force, observed_rate))
        if not propagation["accepted"]:
            raise FloatingPointError(f"Propagation failed: {propagation}")

        true_state.position_n = true_state.position_n + true_state.velocity_n * DT_S
        true_state.timestamp_ns = timestamp_ns
        true_state.accel_bias_b = true_state.accel_bias_b + rng.normal(
            0.0, config.accel_bias_rw_density * np.sqrt(DT_S), 3
        )
        true_state.gyro_bias_b = true_state.gyro_bias_b + rng.normal(
            0.0, config.gyro_bias_rw_density * np.sqrt(DT_S), 3
        )

        if step_index % MEASUREMENT_EVERY_STEPS == 0:
            observed = np.concatenate((
                true_state.position_n + rng.normal(0.0, POSITION_MEASUREMENT_SIGMA_M, 3),
                true_state.velocity_n + rng.normal(0.0, VELOCITY_MEASUREMENT_SIGMA_MPS, 3),
            ))
            result = core.update(GnssMeasurement(
                id=f"trial_{trial_index:03d}_measurement_{step_index:03d}",
                timestamp_ns=timestamp_ns,
                kind=MeasurementKind.POSITION_VELOCITY,
                value=observed,
                covariance=measurement_covariance,
            ))
            if not np.isfinite(result["nis"]):
                raise FloatingPointError("Non-finite NIS")
            nis_values.append(float(result["nis"]))
            accepted += int(result["accepted"])
            rejected += int(not result["accepted"])

    error = state_error(core.state, true_state)
    if not np.all(np.isfinite(error)) or not np.all(np.isfinite(core.state.covariance)):
        raise FloatingPointError("Non-finite final error or covariance")
    nees = float(error @ np.linalg.solve(core.state.covariance, error))
    divergence = (not np.isfinite(nees) or np.linalg.norm(error[0:3]) > 50.0
                  or nees > 1.0e6)
    return {"nees": nees, "nis": nis_values, "accepted": accepted,
            "rejected": rejected, "divergence": divergence,
            "position_error_norm_m": float(np.linalg.norm(error[0:3]))}


def main() -> int:
    output_path = (Path(sys.argv[1]) if len(sys.argv) > 1
                   else Path(__file__).resolve().parents[1] / "results/monte_carlo_results.json")
    parent_sequence = np.random.SeedSequence(BASE_SEED)
    child_sequences = parent_sequence.spawn(TRIALS)
    nees_values = []
    nis_values = []
    divergence_count = 0
    numerical_failure_count = 0
    accepted_measurements = 0
    rejected_measurements = 0
    position_errors = []
    failure_details = []

    for trial_index, child in enumerate(child_sequences):
        try:
            result = run_trial(trial_index, child)
            nees_values.append(result["nees"])
            nis_values.extend(result["nis"])
            divergence_count += int(result["divergence"])
            accepted_measurements += result["accepted"]
            rejected_measurements += result["rejected"]
            position_errors.append(result["position_error_norm_m"])
        except Exception as exception:
            numerical_failure_count += 1
            failure_details.append({"trial": trial_index, "error": str(exception)})

    nees_array = np.asarray(nees_values)
    nis_array = np.asarray(nis_values)
    state_dimension = 15
    measurement_dimension = 6
    nees_individual_interval = interval(state_dimension)
    nis_individual_interval = interval(measurement_dimension)
    nees_mean_interval = mean_interval(len(nees_array), state_dimension)
    nis_mean_interval = mean_interval(len(nis_array), measurement_dimension)
    mean_nees = float(np.mean(nees_array)) if len(nees_array) else float("nan")
    mean_nis = float(np.mean(nis_array)) if len(nis_array) else float("nan")
    nees_coverage = float(np.mean(
        (nees_array >= nees_individual_interval[0]) & (nees_array <= nees_individual_interval[1])
    )) if len(nees_array) else 0.0
    nis_coverage = float(np.mean(
        (nis_array >= nis_individual_interval[0]) & (nis_array <= nis_individual_interval[1])
    )) if len(nis_array) else 0.0

    checks = [
        {"name": "all_trials_completed", "status": "passed" if len(nees_array) == TRIALS else "failed",
         "actual": len(nees_array), "expected": TRIALS},
        {"name": "mean_nees_in_95pct_chi_square_interval",
         "status": "passed" if nees_mean_interval[0] <= mean_nees <= nees_mean_interval[1] else "failed",
         "actual": mean_nees, "interval": nees_mean_interval},
        {"name": "mean_nis_in_95pct_chi_square_interval",
         "status": "passed" if nis_mean_interval[0] <= mean_nis <= nis_mean_interval[1] else "failed",
         "actual": mean_nis, "interval": nis_mean_interval},
        {"name": "no_divergence", "status": "passed" if divergence_count == 0 else "failed",
         "actual": divergence_count},
        {"name": "no_numerical_failure",
         "status": "passed" if numerical_failure_count == 0 else "failed",
         "actual": numerical_failure_count},
    ]
    overall_passed = all(check["status"] == "passed" for check in checks)
    result = {
        "schema_version": 1,
        "overall_status": "passed" if overall_passed else "failed",
        "experiment": {
            "trials": TRIALS,
            "steps_per_trial": STEPS,
            "duration_s": STEPS * DT_S,
            "dt_s": DT_S,
            "measurement_interval_steps": MEASUREMENT_EVERY_STEPS,
            "state_dimension": state_dimension,
            "measurement_dimension": measurement_dimension,
            "seed_strategy": "NumPy SeedSequence(base_seed).spawn(trials), one PCG64 stream per trial",
            "base_seed": BASE_SEED,
            "process_noise": {
                "accel_noise_density_mps2_sqrt_hz": CoreConfig().accel_noise_density,
                "gyro_noise_density_radps_sqrt_hz": CoreConfig().gyro_noise_density,
                "accel_bias_rw_density_mps3_sqrt_hz": CoreConfig().accel_bias_rw_density,
                "gyro_bias_rw_density_radps2_sqrt_hz": CoreConfig().gyro_bias_rw_density,
            },
            "measurement_noise": {
                "position_sigma_m": POSITION_MEASUREMENT_SIGMA_M,
                "velocity_sigma_mps": VELOCITY_MEASUREMENT_SIGMA_MPS,
            },
            "note": "Noise values are the declared oracle defaults and were not tuned to this run.",
        },
        "nees": {
            "sample_count": len(nees_array), "degrees_of_freedom": state_dimension,
            "mean": mean_nees, "median": float(np.median(nees_array)),
            "individual_95pct_chi_square_interval": nees_individual_interval,
            "mean_95pct_chi_square_interval": nees_mean_interval,
            "empirical_individual_coverage": nees_coverage,
            "minimum": float(np.min(nees_array)), "maximum": float(np.max(nees_array)),
        },
        "nis": {
            "sample_count": len(nis_array), "degrees_of_freedom": measurement_dimension,
            "mean": mean_nis, "median": float(np.median(nis_array)),
            "individual_95pct_chi_square_interval": nis_individual_interval,
            "mean_95pct_chi_square_interval": nis_mean_interval,
            "empirical_individual_coverage": nis_coverage,
            "minimum": float(np.min(nis_array)), "maximum": float(np.max(nis_array)),
            "accepted_measurements": accepted_measurements,
            "rejected_measurements": rejected_measurements,
            "acceptance_rate": accepted_measurements / max(1, accepted_measurements + rejected_measurements),
        },
        "position_error_norm_m": {
            "mean": float(np.mean(position_errors)), "maximum": float(np.max(position_errors)),
        },
        "divergence_count": divergence_count,
        "numerical_failure_count": numerical_failure_count,
        "failure_details": failure_details,
        "checks": checks,
    }
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"overall_status": result["overall_status"],
                      "completed_trials": len(nees_array), "mean_nees": mean_nees,
                      "mean_nees_interval": nees_mean_interval, "mean_nis": mean_nis,
                      "mean_nis_interval": nis_mean_interval, "nees_coverage": nees_coverage,
                      "nis_coverage": nis_coverage, "divergence_count": divergence_count,
                      "numerical_failure_count": numerical_failure_count}, indent=2))
    return 0 if overall_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
