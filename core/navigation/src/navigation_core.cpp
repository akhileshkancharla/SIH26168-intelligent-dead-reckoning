#include "s2_oracle/navigation_core.hpp"

#include <Eigen/Cholesky>

#include <cmath>
#include <stdexcept>

namespace s2 {

PropagationLinearization linearizePropagation(const NominalState& state,
                                              const ImuSample& sample,
                                              double dt_s,
                                              const CoreConfig& config) {
    PropagationLinearization result;
    result.corrected_force_b = sample.specific_force_b - state.accel_bias_b;
    result.corrected_rate_b = sample.angular_rate_b - state.gyro_bias_b;

    const Vec3 half_rotation = 0.5 * result.corrected_rate_b * dt_s;
    const Vec3 full_rotation = result.corrected_rate_b * dt_s;
    const Mat3 delta_half = so3Exp(half_rotation);
    const Mat3 delta_full = so3Exp(full_rotation);
    const Mat3 right_jacobian_half = rightJacobianSo3(half_rotation);
    const Mat3 right_jacobian_full = rightJacobianSo3(full_rotation);

    const Mat3 rotation_n_b = state.q_n_b.toRotationMatrix();
    result.rotation_mid_n_b = rotation_n_b * delta_half;

    const Mat3 accel_theta =
        -result.rotation_mid_n_b * skew(result.corrected_force_b) * delta_half.transpose();
    const Mat3 accel_accel_bias = -result.rotation_mid_n_b;
    const Mat3 accel_gyro_bias = result.rotation_mid_n_b
                                * skew(result.corrected_force_b)
                                * right_jacobian_half * (0.5 * dt_s);

    result.phi.setIdentity();
    result.phi.block<3, 3>(kPosition, kVelocity) = Mat3::Identity() * dt_s;
    result.phi.block<3, 3>(kPosition, kAttitude) = 0.5 * accel_theta * dt_s * dt_s;
    result.phi.block<3, 3>(kPosition, kAccelBias) =
        0.5 * accel_accel_bias * dt_s * dt_s;
    result.phi.block<3, 3>(kPosition, kGyroBias) =
        0.5 * accel_gyro_bias * dt_s * dt_s;
    result.phi.block<3, 3>(kVelocity, kAttitude) = accel_theta * dt_s;
    result.phi.block<3, 3>(kVelocity, kAccelBias) = accel_accel_bias * dt_s;
    result.phi.block<3, 3>(kVelocity, kGyroBias) = accel_gyro_bias * dt_s;
    result.phi.block<3, 3>(kAttitude, kAttitude) = delta_full.transpose();
    result.phi.block<3, 3>(kAttitude, kGyroBias) = -right_jacobian_full * dt_s;

    // The 12 driving increments are [integrated accel white noise,
    // integrated gyro white noise, accel-bias RW, gyro-bias RW].  Their
    // covariance is density^2 * dt.  L below maps those increments into the
    // right-invariant local error state used by the deterministic update.
    Mat15x12 L = Mat15x12::Zero();
    L.block<3, 3>(kPosition, 0) = -0.5 * result.rotation_mid_n_b * dt_s;
    L.block<3, 3>(kVelocity, 0) = -result.rotation_mid_n_b;
    L.block<3, 3>(kPosition, 3) = 0.25 * result.rotation_mid_n_b
                                           * skew(result.corrected_force_b)
                                           * right_jacobian_half * dt_s * dt_s;
    L.block<3, 3>(kVelocity, 3) = 0.5 * result.rotation_mid_n_b
                                           * skew(result.corrected_force_b)
                                           * right_jacobian_half * dt_s;
    L.block<3, 3>(kAttitude, 3) = -right_jacobian_full;
    L.block<3, 3>(kAccelBias, 6) = Mat3::Identity();
    L.block<3, 3>(kGyroBias, 9) = Mat3::Identity();

    Eigen::Matrix<double, 12, 12> driving_covariance =
        Eigen::Matrix<double, 12, 12>::Zero();
    driving_covariance.block<3, 3>(0, 0).diagonal().setConstant(
        config.accel_noise_density * config.accel_noise_density * dt_s);
    driving_covariance.block<3, 3>(3, 3).diagonal().setConstant(
        config.gyro_noise_density * config.gyro_noise_density * dt_s);
    driving_covariance.block<3, 3>(6, 6).diagonal().setConstant(
        config.accel_bias_rw_density * config.accel_bias_rw_density * dt_s);
    driving_covariance.block<3, 3>(9, 9).diagonal().setConstant(
        config.gyro_bias_rw_density * config.gyro_bias_rw_density * dt_s);

    result.q_discrete = L * driving_covariance * L.transpose();
    result.q_discrete = 0.5 * (result.q_discrete + result.q_discrete.transpose());
    return result;
}

NominalState propagateNominalOnly(const NominalState& state,
                                  const ImuSample& sample,
                                  double dt_s,
                                  const CoreConfig& config) {
    const PropagationLinearization linearization =
        linearizePropagation(state, sample, dt_s, config);
    NominalState output = state;

    const Vec3 acceleration_n = linearization.rotation_mid_n_b
                              * linearization.corrected_force_b
                              + config.gravity_n;
    output.position_n = state.position_n + state.velocity_n * dt_s
                      + 0.5 * acceleration_n * dt_s * dt_s;
    output.velocity_n = state.velocity_n + acceleration_n * dt_s;
    output.q_n_b = canonicalQuaternion(
        state.q_n_b * quaternionExp(linearization.corrected_rate_b * dt_s));
    output.timestamp_ns = sample.timestamp_ns;
    return output;
}

Mat15 resetJacobian(const Vec3& injected_attitude_error) {
    Mat15 jacobian = Mat15::Identity();
    jacobian.block<3, 3>(kAttitude, kAttitude) =
        rightJacobianSo3(injected_attitude_error);
    return jacobian;
}

NavigationCore::NavigationCore(NominalState initial_state, CoreConfig config)
    : state_(std::move(initial_state)), config_(std::move(config)) {
    state_.q_n_b = canonicalQuaternion(state_.q_n_b);
    state_.covariance = 0.5 * (state_.covariance + state_.covariance.transpose());
}

PropagationResult NavigationCore::propagate(const ImuSample& sample) {
    PropagationResult result;
    if (!sample.specific_force_b.allFinite() || !sample.angular_rate_b.allFinite()) {
        result.status = "invalid_nonfinite_imu";
        return result;
    }
    if (sample.timestamp_ns <= state_.timestamp_ns) {
        result.status = "invalid_nonmonotonic_timestamp";
        return result;
    }

    const double dt_s = static_cast<double>(sample.timestamp_ns - state_.timestamp_ns) * 1.0e-9;
    result.dt_s = dt_s;
    if (!std::isfinite(dt_s) || dt_s < config_.min_dt_s || dt_s > config_.max_dt_s) {
        result.status = "invalid_dt";
        return result;
    }

    const PropagationLinearization linearization =
        linearizePropagation(state_, sample, dt_s, config_);
    NominalState propagated = propagateNominalOnly(state_, sample, dt_s, config_);
    propagated.covariance = linearization.phi * state_.covariance
                          * linearization.phi.transpose()
                          + linearization.q_discrete;
    propagated.covariance =
        0.5 * (propagated.covariance + propagated.covariance.transpose());

    if (!propagated.position_n.allFinite() || !propagated.velocity_n.allFinite()
        || !propagated.q_n_b.coeffs().allFinite()
        || !propagated.covariance.allFinite()) {
        result.status = "numerical_failure";
        return result;
    }

    state_ = std::move(propagated);
    result.accepted = true;
    result.gap_detected = dt_s > config_.gap_factor * config_.expected_dt_s;
    result.status = result.gap_detected ? "accepted_gap" : "accepted";
    return result;
}

MeasurementResult NavigationCore::update(const GnssMeasurement& measurement) {
    MeasurementResult result;
    if (measurement.id.empty()) {
        result.status = "invalid_empty_measurement_id";
        return result;
    }
    if (consumed_measurement_ids_.find(measurement.id) != consumed_measurement_ids_.end()) {
        result.duplicate = true;
        result.status = "duplicate_measurement_id";
        return result;
    }

    // A first presentation consumes the evidence ID regardless of whether the
    // sample is subsequently gated. This prevents retrying one physical fix
    // with altered covariance until it is accepted.
    consumed_measurement_ids_.insert(measurement.id);

    if (measurement.timestamp_ns != state_.timestamp_ns) {
        result.status = "measurement_timestamp_mismatch";
        return result;
    }

    if (measurement.kind == MeasurementKind::PositionVelocity) {
        return updateFixed<6>(measurement);
    }
    return updateFixed<3>(measurement);
}

MeasurementResult NavigationCore::screen(const GnssMeasurement& measurement) const {
    MeasurementResult result;
    if (measurement.id.empty()) {
        result.status = "invalid_empty_measurement_id";
        return result;
    }
    if (consumed_measurement_ids_.contains(measurement.id)) {
        result.duplicate = true;
        result.status = "duplicate_measurement_id";
        return result;
    }
    if (measurement.timestamp_ns != state_.timestamp_ns) {
        result.status = "measurement_timestamp_mismatch";
        return result;
    }
    return measurement.kind == MeasurementKind::PositionVelocity
        ? screenFixed<6>(measurement)
        : screenFixed<3>(measurement);
}

template<int M>
MeasurementResult NavigationCore::screenFixed(const GnssMeasurement& measurement) const {
    MeasurementResult result;
    result.dimension = M;

    Eigen::Matrix<double, M, 1> predicted;
    if constexpr (M == 3) {
        predicted = measurement.kind == MeasurementKind::Position
                  ? state_.position_n : state_.velocity_n;
    } else {
        predicted.template segment<3>(0) = state_.position_n;
        predicted.template segment<3>(3) = state_.velocity_n;
    }

    const Eigen::Matrix<double, M, 1> observed = measurement.value.template head<M>();
    const Eigen::Matrix<double, M, M> measurement_covariance =
        measurement.covariance.template topLeftCorner<M, M>();
    if (!observed.allFinite() || !measurement_covariance.allFinite()) {
        result.status = "invalid_nonfinite_measurement";
        return result;
    }

    const auto H = measurementJacobian<M>(measurement.kind);
    const Eigen::Matrix<double, M, 1> innovation = observed - predicted;
    const Eigen::Matrix<double, M, M> innovation_covariance =
        H * state_.covariance * H.transpose() + measurement_covariance;
    const Eigen::LDLT<Eigen::Matrix<double, M, M>> decomposition(innovation_covariance);
    if (decomposition.info() != Eigen::Success || !decomposition.isPositive()) {
        result.status = "invalid_innovation_covariance";
        return result;
    }

    const Eigen::Matrix<double, M, 1> solved = decomposition.solve(innovation);
    result.nis = innovation.dot(solved);
    result.innovation.template head<M>() = innovation;
    const double gate = M == 3 ? config_.gate_chi2_3 : config_.gate_chi2_6;
    if (!std::isfinite(result.nis) || result.nis > gate) {
        result.status = "rejected_nis_gate";
        return result;
    }
    result.status = "screen_passed";
    return result;
}

template<int M>
MeasurementResult NavigationCore::updateFixed(const GnssMeasurement& measurement) {
    MeasurementResult result = screenFixed<M>(measurement);
    if (result.status != "screen_passed") return result;

    const auto H = measurementJacobian<M>(measurement.kind);
    const Eigen::Matrix<double, M, 1> innovation =
        result.innovation.template head<M>();
    const Eigen::Matrix<double, M, M> measurement_covariance =
        measurement.covariance.template topLeftCorner<M, M>();
    const Eigen::Matrix<double, M, M> innovation_covariance =
        H * state_.covariance * H.transpose() + measurement_covariance;
    const Eigen::LDLT<Eigen::Matrix<double, M, M>> decomposition(innovation_covariance);

    const Eigen::Matrix<double, M, M> inverse_innovation_covariance =
        decomposition.solve(Eigen::Matrix<double, M, M>::Identity());
    const Eigen::Matrix<double, 15, M> gain =
        state_.covariance * H.transpose() * inverse_innovation_covariance;
    const Vec15 correction = gain * innovation;

    const Mat15 identity = Mat15::Identity();
    const Mat15 left = identity - gain * H;
    Mat15 joseph_covariance = left * state_.covariance * left.transpose()
                              + gain * measurement_covariance * gain.transpose();
    joseph_covariance = 0.5 * (joseph_covariance + joseph_covariance.transpose());

    injectError(state_, correction);
    const Mat15 reset = resetJacobian(correction.segment<3>(kAttitude));
    state_.covariance = reset * joseph_covariance * reset.transpose();
    state_.covariance = 0.5 * (state_.covariance + state_.covariance.transpose());

    if (!state_.covariance.allFinite() || !state_.q_n_b.coeffs().allFinite()) {
        throw std::runtime_error("Non-finite state after accepted measurement update");
    }

    result.accepted = true;
    result.status = "accepted";
    return result;
}

template MeasurementResult NavigationCore::screenFixed<3>(const GnssMeasurement&) const;
template MeasurementResult NavigationCore::screenFixed<6>(const GnssMeasurement&) const;
template MeasurementResult NavigationCore::updateFixed<3>(const GnssMeasurement&);
template MeasurementResult NavigationCore::updateFixed<6>(const GnssMeasurement&);

}  // namespace s2
