#pragma once

#include <Eigen/Core>
#include <Eigen/Geometry>

#include <cstdint>
#include <limits>
#include <string>

namespace s2 {

using Vec3 = Eigen::Matrix<double, 3, 1>;
using Vec6 = Eigen::Matrix<double, 6, 1>;
using Vec15 = Eigen::Matrix<double, 15, 1>;
using Mat3 = Eigen::Matrix<double, 3, 3>;
using Mat6 = Eigen::Matrix<double, 6, 6>;
using Mat15 = Eigen::Matrix<double, 15, 15>;
using Mat15x12 = Eigen::Matrix<double, 15, 12>;

constexpr int kPosition = 0;
constexpr int kVelocity = 3;
constexpr int kAttitude = 6;
constexpr int kAccelBias = 9;
constexpr int kGyroBias = 12;

struct NominalState {
    std::int64_t timestamp_ns{0};
    Vec3 position_n{Vec3::Zero()};
    Vec3 velocity_n{Vec3::Zero()};
    Eigen::Quaterniond q_n_b{Eigen::Quaterniond::Identity()};
    Vec3 accel_bias_b{Vec3::Zero()};
    Vec3 gyro_bias_b{Vec3::Zero()};
    Mat15 covariance{Mat15::Identity()};
};

struct ImuSample {
    std::int64_t timestamp_ns{0};
    Vec3 specific_force_b{Vec3::Zero()};
    Vec3 angular_rate_b{Vec3::Zero()};
};

enum class MeasurementKind {
    Position,
    Velocity,
    PositionVelocity,
};

struct GnssMeasurement {
    std::string id;
    std::int64_t timestamp_ns{0};
    MeasurementKind kind{MeasurementKind::Position};
    Vec6 value{Vec6::Zero()};
    Mat6 covariance{Mat6::Zero()};
};

struct CoreConfig {
    Vec3 gravity_n{Vec3(0.0, 0.0, 9.80665)};

    // Continuous-time white-noise densities and bias random-walk densities.
    double accel_noise_density{0.03};       // m/s^2/sqrt(Hz)
    double gyro_noise_density{0.0015};      // rad/s/sqrt(Hz)
    double accel_bias_rw_density{0.0008};   // m/s^3/sqrt(Hz)
    double gyro_bias_rw_density{0.00004};   // rad/s^2/sqrt(Hz)

    double expected_dt_s{0.01};
    double gap_factor{2.5};
    double min_dt_s{1.0e-6};
    double max_dt_s{0.20};

    // 99% chi-square gates, frozen before executing the spike.
    double gate_chi2_3{11.344866730144373};
    double gate_chi2_6{16.811893829770927};
};

struct PropagationResult {
    bool accepted{false};
    bool gap_detected{false};
    double dt_s{0.0};
    std::string status;
};

struct MeasurementResult {
    bool accepted{false};
    bool duplicate{false};
    int dimension{0};
    double nis{std::numeric_limits<double>::quiet_NaN()};
    Vec6 innovation{Vec6::Zero()};
    std::string status;
};

struct PropagationLinearization {
    Mat15 phi{Mat15::Identity()};
    Mat15 q_discrete{Mat15::Zero()};
    Mat3 rotation_mid_n_b{Mat3::Identity()};
    Vec3 corrected_force_b{Vec3::Zero()};
    Vec3 corrected_rate_b{Vec3::Zero()};
};

}  // namespace s2
