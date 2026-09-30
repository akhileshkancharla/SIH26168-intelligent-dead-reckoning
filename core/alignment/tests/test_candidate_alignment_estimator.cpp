#include "sih26168/alignment/candidate_alignment_estimator.hpp"

#include <Eigen/Core>
#include <Eigen/Geometry>

#include <algorithm>
#include <array>
#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace alignment = sih26168::alignment;

namespace {

constexpr std::int64_t kSecond = 1'000'000'000;
constexpr double kPi = 3.14159265358979323846;
int failures = 0;
int total = 0;

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

void run(const std::string& name, const std::function<void()>& test) {
    ++total;
    try {
        test();
        std::cout << "PASS " << name << '\n';
    } catch (const std::exception& exception) {
        ++failures;
        std::cerr << "FAIL " << name << ": " << exception.what() << '\n';
    }
}

std::array<double, 3> array3(const Eigen::Vector3d& value) {
    return {value.x(), value.y(), value.z()};
}

std::array<double, 4> array4(const Eigen::Quaterniond& value) {
    return {value.w(), value.x(), value.y(), value.z()};
}

Eigen::Quaterniond quaternion(const alignment::CandidateRotation& rotation) {
    return {rotation.q_v_b_wxyz[0], rotation.q_v_b_wxyz[1],
            rotation.q_v_b_wxyz[2], rotation.q_v_b_wxyz[3]};
}

double rotationErrorRad(const Eigen::Quaterniond& expected,
                        const Eigen::Quaterniond& actual) {
    const double dot = std::clamp(std::abs(expected.normalized().dot(actual.normalized())),
                                  0.0, 1.0);
    return 2.0 * std::acos(dot);
}

alignment::CandidateEstimatorConfig smallConfig() {
    alignment::CandidateEstimatorConfig config;
    config.minimum_stationary_samples = 4;
    config.minimum_dynamic_intervals = 3;
    config.minimum_m2_samples = 3;
    config.minimum_dynamic_acceleration_mps2 = 0.05;
    return config;
}

struct M1Fixture {
    Eigen::Quaterniond expected_q_v_b;
    std::vector<alignment::BodyImuSample> imu;
    std::vector<alignment::GnssMotionSample> gnss;
};

M1Fixture m1Fixture() {
    const Eigen::Quaterniond tilt(
        Eigen::AngleAxisd(12.0 * kPi / 180.0, Eigen::Vector3d::UnitX())
        * Eigen::AngleAxisd(-7.0 * kPi / 180.0, Eigen::Vector3d::UnitY()));
    const Eigen::Quaterniond yaw(
        Eigen::AngleAxisd(31.0 * kPi / 180.0, Eigen::Vector3d::UnitZ()));
    const Eigen::Quaterniond q_v_b = (yaw * tilt).normalized();
    const Eigen::Vector3d gravity_v(0.0, 0.0, -9.80665);
    const Eigen::Vector3d gravity_b = q_v_b.conjugate() * gravity_v;

    M1Fixture fixture{q_v_b, {}, {}};
    for (int index = 0; index < 4; ++index) {
        fixture.imu.push_back({
            (index + 1) * kSecond,
            "stationary-" + std::to_string(index),
            array3(gravity_b),
            {0.0, 0.0, 0.0},
            "quality-stationary-" + std::to_string(index),
            true,
            true,
        });
    }

    const std::array<double, 4> speeds{5.0, 9.0, 9.0, 5.0};
    const std::array<double, 4> courses{0.0, 0.0, 0.4, 0.4};
    const std::array<std::int64_t, 4> epochs{
        20 * kSecond, 24 * kSecond, 28 * kSecond, 32 * kSecond};
    for (std::size_t index = 0; index < speeds.size(); ++index) {
        fixture.gnss.push_back({
            epochs[index],
            "gnss-" + std::to_string(index),
            speeds[index],
            0.2,
            courses[index],
            2.0 * kPi / 180.0,
            "quality-gnss-" + std::to_string(index),
            true,
        });
        if (index == 0) continue;
        const double dt = static_cast<double>(epochs[index] - epochs[index - 1]) / 1.0e9;
        const double dv = (speeds[index] - speeds[index - 1]) / dt;
        const double dh = std::remainder(courses[index] - courses[index - 1],
                                         2.0 * kPi);
        const double lateral = 0.5 * (speeds[index] + speeds[index - 1]) * dh / dt;
        const Eigen::Vector3d dynamic_v(dv, lateral, 0.0);
        const Eigen::Vector3d specific_force_b =
            gravity_b + q_v_b.conjugate() * dynamic_v;
        fixture.imu.push_back({
            epochs[index],
            "dynamic-" + std::to_string(index),
            array3(specific_force_b),
            array3(q_v_b.conjugate() * Eigen::Vector3d(0.0, 0.0, dh / dt)),
            "quality-dynamic-" + std::to_string(index),
            true,
            false,
        });
    }
    return fixture;
}

std::vector<alignment::NavigationMotionSample> m2Fixture(
    const Eigen::Quaterniond& expected_q_v_b) {
    std::vector<alignment::NavigationMotionSample> samples;
    const std::array<double, 3> courses{0.1, 0.4, -0.2};
    const std::array<std::int64_t, 3> epochs{2 * kSecond, 7 * kSecond, 12 * kSecond};
    for (std::size_t index = 0; index < courses.size(); ++index) {
        const double course = courses[index];
        const Eigen::Quaterniond q_n_v(
            Eigen::AngleAxisd(course, Eigen::Vector3d::UnitZ()));
        const Eigen::Quaterniond q_n_b = (q_n_v * expected_q_v_b).normalized();
        samples.push_back({
            epochs[index],
            "state-" + std::to_string(index),
            {6.0 * std::cos(course), 6.0 * std::sin(course), 0.0},
            array4(q_n_b),
            "quality-state-" + std::to_string(index),
            true,
        });
    }
    return samples;
}

std::vector<alignment::BodyImuSample> m2ImuFixture(
    const std::vector<alignment::NavigationMotionSample>& navigation_samples) {
    std::vector<alignment::BodyImuSample> samples;
    for (std::size_t index = 0; index < navigation_samples.size(); ++index) {
        samples.push_back({
            navigation_samples[index].epoch_ns,
            "m2-imu-" + std::to_string(index),
            {0.2, -0.1, -9.7},
            {0.0, 0.0, 0.05},
            "quality-m2-imu-" + std::to_string(index),
            true,
            false,
        });
    }
    return samples;
}

}  // namespace

