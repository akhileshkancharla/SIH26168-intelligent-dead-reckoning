#pragma once

#include "s2_oracle/types.hpp"

#include <algorithm>
#include <cmath>

namespace s2 {

inline Mat3 skew(const Vec3& vector) {
    Mat3 matrix;
    matrix << 0.0, -vector.z(), vector.y(),
              vector.z(), 0.0, -vector.x(),
              -vector.y(), vector.x(), 0.0;
    return matrix;
}

inline Mat3 so3Exp(const Vec3& rotation_vector) {
    const double angle = rotation_vector.norm();
    const Mat3 K = skew(rotation_vector);
    if (angle < 1.0e-8) {
        return Mat3::Identity() + K + 0.5 * K * K;
    }
    const double a = std::sin(angle) / angle;
    const double b = (1.0 - std::cos(angle)) / (angle * angle);
    return Mat3::Identity() + a * K + b * K * K;
}

inline Vec3 so3Log(const Mat3& rotation) {
    const double cosine = std::clamp((rotation.trace() - 1.0) * 0.5, -1.0, 1.0);
    const double angle = std::acos(cosine);
    Vec3 vee;
    vee << rotation(2, 1) - rotation(1, 2),
           rotation(0, 2) - rotation(2, 0),
           rotation(1, 0) - rotation(0, 1);
    if (angle < 1.0e-8) {
        return 0.5 * vee;
    }
    return (0.5 * angle / std::sin(angle)) * vee;
}

inline Mat3 rightJacobianSo3(const Vec3& rotation_vector) {
    const double angle = rotation_vector.norm();
    const Mat3 K = skew(rotation_vector);
    if (angle < 1.0e-8) {
        return Mat3::Identity() - 0.5 * K + (1.0 / 6.0) * K * K;
    }
    const double a = (1.0 - std::cos(angle)) / (angle * angle);
    const double b = (angle - std::sin(angle)) / (angle * angle * angle);
    return Mat3::Identity() - a * K + b * K * K;
}

inline Eigen::Quaterniond canonicalQuaternion(const Eigen::Quaterniond& input) {
    Eigen::Quaterniond q = input.normalized();
    if (q.w() < 0.0) {
        q.coeffs() *= -1.0;
    }
    return q;
}

inline Eigen::Quaterniond quaternionExp(const Vec3& rotation_vector) {
    return canonicalQuaternion(Eigen::Quaterniond(so3Exp(rotation_vector)));
}

inline Vec3 quaternionLog(const Eigen::Quaterniond& quaternion) {
    return so3Log(canonicalQuaternion(quaternion).toRotationMatrix());
}

inline Eigen::Quaterniond quaternionFromWxyz(double w, double x, double y, double z) {
    return canonicalQuaternion(Eigen::Quaterniond(w, x, y, z));
}

inline Vec15 stateError(const NominalState& nominal, const NominalState& truth) {
    Vec15 error = Vec15::Zero();
    error.segment<3>(kPosition) = truth.position_n - nominal.position_n;
    error.segment<3>(kVelocity) = truth.velocity_n - nominal.velocity_n;
    const Mat3 relative = nominal.q_n_b.toRotationMatrix().transpose()
                        * truth.q_n_b.toRotationMatrix();
    error.segment<3>(kAttitude) = so3Log(relative);
    error.segment<3>(kAccelBias) = truth.accel_bias_b - nominal.accel_bias_b;
    error.segment<3>(kGyroBias) = truth.gyro_bias_b - nominal.gyro_bias_b;
    return error;
}

inline void injectError(NominalState& state, const Vec15& error) {
    state.position_n += error.segment<3>(kPosition);
    state.velocity_n += error.segment<3>(kVelocity);
    state.q_n_b = canonicalQuaternion(
        state.q_n_b * quaternionExp(error.segment<3>(kAttitude)));
    state.accel_bias_b += error.segment<3>(kAccelBias);
    state.gyro_bias_b += error.segment<3>(kGyroBias);
}

inline double rotationDistance(const Eigen::Quaterniond& lhs,
                               const Eigen::Quaterniond& rhs) {
    return so3Log(lhs.toRotationMatrix().transpose() * rhs.toRotationMatrix()).norm();
}

}  // namespace s2
