#include "sih26168/alignment/mount_slip_detector.hpp"

#include <array>
#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

namespace alignment = sih26168::alignment;
namespace contracts = sih26168::contracts;

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

std::array<double, 4> axisAngle(double x, double y, double z,
                                double angle_rad) {
    const double half = angle_rad / 2.0;
    const double scale = std::sin(half);
    return {std::cos(half), x * scale, y * scale, z * scale};
}

contracts::AlignmentEstimate validEstimate() {
    contracts::AlignmentEstimate value;
    value.sequence = 10;
    value.epoch_ns = kSecond;
    value.q_v_b_wxyz = {1.0, 0.0, 0.0, 0.0};
    value.covariance_3x3 = {
        0.01, 0.0, 0.0,
        0.0, 0.01, 0.0,
        0.0, 0.0, 0.01,
    };
    value.status = contracts::AlignmentStatusV1::VALID;
    value.observability = 0.8;
    value.slip_probability = std::nullopt;
    value.method_id = "S3-M1";
    value.evidence_ids = {"alignment-baseline", "alignment-quality"};
    value.config_id = "alignment-config-v1";
    return value;
}

alignment::MountOrientationObservation observation(
    double angle_deg, std::uint64_t sequence = 1,
    std::int64_t epoch_ns = kSecond + 500'000'000,
    std::array<double, 3> axis = {0.0, 0.0, 1.0}) {
    alignment::MountOrientationObservation value;
    value.sequence = sequence;
    value.epoch_ns = epoch_ns;
    value.q_v_b_wxyz = axisAngle(
        axis[0], axis[1], axis[2], angle_deg * kPi / 180.0);
    value.evidence_id = "mount-" + std::to_string(sequence);
    value.quality_evidence_id = "mount-quality-" + std::to_string(sequence);
    value.quality_eligible = true;
    return value;
}

struct Fixture {
    alignment::AlignmentEstimatePublisher publisher;
    alignment::MountSlipDetector detector;

    Fixture()
        : detector(publisher, {"s3-slip-config-v1"}) {
        require(publisher.publish(validEstimate()).accepted,
                "fixture baseline publication failed");
        require(detector.arm(), "fixture detector did not arm");
    }
};

}  // namespace

