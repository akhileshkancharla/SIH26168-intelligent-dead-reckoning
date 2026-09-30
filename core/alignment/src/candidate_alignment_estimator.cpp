#include "sih26168/alignment/candidate_alignment_estimator.hpp"

#include <Eigen/Core>
#include <Eigen/Geometry>

#include <algorithm>
#include <cmath>
#include <unordered_set>
#include <utility>

namespace sih26168::alignment {
namespace {

constexpr double kNanosecondsPerSecond = 1.0e9;
constexpr double kVectorNormFloor = 1.0e-12;
constexpr double kPi = 3.14159265358979323846;

bool finite(double value) {
    return std::isfinite(value);
}

template <std::size_t Size>
bool finiteArray(const std::array<double, Size>& values) {
    return std::all_of(values.begin(), values.end(), finite);
}

double secondsBetween(std::int64_t first_ns, std::int64_t second_ns) {
    return static_cast<double>(second_ns - first_ns) / kNanosecondsPerSecond;
}

double wrapAngle(double angle) {
    return std::remainder(angle, 2.0 * kPi);
}

bool validConfig(const CandidateEstimatorConfig& config) {
    return config.minimum_stationary_samples > 0
        && config.minimum_dynamic_intervals > 0
        && config.minimum_m2_samples > 0
        && finite(config.minimum_dynamic_acceleration_mps2)
        && config.minimum_dynamic_acceleration_mps2 > 0.0;
}

template <typename Sample, typename Validator>
bool validOrderedEvidence(const std::vector<Sample>& samples,
                          std::unordered_set<std::string>& evidence_ids,
                          Validator validator) {
    std::int64_t previous_epoch = -1;
    for (const auto& sample : samples) {
        if (sample.epoch_ns < 0 || sample.epoch_ns <= previous_epoch
            || sample.evidence_id.empty() || !evidence_ids.insert(sample.evidence_id).second
            || !validator(sample)) {
            return false;
        }
        previous_epoch = sample.epoch_ns;
    }
    return true;
}

bool qualified(const GnssMotionSample& sample) {
    return sample.quality_eligible
        && sample.speed_mps >= kMinimumQualifiedSpeedMps
        && sample.speed_accuracy_mps <= kMaximumGnssSpeedAccuracyMps
        && sample.course_accuracy_rad <= kMaximumGnssCourseAccuracyRad;
}

Eigen::Vector3d vector3(const std::array<double, 3>& values) {
    return {values[0], values[1], values[2]};
}

std::array<double, 4> canonicalWxyz(Eigen::Quaterniond quaternion) {
    quaternion.normalize();
    if (quaternion.w() < 0.0) quaternion.coeffs() *= -1.0;
    return {quaternion.w(), quaternion.x(), quaternion.y(), quaternion.z()};
}

void appendUnique(std::vector<std::string>& target, const std::string& evidence_id) {
    if (std::find(target.begin(), target.end(), evidence_id) == target.end()) {
        target.push_back(evidence_id);
    }
}

template <typename Sample, typename Predicate>
std::pair<std::size_t, std::size_t> longestQualifiedRun(
    const std::vector<Sample>& samples, Predicate predicate) {
    std::size_t best_begin = 0;
    std::size_t best_end = 0;
    double best_duration = -1.0;
    std::size_t run_begin = 0;
    bool in_run = false;
    for (std::size_t index = 0; index <= samples.size(); ++index) {
        const bool is_qualified = index < samples.size() && predicate(samples[index]);
        if (is_qualified && !in_run) {
            run_begin = index;
            in_run = true;
        }
        if (!is_qualified && in_run) {
            const std::size_t run_end = index - 1;
            const double duration = secondsBetween(
                samples[run_begin].epoch_ns, samples[run_end].epoch_ns);
            if (duration > best_duration) {
                best_begin = run_begin;
                best_end = run_end;
                best_duration = duration;
            }
            in_run = false;
        }
    }
    return {best_begin, best_end};
}

CandidateSolveResult failure(const char* method_id, CandidateSolveOutcome outcome) {
    CandidateSolveResult result;
    result.method_id = method_id;
    result.outcome = outcome;
    return result;
}

}  // namespace

bool CandidateSolveResult::hasEstimate() const {
    return outcome == CandidateSolveOutcome::EstimateAvailable && rotation.has_value();
}

CandidateSolveResult solveM1(const std::vector<BodyImuSample>& imu_samples,
                             const std::vector<GnssMotionSample>& gnss_samples,
                             const CandidateEstimatorConfig& config) {
    constexpr const char* kMethod = "S3-M1";
    if (!validConfig(config)) return failure(kMethod, CandidateSolveOutcome::InvalidInput);

    std::unordered_set<std::string> evidence_ids;
    const bool valid_imu = validOrderedEvidence(
        imu_samples, evidence_ids, [](const BodyImuSample& sample) {
            return finiteArray(sample.specific_force_b_mps2)
                && finiteArray(sample.angular_rate_b_radps)
                && !sample.quality_evidence_id.empty();
        });
    const bool valid_gnss = validOrderedEvidence(
        gnss_samples, evidence_ids, [](const GnssMotionSample& sample) {
            return finite(sample.speed_mps) && sample.speed_mps >= 0.0
                && finite(sample.speed_accuracy_mps) && sample.speed_accuracy_mps >= 0.0
                && finite(sample.course_rad)
                && finite(sample.course_accuracy_rad) && sample.course_accuracy_rad >= 0.0
                && !sample.quality_evidence_id.empty();
        });
    if (!valid_imu || !valid_gnss) {
        return failure(kMethod, CandidateSolveOutcome::InvalidInput);
    }

    Eigen::Vector3d gravity_sum = Eigen::Vector3d::Zero();
    std::vector<std::string> stationary_evidence;
    std::size_t stationary_count = 0;
    for (const auto& sample : imu_samples) {
        if (sample.quality_eligible && sample.stationary) {
            gravity_sum += vector3(sample.specific_force_b_mps2);
            ++stationary_count;
            appendUnique(stationary_evidence, sample.evidence_id);
            appendUnique(stationary_evidence, sample.quality_evidence_id);
        }
    }
    if (stationary_count < config.minimum_stationary_samples
        || !finite(gravity_sum.norm()) || gravity_sum.norm() <= kVectorNormFloor) {
        auto result = failure(kMethod, CandidateSolveOutcome::InsufficientGravityEvidence);
        result.stationary_samples_used = stationary_count;
        result.consumed_evidence_ids = std::move(stationary_evidence);
        return result;
    }

    const Eigen::Vector3d gravity_b = gravity_sum
        / static_cast<double>(stationary_count);
    const Eigen::Vector3d vehicle_up(0.0, 0.0, -1.0);
    const Eigen::Quaterniond tilt = Eigen::Quaterniond::FromTwoVectors(
        gravity_b.normalized(), vehicle_up);

    const auto [qualified_begin, qualified_end] = longestQualifiedRun(
        gnss_samples, [](const GnssMotionSample& sample) { return qualified(sample); });
    if (gnss_samples.empty() || qualified_end <= qualified_begin
        || !qualified(gnss_samples[qualified_begin])) {
        auto result = failure(kMethod, CandidateSolveOutcome::InsufficientMotionDuration);
        result.stationary_samples_used = stationary_count;
        result.consumed_evidence_ids = std::move(stationary_evidence);
        return result;
    }

    const auto& first_qualified = gnss_samples[qualified_begin];
    const auto& last_qualified = gnss_samples[qualified_end];
    const double duration_seconds = secondsBetween(
        first_qualified.epoch_ns, last_qualified.epoch_ns);
    if (!finite(duration_seconds)
        || duration_seconds < kMinimumQualifiedMotionDurationSeconds) {
        auto result = failure(kMethod, CandidateSolveOutcome::InsufficientMotionDuration);
        result.stationary_samples_used = stationary_count;
        result.qualified_motion_duration_seconds = duration_seconds;
        result.consumed_evidence_ids = std::move(stationary_evidence);
        return result;
    }

    double dot_sum = 0.0;
    double cross_sum = 0.0;
    double accumulated_heading_change = 0.0;
    std::size_t used_intervals = 0;
    std::vector<std::string> dynamic_evidence;

    for (std::size_t index = qualified_begin + 1; index <= qualified_end; ++index) {
        const auto& previous = gnss_samples[index - 1];
        const auto& current = gnss_samples[index];
        const double delta_time = secondsBetween(previous.epoch_ns, current.epoch_ns);
        if (!(delta_time > 0.0) || !finite(delta_time)) {
            return failure(kMethod, CandidateSolveOutcome::InvalidInput);
        }

        Eigen::Vector3d body_sum = Eigen::Vector3d::Zero();
        std::size_t body_count = 0;
        std::vector<std::string> interval_imu_evidence;
        for (const auto& sample : imu_samples) {
            if (sample.quality_eligible && !sample.stationary
                && sample.epoch_ns > previous.epoch_ns
                && sample.epoch_ns <= current.epoch_ns) {
                body_sum += vector3(sample.specific_force_b_mps2);
                ++body_count;
                interval_imu_evidence.push_back(sample.evidence_id);
                interval_imu_evidence.push_back(sample.quality_evidence_id);
            }
        }
        if (body_count == 0) continue;

        const double heading_delta = wrapAngle(current.course_rad - previous.course_rad);
        const double longitudinal_acceleration =
            (current.speed_mps - previous.speed_mps) / delta_time;
        const double average_speed = 0.5 * (current.speed_mps + previous.speed_mps);
        const double lateral_acceleration = average_speed * heading_delta / delta_time;
        const Eigen::Vector2d target_vehicle(
            longitudinal_acceleration, lateral_acceleration);

        const Eigen::Vector3d mean_body = body_sum / static_cast<double>(body_count);
        const Eigen::Vector3d tilted_dynamic = tilt * (mean_body - gravity_b);
        const Eigen::Vector2d observed_tilted(tilted_dynamic.x(), tilted_dynamic.y());
        if (target_vehicle.norm() < config.minimum_dynamic_acceleration_mps2
            || observed_tilted.norm() < config.minimum_dynamic_acceleration_mps2) {
            continue;
        }

        dot_sum += observed_tilted.dot(target_vehicle);
        cross_sum += observed_tilted.x() * target_vehicle.y()
            - observed_tilted.y() * target_vehicle.x();
        accumulated_heading_change += std::abs(heading_delta);
        ++used_intervals;
        for (const auto& evidence_id : interval_imu_evidence) {
            appendUnique(dynamic_evidence, evidence_id);
        }
        appendUnique(dynamic_evidence, previous.evidence_id);
        appendUnique(dynamic_evidence, previous.quality_evidence_id);
        appendUnique(dynamic_evidence, current.evidence_id);
        appendUnique(dynamic_evidence, current.quality_evidence_id);
    }

    if (used_intervals < config.minimum_dynamic_intervals
        || !finite(dot_sum) || !finite(cross_sum)
        || std::hypot(dot_sum, cross_sum) <= kVectorNormFloor) {
        auto result = failure(kMethod, CandidateSolveOutcome::InsufficientDynamicExcitation);
        result.stationary_samples_used = stationary_count;
        result.motion_observations_used = used_intervals;
        result.qualified_motion_duration_seconds = duration_seconds;
        result.accumulated_heading_change_rad = accumulated_heading_change;
        result.consumed_evidence_ids = std::move(stationary_evidence);
        result.consumed_evidence_ids.insert(result.consumed_evidence_ids.end(),
                                            dynamic_evidence.begin(),
                                            dynamic_evidence.end());
        return result;
    }

    const double yaw = std::atan2(cross_sum, dot_sum);
    Eigen::Quaterniond q_v_b = Eigen::AngleAxisd(yaw, Eigen::Vector3d::UnitZ()) * tilt;

    CandidateSolveResult result;
    result.outcome = CandidateSolveOutcome::EstimateAvailable;
    result.method_id = kMethod;
    result.rotation = CandidateRotation{canonicalWxyz(q_v_b)};
    result.stationary_samples_used = stationary_count;
    result.motion_observations_used = used_intervals;
    result.qualified_motion_duration_seconds = duration_seconds;
    result.accumulated_heading_change_rad = accumulated_heading_change;
    result.consumed_evidence_ids = std::move(stationary_evidence);
    result.consumed_evidence_ids.insert(result.consumed_evidence_ids.end(),
                                        dynamic_evidence.begin(),
                                        dynamic_evidence.end());
    return result;
}

CandidateSolveResult solveM2(const std::vector<BodyImuSample>& imu_samples,
                             const std::vector<NavigationMotionSample>& navigation_samples,
                             const CandidateEstimatorConfig& config) {
    constexpr const char* kMethod = "S3-M2";
    if (!validConfig(config)) return failure(kMethod, CandidateSolveOutcome::InvalidInput);

    std::unordered_set<std::string> evidence_ids;
    const bool valid_imu = validOrderedEvidence(
        imu_samples, evidence_ids, [](const BodyImuSample& sample) {
            return finiteArray(sample.specific_force_b_mps2)
                && finiteArray(sample.angular_rate_b_radps)
                && !sample.quality_evidence_id.empty();
        });
    const bool valid_samples = validOrderedEvidence(
        navigation_samples, evidence_ids, [](const NavigationMotionSample& sample) {
            if (!finiteArray(sample.velocity_n_mps) || !finiteArray(sample.q_n_b_wxyz)) {
                return false;
            }
            const Eigen::Quaterniond quaternion(sample.q_n_b_wxyz[0], sample.q_n_b_wxyz[1],
                                                sample.q_n_b_wxyz[2], sample.q_n_b_wxyz[3]);
            return finite(quaternion.norm()) && quaternion.norm() > kVectorNormFloor
                && !sample.quality_evidence_id.empty();
        });
    if (!valid_imu || !valid_samples) {
        return failure(kMethod, CandidateSolveOutcome::InvalidInput);
    }

    const auto is_qualified = [](const NavigationMotionSample& sample) {
        const double horizontal_speed = std::hypot(
            sample.velocity_n_mps[0], sample.velocity_n_mps[1]);
        return sample.quality_eligible && horizontal_speed >= kMinimumQualifiedSpeedMps;
    };
    const auto [qualified_begin, qualified_end] = longestQualifiedRun(
        navigation_samples, is_qualified);
    const std::size_t qualified_count = navigation_samples.empty()
        || !is_qualified(navigation_samples[qualified_begin])
        ? 0
        : qualified_end - qualified_begin + 1;
    if (qualified_count < config.minimum_m2_samples) {
        return failure(kMethod, CandidateSolveOutcome::InsufficientDynamicExcitation);
    }

    const double duration_seconds = secondsBetween(
        navigation_samples[qualified_begin].epoch_ns,
        navigation_samples[qualified_end].epoch_ns);
    if (!finite(duration_seconds)
        || duration_seconds < kMinimumQualifiedMotionDurationSeconds) {
        auto result = failure(kMethod, CandidateSolveOutcome::InsufficientMotionDuration);
        result.motion_observations_used = qualified_count;
        result.qualified_motion_duration_seconds = duration_seconds;
        return result;
    }

    std::vector<std::string> contemporaneous_imu_evidence;
    std::size_t contemporaneous_imu_count = 0;
    for (const auto& sample : imu_samples) {
        if (sample.quality_eligible && !sample.stationary
            && sample.epoch_ns >= navigation_samples[qualified_begin].epoch_ns
            && sample.epoch_ns <= navigation_samples[qualified_end].epoch_ns) {
            appendUnique(contemporaneous_imu_evidence, sample.evidence_id);
            appendUnique(contemporaneous_imu_evidence, sample.quality_evidence_id);
            ++contemporaneous_imu_count;
        }
    }
    if (contemporaneous_imu_count < config.minimum_m2_samples) {
        auto result = failure(kMethod, CandidateSolveOutcome::InsufficientDynamicExcitation);
        result.motion_observations_used = qualified_count;
        result.qualified_motion_duration_seconds = duration_seconds;
        result.consumed_evidence_ids = std::move(contemporaneous_imu_evidence);
        return result;
    }

    Eigen::Vector4d quaternion_sum = Eigen::Vector4d::Zero();  // [w,x,y,z]
    Eigen::Vector4d reference = Eigen::Vector4d::Zero();
    double accumulated_heading_change = 0.0;
    double previous_course = 0.0;
    bool have_previous_course = false;
    std::vector<std::string> consumed_evidence = std::move(contemporaneous_imu_evidence);

    for (std::size_t index = qualified_begin; index <= qualified_end; ++index) {
        const auto& sample = navigation_samples[index];
        const double course = std::atan2(sample.velocity_n_mps[1], sample.velocity_n_mps[0]);
        Eigen::Quaterniond q_n_b(sample.q_n_b_wxyz[0], sample.q_n_b_wxyz[1],
                                sample.q_n_b_wxyz[2], sample.q_n_b_wxyz[3]);
        q_n_b.normalize();
        const Eigen::Quaterniond q_n_v(Eigen::AngleAxisd(course, Eigen::Vector3d::UnitZ()));
        Eigen::Quaterniond q_v_b = q_n_v.conjugate() * q_n_b;
        q_v_b.normalize();
        Eigen::Vector4d value(q_v_b.w(), q_v_b.x(), q_v_b.y(), q_v_b.z());
        if (reference.squaredNorm() == 0.0) reference = value;
        if (value.dot(reference) < 0.0) value *= -1.0;
        quaternion_sum += value;
        if (have_previous_course) {
            accumulated_heading_change += std::abs(wrapAngle(course - previous_course));
        }
        previous_course = course;
        have_previous_course = true;
        appendUnique(consumed_evidence, sample.evidence_id);
        appendUnique(consumed_evidence, sample.quality_evidence_id);
    }

    if (!quaternion_sum.allFinite() || quaternion_sum.norm() <= kVectorNormFloor) {
        return failure(kMethod, CandidateSolveOutcome::InsufficientDynamicExcitation);
    }
    quaternion_sum.normalize();
    Eigen::Quaterniond q_v_b(
        quaternion_sum[0], quaternion_sum[1], quaternion_sum[2], quaternion_sum[3]);

    CandidateSolveResult result;
    result.outcome = CandidateSolveOutcome::EstimateAvailable;
    result.method_id = kMethod;
    result.rotation = CandidateRotation{canonicalWxyz(q_v_b)};
    result.motion_observations_used = qualified_count;
    result.qualified_motion_duration_seconds = duration_seconds;
    result.accumulated_heading_change_rad = accumulated_heading_change;
    result.consumed_evidence_ids = std::move(consumed_evidence);
    return result;
}

const char* toString(CandidateSolveOutcome outcome) {
    switch (outcome) {
        case CandidateSolveOutcome::EstimateAvailable: return "estimate_available";
        case CandidateSolveOutcome::InvalidInput: return "invalid_input";
        case CandidateSolveOutcome::InsufficientGravityEvidence:
            return "insufficient_gravity_evidence";
        case CandidateSolveOutcome::InsufficientMotionDuration:
            return "insufficient_motion_duration";
        case CandidateSolveOutcome::InsufficientDynamicExcitation:
            return "insufficient_dynamic_excitation";
    }
    return "unknown";
}

}  // namespace sih26168::alignment
