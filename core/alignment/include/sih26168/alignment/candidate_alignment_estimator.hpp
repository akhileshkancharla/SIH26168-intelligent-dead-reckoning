#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace sih26168::alignment {

// Frozen S3 qualification thresholds. They are feasibility gates, not claims
// of universal field performance.
inline constexpr double kMinimumQualifiedSpeedMps = 3.0;
inline constexpr double kMaximumGnssSpeedAccuracyMps = 0.5;
inline constexpr double kMaximumGnssCourseAccuracyRad =
    5.0 * 3.14159265358979323846 / 180.0;
inline constexpr double kMinimumQualifiedMotionDurationSeconds = 10.0;

struct BodyImuSample {
    std::int64_t epoch_ns{0};
    std::string evidence_id;
    std::array<double, 3> specific_force_b_mps2{};
    std::array<double, 3> angular_rate_b_radps{};
    std::string quality_evidence_id;
    bool quality_eligible{false};
    bool stationary{false};
};

struct GnssMotionSample {
    std::int64_t epoch_ns{0};
    std::string evidence_id;
    double speed_mps{0.0};
    double speed_accuracy_mps{0.0};
    double course_rad{0.0};
    double course_accuracy_rad{0.0};
    std::string quality_evidence_id;
    bool quality_eligible{false};
};

struct NavigationMotionSample {
    std::int64_t epoch_ns{0};
    std::string evidence_id;
    std::array<double, 3> velocity_n_mps{};
    std::array<double, 4> q_n_b_wxyz{1.0, 0.0, 0.0, 0.0};
    std::string quality_evidence_id;
    bool quality_eligible{false};
};

struct CandidateEstimatorConfig {
    std::size_t minimum_stationary_samples{8};
    std::size_t minimum_dynamic_intervals{3};
    std::size_t minimum_m2_samples{3};
    double minimum_dynamic_acceleration_mps2{0.1};
};

enum class CandidateSolveOutcome {
    EstimateAvailable,
    InvalidInput,
    InsufficientGravityEvidence,
    InsufficientMotionDuration,
    InsufficientDynamicExcitation,
};

struct CandidateRotation {
    // Active physical-body-to-vehicle quaternion, canonicalized to w >= 0.
    std::array<double, 4> q_v_b_wxyz{1.0, 0.0, 0.0, 0.0};
};

struct CandidateSolveResult {
    CandidateSolveOutcome outcome{CandidateSolveOutcome::InvalidInput};
    std::string method_id;
    std::optional<CandidateRotation> rotation;
    std::size_t stationary_samples_used{0};
    std::size_t motion_observations_used{0};
    double qualified_motion_duration_seconds{0.0};
    double accumulated_heading_change_rad{0.0};
    std::vector<std::string> consumed_evidence_ids;

    [[nodiscard]] bool hasEstimate() const;
};

// S3-M1: stationary gravity constrains tilt; qualified GNSS-derived vehicle
// acceleration supplies the independent horizontal evidence needed for yaw.
// No estimate is returned from stationary-only evidence.
CandidateSolveResult solveM1(
    const std::vector<BodyImuSample>& imu_samples,
    const std::vector<GnssMotionSample>& gnss_samples,
    const CandidateEstimatorConfig& config = {});

// S3-M2: paired I-07 velocity and body-attitude snapshots are bounded
// alignment evidence. No magnetometer input is required or authoritative.
CandidateSolveResult solveM2(
    const std::vector<BodyImuSample>& imu_samples,
    const std::vector<NavigationMotionSample>& navigation_samples,
    const CandidateEstimatorConfig& config = {});

[[nodiscard]] const char* toString(CandidateSolveOutcome outcome);

}  // namespace sih26168::alignment