int main() {
    run("m1_recovers_body_to_vehicle_rotation", [] {
        const auto fixture = m1Fixture();
        const auto result = alignment::solveM1(fixture.imu, fixture.gnss, smallConfig());
        require(result.hasEstimate(), "qualified M1 fixture produced no estimate");
        require(result.method_id == "S3-M1", "wrong M1 method identity");
        require(result.motion_observations_used == 3, "wrong M1 interval count");
        require(result.qualified_motion_duration_seconds == 12.0,
                "wrong M1 qualified duration");
        require(rotationErrorRad(fixture.expected_q_v_b, quaternion(*result.rotation)) < 1.0e-10,
                "M1 rotation differs from the synthetic truth");
        require(result.rotation->q_v_b_wxyz[0] >= 0.0, "M1 quaternion is not canonical");
        require(std::find(result.consumed_evidence_ids.begin(),
                          result.consumed_evidence_ids.end(), "quality-gnss-1")
                    != result.consumed_evidence_ids.end(),
                "M1 omitted consumed I-04 evidence identity");
    });

    run("m1_stationary_gravity_never_fabricates_yaw", [] {
        const auto fixture = m1Fixture();
        const auto result = alignment::solveM1(fixture.imu, {}, smallConfig());
        require(!result.hasEstimate(), "stationary evidence produced a full estimate");
        require(result.outcome == alignment::CandidateSolveOutcome::InsufficientMotionDuration,
                "stationary-only failure was not explicit");
    });

    run("m1_requires_enough_gravity_evidence", [] {
        auto fixture = m1Fixture();
        fixture.imu.erase(fixture.imu.begin(), fixture.imu.begin() + 2);
        const auto result = alignment::solveM1(fixture.imu, fixture.gnss, smallConfig());
        require(result.outcome == alignment::CandidateSolveOutcome::InsufficientGravityEvidence,
                "under-observed gravity was accepted");
        require(!result.rotation.has_value(), "under-observed gravity returned a rotation");
    });

    run("m1_enforces_frozen_motion_duration", [] {
        auto fixture = m1Fixture();
        fixture.gnss.back().epoch_ns = 29 * kSecond;
        const auto result = alignment::solveM1(fixture.imu, fixture.gnss, smallConfig());
        require(result.outcome == alignment::CandidateSolveOutcome::InsufficientMotionDuration,
                "short motion segment was accepted");
    });

    run("m1_rejects_unqualified_gnss", [] {
        auto fixture = m1Fixture();
        for (auto& sample : fixture.gnss) sample.course_accuracy_rad = 6.0 * kPi / 180.0;
        const auto result = alignment::solveM1(fixture.imu, fixture.gnss, smallConfig());
        require(result.outcome == alignment::CandidateSolveOutcome::InsufficientMotionDuration,
                "GNSS outside the frozen accuracy gate was consumed");
    });

    run("m1_does_not_bridge_quality_gaps", [] {
        auto fixture = m1Fixture();
        fixture.gnss[1].quality_eligible = false;
        const auto result = alignment::solveM1(fixture.imu, fixture.gnss, smallConfig());
        require(result.outcome == alignment::CandidateSolveOutcome::InsufficientMotionDuration,
                "M1 bridged a degraded GNSS sample to satisfy duration");
        require(!result.hasEstimate(), "quality-gapped M1 segment returned an estimate");
    });

    run("m1_rejects_nonfinite_and_duplicate_evidence", [] {
        auto nonfinite = m1Fixture();
        nonfinite.imu.front().specific_force_b_mps2[0] =
            std::numeric_limits<double>::quiet_NaN();
        require(alignment::solveM1(nonfinite.imu, nonfinite.gnss, smallConfig()).outcome
                    == alignment::CandidateSolveOutcome::InvalidInput,
                "non-finite M1 evidence was accepted");

        auto duplicate = m1Fixture();
        duplicate.gnss.front().evidence_id = duplicate.imu.front().evidence_id;
        require(alignment::solveM1(duplicate.imu, duplicate.gnss, smallConfig()).outcome
                    == alignment::CandidateSolveOutcome::InvalidInput,
                "duplicate cross-stream evidence identity was accepted");

        auto missing_quality = m1Fixture();
        missing_quality.gnss.front().quality_evidence_id.clear();
        require(alignment::solveM1(
                    missing_quality.imu, missing_quality.gnss, smallConfig()).outcome
                    == alignment::CandidateSolveOutcome::InvalidInput,
                "M1 evidence without I-04 identity was accepted");
    });

    run("m1_is_deterministic_and_does_not_mutate_inputs", [] {
        auto fixture = m1Fixture();
        const auto original_imu = fixture.imu;
        const auto original_gnss = fixture.gnss;
        const auto first = alignment::solveM1(fixture.imu, fixture.gnss, smallConfig());
        const auto second = alignment::solveM1(fixture.imu, fixture.gnss, smallConfig());
        require(first.rotation->q_v_b_wxyz == second.rotation->q_v_b_wxyz,
                "unchanged M1 input changed output bytes");
        require(fixture.imu.front().specific_force_b_mps2
                    == original_imu.front().specific_force_b_mps2
                && fixture.gnss.front().course_rad == original_gnss.front().course_rad,
                "M1 mutated source evidence");
    });

    run("m2_recovers_body_to_vehicle_rotation", [] {
        const Eigen::Quaterniond expected(
            Eigen::AngleAxisd(0.35, Eigen::Vector3d::UnitZ())
            * Eigen::AngleAxisd(-0.2, Eigen::Vector3d::UnitY())
            * Eigen::AngleAxisd(0.1, Eigen::Vector3d::UnitX()));
        const auto samples = m2Fixture(expected);
        const auto result = alignment::solveM2(m2ImuFixture(samples), samples, smallConfig());
        require(result.hasEstimate(), "qualified M2 fixture produced no estimate");
        require(result.method_id == "S3-M2", "wrong M2 method identity");
        require(result.motion_observations_used == 3, "wrong M2 observation count");
        require(rotationErrorRad(expected, quaternion(*result.rotation)) < 1.0e-10,
                "M2 rotation differs from the synthetic truth");
        require(std::find(result.consumed_evidence_ids.begin(),
                          result.consumed_evidence_ids.end(), "quality-state-0")
                    != result.consumed_evidence_ids.end(),
                "M2 omitted consumed I-04 evidence identity");
    });

    run("m2_fails_closed_on_low_speed", [] {
        const Eigen::Quaterniond expected = Eigen::Quaterniond::Identity();
        auto samples = m2Fixture(expected);
        for (auto& sample : samples) sample.velocity_n_mps = {1.0, 0.0, 0.0};
        const auto result = alignment::solveM2(m2ImuFixture(samples), samples, smallConfig());
        require(result.outcome == alignment::CandidateSolveOutcome::InsufficientDynamicExcitation,
                "low-speed M2 evidence was accepted");
        require(!result.hasEstimate(), "low-speed M2 returned an estimate");
    });

    run("m2_enforces_duration_and_quality", [] {
        const Eigen::Quaterniond expected = Eigen::Quaterniond::Identity();
        auto short_samples = m2Fixture(expected);
        short_samples.back().epoch_ns = 11 * kSecond;
        require(alignment::solveM2(
                    m2ImuFixture(short_samples), short_samples, smallConfig()).outcome
                    == alignment::CandidateSolveOutcome::InsufficientMotionDuration,
                "short M2 segment was accepted");

        auto degraded_samples = m2Fixture(expected);
        degraded_samples[1].quality_eligible = false;
        require(alignment::solveM2(
                    m2ImuFixture(degraded_samples), degraded_samples, smallConfig()).outcome
                    == alignment::CandidateSolveOutcome::InsufficientDynamicExcitation,
                "degraded M2 sample was consumed");
    });

    run("m2_rejects_invalid_quaternion", [] {
        auto samples = m2Fixture(Eigen::Quaterniond::Identity());
        const auto imu = m2ImuFixture(samples);
        samples[1].q_n_b_wxyz = {0.0, 0.0, 0.0, 0.0};
        require(alignment::solveM2(imu, samples, smallConfig()).outcome
                    == alignment::CandidateSolveOutcome::InvalidInput,
                "zero M2 quaternion was accepted");
    });

    run("m2_requires_contemporaneous_raw_imu", [] {
        const auto samples = m2Fixture(Eigen::Quaterniond::Identity());
        const auto result = alignment::solveM2({}, samples, smallConfig());
        require(result.outcome == alignment::CandidateSolveOutcome::InsufficientDynamicExcitation,
                "M2 produced an estimate without its frozen I-03 input");
        require(!result.hasEstimate(), "M2 without raw IMU returned an estimate");
    });

    run("invalid_configuration_fails_closed", [] {
        auto fixture = m1Fixture();
        auto config = smallConfig();
        config.minimum_dynamic_acceleration_mps2 = 0.0;
        require(alignment::solveM1(fixture.imu, fixture.gnss, config).outcome
                    == alignment::CandidateSolveOutcome::InvalidInput,
                "invalid M1 configuration was accepted");
        const auto m2 = m2Fixture(Eigen::Quaterniond::Identity());
        require(alignment::solveM2(m2ImuFixture(m2), m2, config).outcome
                    == alignment::CandidateSolveOutcome::InvalidInput,
                "invalid M2 configuration was accepted");
    });

    run("outcomes_have_stable_strings", [] {
        require(std::string(alignment::toString(
                    alignment::CandidateSolveOutcome::EstimateAvailable))
                    == "estimate_available",
                "estimate outcome string changed");
        require(std::string(alignment::toString(
                    alignment::CandidateSolveOutcome::InsufficientDynamicExcitation))
                    == "insufficient_dynamic_excitation",
                "excitation outcome string changed");
    });

    std::cout << "RESULT " << (total - failures) << '/' << total << " tests passed\n";
    return failures == 0 ? 0 : 1;
}
