"""Independent NumPy reference for the S2 canonical 15-state ESKF.

This module deliberately contains no binding, subprocess call, or import of the
C++ implementation.  Both implementations consume the same CSV fixtures, but
the SO(3), mechanization, covariance, update, injection, and reset operations
are written independently here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Set

import numpy as np


POSITION = slice(0, 3)
VELOCITY = slice(3, 6)
ATTITUDE = slice(6, 9)
ACCEL_BIAS = slice(9, 12)
GYRO_BIAS = slice(12, 15)


def skew(vector: np.ndarray) -> np.ndarray:
    x, y, z = np.asarray(vector, dtype=np.float64)
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]], dtype=np.float64)


def so3_exp(rotation_vector: np.ndarray) -> np.ndarray:
    rotation_vector = np.asarray(rotation_vector, dtype=np.float64)
    angle = float(np.linalg.norm(rotation_vector))
    cross = skew(rotation_vector)
    if angle < 1.0e-8:
        return np.eye(3) + cross + 0.5 * cross @ cross
    a = np.sin(angle) / angle
    b = (1.0 - np.cos(angle)) / (angle * angle)
    return np.eye(3) + a * cross + b * cross @ cross


def so3_log(rotation: np.ndarray) -> np.ndarray:
    rotation = np.asarray(rotation, dtype=np.float64)
    cosine = float(np.clip((np.trace(rotation) - 1.0) * 0.5, -1.0, 1.0))
    angle = float(np.arccos(cosine))
    vee = np.array(
        [
            rotation[2, 1] - rotation[1, 2],
            rotation[0, 2] - rotation[2, 0],
            rotation[1, 0] - rotation[0, 1],
        ],
        dtype=np.float64,
    )
    if angle < 1.0e-8:
        return 0.5 * vee
    return (0.5 * angle / np.sin(angle)) * vee


def right_jacobian_so3(rotation_vector: np.ndarray) -> np.ndarray:
    rotation_vector = np.asarray(rotation_vector, dtype=np.float64)
    angle = float(np.linalg.norm(rotation_vector))
    cross = skew(rotation_vector)
    if angle < 1.0e-8:
        return np.eye(3) - 0.5 * cross + (1.0 / 6.0) * cross @ cross
    a = (1.0 - np.cos(angle)) / (angle * angle)
    b = (angle - np.sin(angle)) / (angle * angle * angle)
    return np.eye(3) - a * cross + b * cross @ cross


def quat_normalize(quaternion_wxyz: np.ndarray) -> np.ndarray:
    q = np.asarray(quaternion_wxyz, dtype=np.float64).copy()
    norm = float(np.linalg.norm(q))
    if not np.isfinite(norm) or norm <= 0.0:
        raise ValueError("Quaternion norm must be finite and positive")
    q /= norm
    if q[0] < 0.0:
        q *= -1.0
    return q


def quat_multiply(lhs_wxyz: np.ndarray, rhs_wxyz: np.ndarray) -> np.ndarray:
    w1, x1, y1, z1 = np.asarray(lhs_wxyz, dtype=np.float64)
    w2, x2, y2, z2 = np.asarray(rhs_wxyz, dtype=np.float64)
    return quat_normalize(
        np.array(
            [
                w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            ],
            dtype=np.float64,
        )
    )


def quat_exp(rotation_vector: np.ndarray) -> np.ndarray:
    rotation_vector = np.asarray(rotation_vector, dtype=np.float64)
    angle = float(np.linalg.norm(rotation_vector))
    if angle < 1.0e-12:
        return quat_normalize(
            np.concatenate(([1.0 - angle * angle / 8.0], 0.5 * rotation_vector))
        )
    half = 0.5 * angle
    return quat_normalize(
        np.concatenate(([np.cos(half)], np.sin(half) * rotation_vector / angle))
    )


def quat_to_rot(quaternion_wxyz: np.ndarray) -> np.ndarray:
    w, x, y, z = quat_normalize(quaternion_wxyz)
    return np.array(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - w * z), 2.0 * (x * z + w * y)],
            [2.0 * (x * y + w * z), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - w * x)],
            [2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def rot_to_quat(rotation: np.ndarray) -> np.ndarray:
    """Convert a proper rotation matrix to scalar-first Hamilton coefficients."""
    r = np.asarray(rotation, dtype=np.float64)
    trace = float(np.trace(r))
    if trace > 0.0:
        s = 2.0 * np.sqrt(trace + 1.0)
        q = np.array([0.25 * s, (r[2, 1] - r[1, 2]) / s,
                      (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s])
    else:
        axis = int(np.argmax(np.diag(r)))
        if axis == 0:
            s = 2.0 * np.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2])
            q = np.array([(r[2, 1] - r[1, 2]) / s, 0.25 * s,
                          (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s])
        elif axis == 1:
            s = 2.0 * np.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2])
            q = np.array([(r[0, 2] - r[2, 0]) / s, (r[0, 1] + r[1, 0]) / s,
                          0.25 * s, (r[1, 2] + r[2, 1]) / s])
        else:
            s = 2.0 * np.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1])
            q = np.array([(r[1, 0] - r[0, 1]) / s, (r[0, 2] + r[2, 0]) / s,
                          (r[1, 2] + r[2, 1]) / s, 0.25 * s])
    return quat_normalize(q)


def rotation_distance(lhs_wxyz: np.ndarray, rhs_wxyz: np.ndarray) -> float:
    relative = quat_to_rot(lhs_wxyz).T @ quat_to_rot(rhs_wxyz)
    return float(np.linalg.norm(so3_log(relative)))


@dataclass
class NominalState:
    timestamp_ns: int = 0
    position_n: np.ndarray = field(default_factory=lambda: np.zeros(3))
    velocity_n: np.ndarray = field(default_factory=lambda: np.zeros(3))
    q_n_b: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0, 0.0]))
    accel_bias_b: np.ndarray = field(default_factory=lambda: np.zeros(3))
    gyro_bias_b: np.ndarray = field(default_factory=lambda: np.zeros(3))
    covariance: np.ndarray = field(default_factory=lambda: np.eye(15))

    def copy(self) -> "NominalState":
        return NominalState(
            timestamp_ns=int(self.timestamp_ns),
            position_n=np.asarray(self.position_n, dtype=np.float64).copy(),
            velocity_n=np.asarray(self.velocity_n, dtype=np.float64).copy(),
            q_n_b=np.asarray(self.q_n_b, dtype=np.float64).copy(),
            accel_bias_b=np.asarray(self.accel_bias_b, dtype=np.float64).copy(),
            gyro_bias_b=np.asarray(self.gyro_bias_b, dtype=np.float64).copy(),
            covariance=np.asarray(self.covariance, dtype=np.float64).copy(),
        )


@dataclass(frozen=True)
class ImuSample:
    timestamp_ns: int
    specific_force_b: np.ndarray
    angular_rate_b: np.ndarray


class MeasurementKind(str, Enum):
    POSITION = "position"
    VELOCITY = "velocity"
    POSITION_VELOCITY = "position_velocity"


@dataclass(frozen=True)
class GnssMeasurement:
    id: str
    timestamp_ns: int
    kind: MeasurementKind
    value: np.ndarray
    covariance: np.ndarray


@dataclass(frozen=True)
class CoreConfig:
    gravity_n: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 9.80665]))
    accel_noise_density: float = 0.03
    gyro_noise_density: float = 0.0015
    accel_bias_rw_density: float = 0.0008
    gyro_bias_rw_density: float = 0.00004
    expected_dt_s: float = 0.01
    gap_factor: float = 2.5
    min_dt_s: float = 1.0e-6
    max_dt_s: float = 0.20
    gate_chi2_3: float = 11.344866730144373
    gate_chi2_6: float = 16.811893829770927


def state_error(nominal: NominalState, truth: NominalState) -> np.ndarray:
    error = np.zeros(15)
    error[POSITION] = truth.position_n - nominal.position_n
    error[VELOCITY] = truth.velocity_n - nominal.velocity_n
    error[ATTITUDE] = so3_log(quat_to_rot(nominal.q_n_b).T @ quat_to_rot(truth.q_n_b))
    error[ACCEL_BIAS] = truth.accel_bias_b - nominal.accel_bias_b
    error[GYRO_BIAS] = truth.gyro_bias_b - nominal.gyro_bias_b
    return error


def inject_error(state: NominalState, error: np.ndarray) -> None:
    error = np.asarray(error, dtype=np.float64)
    state.position_n += error[POSITION]
    state.velocity_n += error[VELOCITY]
    state.q_n_b = quat_multiply(state.q_n_b, quat_exp(error[ATTITUDE]))
    state.accel_bias_b += error[ACCEL_BIAS]
    state.gyro_bias_b += error[GYRO_BIAS]


def reset_jacobian(injected_attitude_error: np.ndarray) -> np.ndarray:
    jacobian = np.eye(15)
    jacobian[ATTITUDE, ATTITUDE] = right_jacobian_so3(injected_attitude_error)
    return jacobian


def linearize_propagation(
    state: NominalState, sample: ImuSample, dt_s: float, config: CoreConfig
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    corrected_force = np.asarray(sample.specific_force_b) - state.accel_bias_b
    corrected_rate = np.asarray(sample.angular_rate_b) - state.gyro_bias_b
    half_rotation = 0.5 * corrected_rate * dt_s
    full_rotation = corrected_rate * dt_s
    delta_half = so3_exp(half_rotation)
    delta_full = so3_exp(full_rotation)
    jr_half = right_jacobian_so3(half_rotation)
    jr_full = right_jacobian_so3(full_rotation)
    rotation_mid = quat_to_rot(state.q_n_b) @ delta_half

    accel_theta = -rotation_mid @ skew(corrected_force) @ delta_half.T
    accel_accel_bias = -rotation_mid
    accel_gyro_bias = rotation_mid @ skew(corrected_force) @ jr_half * (0.5 * dt_s)

    phi = np.eye(15)
    phi[POSITION, VELOCITY] = np.eye(3) * dt_s
    phi[POSITION, ATTITUDE] = 0.5 * accel_theta * dt_s**2
    phi[POSITION, ACCEL_BIAS] = 0.5 * accel_accel_bias * dt_s**2
    phi[POSITION, GYRO_BIAS] = 0.5 * accel_gyro_bias * dt_s**2
    phi[VELOCITY, ATTITUDE] = accel_theta * dt_s
    phi[VELOCITY, ACCEL_BIAS] = accel_accel_bias * dt_s
    phi[VELOCITY, GYRO_BIAS] = accel_gyro_bias * dt_s
    phi[ATTITUDE, ATTITUDE] = delta_full.T
    phi[ATTITUDE, GYRO_BIAS] = -jr_full * dt_s

    noise_map = np.zeros((15, 12))
    noise_map[POSITION, 0:3] = -0.5 * rotation_mid * dt_s
    noise_map[VELOCITY, 0:3] = -rotation_mid
    noise_map[POSITION, 3:6] = 0.25 * rotation_mid @ skew(corrected_force) @ jr_half * dt_s**2
    noise_map[VELOCITY, 3:6] = 0.5 * rotation_mid @ skew(corrected_force) @ jr_half * dt_s
    noise_map[ATTITUDE, 3:6] = -jr_full
    noise_map[ACCEL_BIAS, 6:9] = np.eye(3)
    noise_map[GYRO_BIAS, 9:12] = np.eye(3)

    densities = np.array(
        [
            *([config.accel_noise_density] * 3),
            *([config.gyro_noise_density] * 3),
            *([config.accel_bias_rw_density] * 3),
            *([config.gyro_bias_rw_density] * 3),
        ]
    )
    driving_covariance = np.diag(densities**2 * dt_s)
    q_discrete = noise_map @ driving_covariance @ noise_map.T
    q_discrete = 0.5 * (q_discrete + q_discrete.T)
    return phi, q_discrete, rotation_mid, corrected_force, corrected_rate


def propagate_nominal_only(
    state: NominalState, sample: ImuSample, dt_s: float, config: CoreConfig
) -> NominalState:
    _, _, rotation_mid, corrected_force, corrected_rate = linearize_propagation(
        state, sample, dt_s, config
    )
    output = state.copy()
    acceleration_n = rotation_mid @ corrected_force + np.asarray(config.gravity_n)
    output.position_n = state.position_n + state.velocity_n * dt_s + 0.5 * acceleration_n * dt_s**2
    output.velocity_n = state.velocity_n + acceleration_n * dt_s
    output.q_n_b = quat_multiply(state.q_n_b, quat_exp(corrected_rate * dt_s))
    output.timestamp_ns = int(sample.timestamp_ns)
    return output


def measurement_jacobian(kind: MeasurementKind) -> np.ndarray:
    if kind == MeasurementKind.POSITION:
        h = np.zeros((3, 15))
        h[:, POSITION] = np.eye(3)
        return h
    if kind == MeasurementKind.VELOCITY:
        h = np.zeros((3, 15))
        h[:, VELOCITY] = np.eye(3)
        return h
    h = np.zeros((6, 15))
    h[0:3, POSITION] = np.eye(3)
    h[3:6, VELOCITY] = np.eye(3)
    return h


class NavigationCore:
    def __init__(self, initial_state: NominalState, config: CoreConfig | None = None):
        self.state = initial_state.copy()
        self.state.q_n_b = quat_normalize(self.state.q_n_b)
        self.state.covariance = 0.5 * (self.state.covariance + self.state.covariance.T)
        self.config = config or CoreConfig()
        self.consumed_measurement_ids: Set[str] = set()

    def propagate(self, sample: ImuSample) -> dict:
        if not np.all(np.isfinite(sample.specific_force_b)) or not np.all(
            np.isfinite(sample.angular_rate_b)
        ):
            return {"accepted": False, "gap_detected": False, "dt_s": 0.0,
                    "status": "invalid_nonfinite_imu"}
        if int(sample.timestamp_ns) <= int(self.state.timestamp_ns):
            return {"accepted": False, "gap_detected": False, "dt_s": 0.0,
                    "status": "invalid_nonmonotonic_timestamp"}
        dt_s = (int(sample.timestamp_ns) - int(self.state.timestamp_ns)) * 1.0e-9
        if not np.isfinite(dt_s) or dt_s < self.config.min_dt_s or dt_s > self.config.max_dt_s:
            return {"accepted": False, "gap_detected": False, "dt_s": dt_s,
                    "status": "invalid_dt"}

        phi, q_discrete, _, _, _ = linearize_propagation(
            self.state, sample, dt_s, self.config
        )
        propagated = propagate_nominal_only(self.state, sample, dt_s, self.config)
        propagated.covariance = phi @ self.state.covariance @ phi.T + q_discrete
        propagated.covariance = 0.5 * (propagated.covariance + propagated.covariance.T)
        if not (
            np.all(np.isfinite(propagated.position_n))
            and np.all(np.isfinite(propagated.velocity_n))
            and np.all(np.isfinite(propagated.q_n_b))
            and np.all(np.isfinite(propagated.covariance))
        ):
            return {"accepted": False, "gap_detected": False, "dt_s": dt_s,
                    "status": "numerical_failure"}
        self.state = propagated
        gap = dt_s > self.config.gap_factor * self.config.expected_dt_s
        return {"accepted": True, "gap_detected": gap, "dt_s": dt_s,
                "status": "accepted_gap" if gap else "accepted"}

    def update(self, measurement: GnssMeasurement) -> dict:
        if not measurement.id:
            return self._measurement_result(status="invalid_empty_measurement_id")
        if measurement.id in self.consumed_measurement_ids:
            return self._measurement_result(status="duplicate_measurement_id", duplicate=True)
        self.consumed_measurement_ids.add(measurement.id)
        if int(measurement.timestamp_ns) != int(self.state.timestamp_ns):
            return self._measurement_result(status="measurement_timestamp_mismatch")

        dimension = 6 if measurement.kind == MeasurementKind.POSITION_VELOCITY else 3
        if measurement.kind == MeasurementKind.POSITION:
            predicted = self.state.position_n
        elif measurement.kind == MeasurementKind.VELOCITY:
            predicted = self.state.velocity_n
        else:
            predicted = np.concatenate((self.state.position_n, self.state.velocity_n))
        observed = np.asarray(measurement.value, dtype=np.float64)[:dimension]
        measurement_covariance = np.asarray(measurement.covariance, dtype=np.float64)[:dimension, :dimension]
        if not np.all(np.isfinite(observed)) or not np.all(np.isfinite(measurement_covariance)):
            return self._measurement_result(
                status="invalid_nonfinite_measurement", dimension=dimension
            )

        h = measurement_jacobian(measurement.kind)
        innovation = observed - predicted
        innovation_covariance = h @ self.state.covariance @ h.T + measurement_covariance
        try:
            np.linalg.cholesky(innovation_covariance)
            solved = np.linalg.solve(innovation_covariance, innovation)
        except np.linalg.LinAlgError:
            return self._measurement_result(
                status="invalid_innovation_covariance", dimension=dimension,
                innovation=innovation
            )
        nis = float(innovation @ solved)
        gate = self.config.gate_chi2_6 if dimension == 6 else self.config.gate_chi2_3
        if not np.isfinite(nis) or nis > gate:
            return self._measurement_result(
                status="rejected_nis_gate", dimension=dimension,
                innovation=innovation, nis=nis
            )

        gain = np.linalg.solve(innovation_covariance, h @ self.state.covariance).T
        correction = gain @ innovation
        identity = np.eye(15)
        left = identity - gain @ h
        joseph = left @ self.state.covariance @ left.T + gain @ measurement_covariance @ gain.T
        joseph = 0.5 * (joseph + joseph.T)
        inject_error(self.state, correction)
        reset = reset_jacobian(correction[ATTITUDE])
        self.state.covariance = reset @ joseph @ reset.T
        self.state.covariance = 0.5 * (self.state.covariance + self.state.covariance.T)
        if not np.all(np.isfinite(self.state.covariance)):
            raise FloatingPointError("Non-finite covariance after accepted update")
        return self._measurement_result(
            status="accepted", accepted=True, dimension=dimension,
            innovation=innovation, nis=nis
        )

    @staticmethod
    def _measurement_result(
        *, status: str, accepted: bool = False, duplicate: bool = False,
        dimension: int = 0, innovation: np.ndarray | None = None,
        nis: float = float("nan")
    ) -> dict:
        padded = np.zeros(6)
        if innovation is not None:
            padded[: len(innovation)] = innovation
        return {
            "accepted": accepted,
            "duplicate": duplicate,
            "dimension": dimension,
            "nis": nis,
            "innovation": padded,
            "status": status,
        }


def default_initial_covariance() -> np.ndarray:
    standard_deviations = np.array(
        [
            *([1.0] * 3),
            *([0.5] * 3),
            *([np.deg2rad(5.0)] * 3),
            *([0.05] * 3),
            *([0.005] * 3),
        ]
    )
    return np.diag(standard_deviations**2)