int main() {
    run("arms_only_from_current_valid_i06", [] {
        alignment::AlignmentEstimatePublisher publisher;
        alignment::MountSlipDetector detector(publisher, {"s3-slip-config-v1"});
        require(!detector.arm(), "detector armed without I-06 baseline");
        require(!publisher.dependentAidsEligible(),
                "unarmed detector left dependent aids eligible");

        auto uncertain = validEstimate();
        uncertain.status = contracts::AlignmentStatusV1::UNCERTAIN;
        require(publisher.publish(uncertain).accepted, "UNCERTAIN record was rejected");
        require(!detector.arm(), "detector armed from UNCERTAIN baseline");
    });

    run("below_threshold_is_no_slip", [] {
        Fixture fixture;
        const auto decision = fixture.detector.observe(observation(14.0));
        require(decision.outcome == alignment::MountSlipOutcome::NoSlip,
                "sub-threshold rotation triggered slip");
        require(decision.angular_change_rad.has_value(),
                "no-slip decision omitted measured change");
        require(fixture.publisher.dependentAidsEligible(),
                "eligible no-slip observation disabled dependent aids");
        require(fixture.publisher.latest()->status
                    == contracts::AlignmentStatusV1::VALID,
                "no-slip observation changed I-06 status");
    });

    run("frozen_yaw_threshold_publishes_slip_atomically", [] {
        Fixture fixture;
        const auto decision = fixture.detector.observe(observation(15.0));
        require(decision.slipSuspected(), "15-degree yaw slip was not detected");
        require(fixture.detector.slipLatched(), "detected slip was not latched");
        require(!fixture.publisher.dependentAidsEligible(),
                "slip publication did not atomically disable dependent aids");
        const auto& published = *fixture.publisher.latest();
        require(published.status == contracts::AlignmentStatusV1::SLIP_SUSPECTED,
                "slip status was not published");
        require(published.q_v_b_wxyz == validEstimate().q_v_b_wxyz,
                "slip publication rewrote the last valid alignment");
        require(!published.slip_probability.has_value(),
                "deterministic detector fabricated a probability");
        require(published.method_id
                    == "S3-M1|S3-MOUNT-SLIP-GEODESIC-v1",
                "slip method provenance is incomplete");
        require(published.config_id
                    == "alignment-config-v1|s3-slip-config-v1",
                "alignment or slip configuration identity is missing");
        require(published.evidence_ids.back() == "mount-quality-1",
                "triggering quality evidence was not retained");
    });

    run("roll_and_pitch_slips_are_detected_without_magnetometer", [] {
        Fixture roll;
        require(roll.detector.observe(
                    observation(16.0, 1, kSecond + 500'000'000, {1.0, 0.0, 0.0}))
                    .slipSuspected(),
                "roll slip was not detected");
        Fixture pitch;
        require(pitch.detector.observe(
                    observation(16.0, 1, kSecond + 500'000'000, {0.0, 1.0, 0.0}))
                    .slipSuspected(),
                "pitch slip was not detected");
    });

    run("monitoring_gap_fails_closed_at_frozen_latency", [] {
        Fixture within;
        require(within.detector.observe(
                    observation(0.0, 1, 2 * kSecond)).outcome
                    == alignment::MountSlipOutcome::NoSlip,
                "observation at the one-second boundary was rejected");

        Fixture beyond;
        const auto decision = beyond.detector.observe(
            observation(0.0, 1, 2 * kSecond + 1));
        require(decision.outcome == alignment::MountSlipOutcome::MonitoringGap,
                "monitoring gap beyond one second was accepted");
        require(!beyond.publisher.dependentAidsEligible(),
                "monitoring gap did not fail dependent aids closed");
        require(!beyond.detector.armed(),
                "monitoring failure did not require explicit re-arming");
        require(beyond.publisher.latest()->status
                    == contracts::AlignmentStatusV1::VALID,
                "monitoring failure overwrote the last accepted posterior");
    });

    run("quality_loss_fails_closed", [] {
        Fixture fixture;
        auto degraded = observation(0.0);
        degraded.quality_eligible = false;
        require(fixture.detector.observe(degraded).outcome
                    == alignment::MountSlipOutcome::QualityIneligible,
                "quality-ineligible observation was accepted");
        require(!fixture.publisher.dependentAidsEligible(),
                "quality loss left dependent aids eligible");
    });

    run("malformed_quaternions_fail_closed", [] {
        Fixture noncanonical;
        auto negative = observation(0.0);
        negative.q_v_b_wxyz = {-1.0, 0.0, 0.0, 0.0};
        require(noncanonical.detector.observe(negative).outcome
                    == alignment::MountSlipOutcome::InvalidInput,
                "negative-w quaternion was accepted");

        Fixture nonunit;
        auto scaled = observation(0.0);
        scaled.q_v_b_wxyz = {2.0, 0.0, 0.0, 0.0};
        require(nonunit.detector.observe(scaled).outcome
                    == alignment::MountSlipOutcome::InvalidInput,
                "non-unit quaternion was accepted");

        Fixture nonfinite;
        auto nan = observation(0.0);
        nan.q_v_b_wxyz[1] = std::numeric_limits<double>::quiet_NaN();
        require(nonfinite.detector.observe(nan).outcome
                    == alignment::MountSlipOutcome::InvalidInput,
                "non-finite quaternion was accepted");
    });

    run("evidence_identities_are_unique_and_not_reused", [] {
        Fixture fixture;
        require(fixture.detector.observe(observation(0.0)).outcome
                    == alignment::MountSlipOutcome::NoSlip,
                "first observation was rejected");
        auto reused = observation(0.0, 2, kSecond + 600'000'000);
        reused.evidence_id = "mount-1";
        require(fixture.detector.observe(reused).outcome
                    == alignment::MountSlipOutcome::InvalidInput,
                "reused evidence identity was accepted");
        require(!fixture.publisher.dependentAidsEligible(),
                "evidence reuse did not fail closed");
    });

    run("observation_sequence_and_epoch_are_monotonic", [] {
        Fixture sequence;
        require(sequence.detector.observe(observation(0.0)).outcome
                    == alignment::MountSlipOutcome::NoSlip,
                "first sequence observation was rejected");
        require(sequence.detector.observe(
                    observation(0.0, 1, kSecond + 600'000'000)).outcome
                    == alignment::MountSlipOutcome::SequenceNotIncreasing,
                "duplicate observation sequence was accepted");

        Fixture epoch;
        require(epoch.detector.observe(observation(0.0)).outcome
                    == alignment::MountSlipOutcome::NoSlip,
                "first epoch observation was rejected");
        require(epoch.detector.observe(
                    observation(0.0, 2, kSecond + 400'000'000)).outcome
                    == alignment::MountSlipOutcome::EpochRegressed,
                "regressed observation epoch was accepted");
    });

    run("baseline_change_requires_explicit_rearm", [] {
        Fixture fixture;
        auto replacement = validEstimate();
        ++replacement.sequence;
        ++replacement.epoch_ns;
        replacement.evidence_ids = {"replacement-alignment"};
        require(fixture.publisher.publish(replacement).accepted,
                "replacement VALID posterior was rejected");
        require(fixture.detector.observe(
                    observation(0.0, 1, replacement.epoch_ns)).outcome
                    == alignment::MountSlipOutcome::BaselineChanged,
                "detector silently switched alignment baseline");
        require(!fixture.publisher.dependentAidsEligible(),
                "unreviewed baseline change left aids eligible");
    });

    run("slip_remains_latched_until_new_evidence_recovery", [] {
        Fixture fixture;
        require(fixture.detector.observe(observation(16.0)).slipSuspected(),
                "slip was not detected");
        require(fixture.detector.observe(
                    observation(0.0, 2, kSecond + 600'000'000)).outcome
                    == alignment::MountSlipOutcome::AlreadyLatched,
                "latched detector resumed automatically");

        auto recovered = *fixture.publisher.latest();
        ++recovered.sequence;
        ++recovered.epoch_ns;
        recovered.status = contracts::AlignmentStatusV1::VALID;
        recovered.method_id = "S3-M1";
        recovered.config_id = "alignment-config-v2";
        recovered.evidence_ids.push_back("post-slip-realignment");
        require(fixture.publisher.publish(recovered).accepted,
                "new-evidence recovery was rejected");
        require(fixture.detector.arm(), "detector did not explicitly re-arm");
        require(!fixture.detector.slipLatched(), "re-armed detector stayed latched");
        require(fixture.detector.observe(
                    observation(0.0, 3, recovered.epoch_ns + 1)).outcome
                    == alignment::MountSlipOutcome::NoSlip,
                "re-armed detector rejected eligible evidence");
    });

    run("unchanged_input_replay_is_deterministic", [] {
        Fixture first;
        Fixture second;
        const auto input = observation(16.0);
        const auto first_decision = first.detector.observe(input);
        const auto second_decision = second.detector.observe(input);
        require(first_decision.outcome == second_decision.outcome
                    && first_decision.angular_change_rad
                        == second_decision.angular_change_rad,
                "unchanged input changed detector decision");
        require(first.publisher.latest()->sequence
                    == second.publisher.latest()->sequence
                    && first.publisher.latest()->epoch_ns
                        == second.publisher.latest()->epoch_ns
                    && first.publisher.latest()->q_v_b_wxyz
                        == second.publisher.latest()->q_v_b_wxyz
                    && first.publisher.latest()->evidence_ids
                        == second.publisher.latest()->evidence_ids,
                "unchanged input changed published I-06 fields");
    });

    run("invalid_configuration_never_arms", [] {
        alignment::AlignmentEstimatePublisher publisher;
        require(publisher.publish(validEstimate()).accepted,
                "baseline publication failed");
        alignment::MountSlipDetector detector(publisher, {""});
        require(!detector.arm(), "empty configuration identity was accepted");
        require(detector.observe(observation(16.0)).outcome
                    == alignment::MountSlipOutcome::InvalidConfiguration,
                "invalid configuration processed evidence");
    });

    run("outcomes_have_stable_strings", [] {
        require(std::string(alignment::toString(
                    alignment::MountSlipOutcome::SlipSuspected))
                    == "slip_suspected",
                "slip outcome string changed");
        require(std::string(alignment::toString(
                    alignment::MountSlipOutcome::MonitoringGap))
                    == "monitoring_gap",
                "gap outcome string changed");
    });

    std::cout << "RESULT " << (total - failures) << '/' << total << " tests passed\n";
    return failures == 0 ? 0 : 1;
}
