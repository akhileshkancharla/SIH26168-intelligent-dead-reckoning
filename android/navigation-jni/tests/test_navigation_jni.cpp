#include "sih26168/navigation_jni.hpp"

#include <cmath>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <new>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace api = sih26168::navigation;
namespace jni = sih26168::navigation::jni;

namespace {

int total = 0;
int failed = 0;

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

template <typename F>
void run(const char* name, F test) {
    ++total;
    try {
        test();
        std::cout << "PASS " << name << '\n';
    } catch (const std::exception& error) {
        ++failed;
        std::cerr << "FAIL " << name << ": " << error.what() << '\n';
    }
}

api::InitialState initialState() {
    api::InitialState value;
    value.state_sequence.value = 7;
    value.source_timestamp.nanoseconds = 1'000'000'000;
    value.clock_id.value = "boot-clock-1";
    value.origin_id.value = "origin-1";
    value.mode = api::NavigationMode::GnssAided;
    value.position_n_m = {1.0, 2.0, 3.0};
    value.velocity_n_mps = {0.1, 0.2, 0.3};
    value.q_n_b_wxyz = {1.0, 0.0, 0.0, 0.0};
    value.accel_bias_b_mps2 = {0.01, -0.02, 0.03};
    value.gyro_bias_b_radps = {0.001, -0.002, 0.003};
    value.covariance = api::identityCovariance(0.5);
    return value;
}

api::ImuSample sample(std::uint64_t sequence, std::int64_t timestamp,
                      const std::string& evidence) {
    api::ImuSample value;
    value.sequence.value = sequence;
    value.evidence_id.value = evidence;
    value.source_timestamp.nanoseconds = timestamp;
    value.arrival_timestamp.nanoseconds = timestamp + 1'000;
    value.specific_force_b_mps2 = {0.0, 0.0, -9.80665};
    value.angular_rate_b_radps = {0.01, -0.02, 0.03};
    return value;
}

api::ImuBatch batch() {
    api::ImuBatch value;
    value.batch_id.value = "batch-1";
    value.samples = {sample(10, 1'010'000'000, "imu-10"),
                     sample(11, 1'020'000'000, "imu-11")};
    value.first_seq = value.samples.front().sequence;
    value.last_seq = value.samples.back().sequence;
    value.gap_flags = static_cast<api::ImuGapFlags>(api::ImuGapFlag::TimingGap);
    value.clock_id.value = "boot-clock-1";
    return value;
}

api::MeasurementInput measurement() {
    api::MeasurementInput value;
    value.sequence.value = 1;
    value.measurement_id.value = "gnss-1";
    value.state_epoch_ns.nanoseconds = 1'020'000'000;
    value.arrival_timestamp.nanoseconds = 1'020'001'000;
    value.kind = api::MeasurementKind::PositionVelocity;
    value.origin_id.value = "origin-1";
    value.provider_evidence_ids = {{"provider-1"}, {"provider-2"}};
    value.precheck.status = api::MeasurementPrecheckStatus::Passed;
    value.precheck.reason_code = "passed";
    value.z = {1.01, 2.01, 3.01, 0.1, 0.2, 0.3};
    for (std::size_t index = 0; index < 6; ++index) value.R[index * 6 + index] = 1.0;
    return value;
}

std::uint64_t create(jni::HandleRegistry& registry, const api::InitialState& state = initialState()) {
    const auto [status, handle] = registry.create(jni::encodeInitialState(state));
    require(status == jni::BoundaryStatus::Ok && handle != 0, "handle creation failed");
    return handle;
}

void requireSameState(const api::StateSnapshot& direct, const api::StateSnapshot& boundary,
                      const std::string& context) {
    require(direct.sequence.value == boundary.sequence.value, context + ": state sequence differs");
    require(direct.epoch_ns.nanoseconds == boundary.epoch_ns.nanoseconds,
            context + ": state epoch differs");
    require(direct.navigation_frame == boundary.navigation_frame,
            context + ": navigation frame differs");
    require(direct.body_frame == boundary.body_frame, context + ": body frame differs");
    require(direct.position_n_m == boundary.position_n_m, context + ": position differs");
    require(direct.velocity_n_mps == boundary.velocity_n_mps, context + ": velocity differs");
    require(direct.q_n_b_wxyz == boundary.q_n_b_wxyz, context + ": attitude differs");
    require(direct.accel_bias_b_mps2 == boundary.accel_bias_b_mps2,
            context + ": accelerometer bias differs");
    require(direct.gyro_bias_b_radps == boundary.gyro_bias_b_radps,
            context + ": gyroscope bias differs");
    require(direct.origin_id.value == boundary.origin_id.value, context + ": origin differs");
    require(direct.mode == boundary.mode, context + ": navigation mode differs");
    require(direct.validity == boundary.validity, context + ": state validity differs");
}

void requireSameCovariance(const api::CovarianceSnapshot& direct,
                           const api::CovarianceSnapshot& boundary,
                           const std::string& context) {
    require(direct.state_sequence.value == boundary.state_sequence.value,
            context + ": covariance sequence differs");
    require(direct.epoch_ns.nanoseconds == boundary.epoch_ns.nanoseconds,
            context + ": covariance epoch differs");
    require(direct.ordering_id == boundary.ordering_id,
            context + ": covariance ordering differs");
    require(direct.covariance_15x15 == boundary.covariance_15x15,
            context + ": covariance values differ");
    require(direct.quality_flags == boundary.quality_flags,
            context + ": covariance quality differs");
}

void requireSameSnapshots(const api::NavigationCore& direct, const jni::SnapshotPair& boundary,
                          const std::string& context) {
    requireSameState(direct.stateSnapshot(), boundary.state, context);
    requireSameCovariance(direct.covarianceSnapshot(), boundary.covariance, context);
}

void requireSameResult(const api::PropagationResult& direct,
                       const api::PropagationResult& boundary,
                       const std::string& context) {
    require(direct.status == boundary.status, context + ": propagation status differs");
    require(direct.delta_time_seconds == boundary.delta_time_seconds,
            context + ": propagation delta time differs");
    require(direct.gap_detected == boundary.gap_detected,
            context + ": propagation gap decision differs");
    require(direct.state_sequence.value == boundary.state_sequence.value,
            context + ": propagation result sequence differs");
}

void requireSameResult(const api::MeasurementResult& direct,
                       const api::MeasurementResult& boundary,
                       const std::string& context) {
    require(direct.status == boundary.status, context + ": measurement status differs");
    require(direct.dimension == boundary.dimension, context + ": measurement dimension differs");
    require(direct.normalized_innovation_squared == boundary.normalized_innovation_squared,
            context + ": measurement innovation differs");
    require(direct.state_sequence.value == boundary.state_sequence.value,
            context + ": measurement result sequence differs");
}

jni::PropagationResponse propagate(jni::HandleRegistry& registry, std::uint64_t handle,
                                   const api::ImuBatch& input) {
    const auto [status, bytes] = registry.propagate(handle, jni::encodeImuBatch(input));
    require(status == jni::BoundaryStatus::Ok, "propagation boundary rejected valid wire input");
    const auto decoded = jni::decodePropagationResponse(bytes);
    require(decoded.status == jni::BoundaryStatus::Ok, "propagation response decode failed");
    require(decoded.value.boundary_status == jni::BoundaryStatus::Ok,
            "propagation response reported a boundary failure");
    return decoded.value;
}

jni::MeasurementResponse update(jni::HandleRegistry& registry, std::uint64_t handle,
                                const api::MeasurementInput& input) {
    const auto [status, bytes] = registry.update(handle, jni::encodeMeasurement(input));
    require(status == jni::BoundaryStatus::Ok, "measurement boundary rejected valid wire input");
    const auto decoded = jni::decodeMeasurementResponse(bytes);
    require(decoded.status == jni::BoundaryStatus::Ok, "measurement response decode failed");
    require(decoded.value.boundary_status == jni::BoundaryStatus::Ok,
            "measurement response reported a boundary failure");
    return decoded.value;
}

}  // namespace

int main() {
    run("complete_input_field_round_trip", [] {
        const auto initial = jni::decodeInitialState(jni::encodeInitialState(initialState()));
        require(initial.status == jni::BoundaryStatus::Ok, "initial decode failed");
        require(initial.value.state_sequence.value == 7, "initial sequence changed");
        require(initial.value.source_timestamp.nanoseconds == 1'000'000'000,
                "initial epoch changed");
        require(initial.value.clock_id.value == "boot-clock-1", "clock changed");
        require(initial.value.origin_id.value == "origin-1", "origin changed");
        require(initial.value.mode == api::NavigationMode::GnssAided, "mode changed");
        require(initial.value.navigation_frame == api::NavigationFrame::LocalNorthEastDown
                    && initial.value.body_frame == api::BodyFrame::PhysicalImuBody,
                "initial frames changed");
        require(initial.value.position_n_m == initialState().position_n_m, "position changed");
        require(initial.value.velocity_n_mps == initialState().velocity_n_mps,
                "velocity changed");
        require(initial.value.q_n_b_wxyz == initialState().q_n_b_wxyz,
                "quaternion changed");
        require(initial.value.accel_bias_b_mps2 == initialState().accel_bias_b_mps2
                    && initial.value.gyro_bias_b_radps == initialState().gyro_bias_b_radps,
                "biases changed");
        require(initial.value.covariance == initialState().covariance, "covariance changed");

        const auto imu = jni::decodeImuBatch(jni::encodeImuBatch(batch()));
        require(imu.status == jni::BoundaryStatus::Ok, "batch decode failed");
        require(imu.value.batch_id.value == "batch-1", "batch id changed");
        require(imu.value.first_seq.value == 10 && imu.value.last_seq.value == 11,
                "sequence range changed");
        require(imu.value.clock_id.value == "boot-clock-1", "batch clock changed");
        require(imu.value.gap_flags == static_cast<std::uint32_t>(api::ImuGapFlag::TimingGap),
                "gap flag changed");
        require(imu.value.samples[0].evidence_id.value == "imu-10"
                    && imu.value.samples[1].evidence_id.value == "imu-11",
                "constituent evidence changed");
        require(imu.value.samples[0].source_timestamp.nanoseconds == 1'010'000'000
                    && imu.value.samples[0].arrival_timestamp.nanoseconds == 1'010'001'000,
                "sample timestamps changed");
        require(imu.value.samples[0].body_frame == api::BodyFrame::PhysicalImuBody,
                "sample body frame changed");
        require(imu.value.samples[0].specific_force_b_mps2
                    == batch().samples[0].specific_force_b_mps2
                    && imu.value.samples[0].angular_rate_b_radps
                    == batch().samples[0].angular_rate_b_radps,
                "sample vectors changed");

        const auto gnss = jni::decodeMeasurement(jni::encodeMeasurement(measurement()));
        require(gnss.status == jni::BoundaryStatus::Ok, "measurement decode failed");
        require(gnss.value.measurement_id.value == "gnss-1", "measurement id changed");
        require(gnss.value.sequence.value == 1
                    && gnss.value.state_epoch_ns.nanoseconds == 1'020'000'000
                    && gnss.value.arrival_timestamp.nanoseconds == 1'020'001'000,
                "measurement sequence or timestamps changed");
        require(gnss.value.kind == api::MeasurementKind::PositionVelocity
                    && gnss.value.navigation_frame == api::NavigationFrame::LocalNorthEastDown,
                "measurement kind or frame changed");
        require(gnss.value.origin_id.value == "origin-1", "measurement origin changed");
        require(gnss.value.provider_evidence_ids.size() == 2
                    && gnss.value.provider_evidence_ids[1].value == "provider-2",
                "provider evidence changed");
        require(gnss.value.precheck.status == api::MeasurementPrecheckStatus::Passed
                    && gnss.value.precheck.reason_code == "passed",
                "precheck changed");
        require(gnss.value.z == measurement().z && gnss.value.R == measurement().R,
                "measurement values changed");
    });

    run("valid_batch_and_snapshot_round_trip", [] {
        jni::HandleRegistry registry;
        const auto handle = create(registry);
        const auto [status, bytes] = registry.propagate(handle, jni::encodeImuBatch(batch()));
        require(status == jni::BoundaryStatus::Ok, "propagation boundary failed");
        const auto response = jni::decodePropagationResponse(bytes);
        require(response.status == jni::BoundaryStatus::Ok, "response decode failed");
        require(response.value.result.status == api::PropagationStatus::AcceptedGap,
                "gap batch result changed");
        require(response.value.result.state_sequence.value == 9, "state sequence changed");
        require(response.value.snapshots.state.sequence.value
                    == response.value.snapshots.covariance.state_sequence.value,
                "state/covariance sequence diverged");
        require(response.value.snapshots.state.epoch_ns.nanoseconds
                    == response.value.snapshots.covariance.epoch_ns.nanoseconds,
                "state/covariance epoch diverged");
        require(response.value.snapshots.state.origin_id.value == "origin-1", "origin lost");
        require(response.value.snapshots.state.mode == api::NavigationMode::GnssAided,
                "mode lost");
        require(response.value.snapshots.state.validity == api::StateValidity::Valid,
                "validity lost");
        require(response.value.snapshots.state.navigation_frame
                    == api::NavigationFrame::LocalNorthEastDown
                    && response.value.snapshots.state.body_frame
                    == api::BodyFrame::PhysicalImuBody,
                "snapshot frames lost");
        require(response.value.snapshots.state.q_n_b_wxyz.size() == 4
                    && response.value.snapshots.state.accel_bias_b_mps2.size() == 3
                    && response.value.snapshots.state.gyro_bias_b_radps.size() == 3,
                "snapshot orientation or biases incomplete");
        require(response.value.snapshots.covariance.ordering_id
                    == "s2-error-state-v1:p_n,v_n,theta_b,bias_accel_b,bias_gyro_b",
                "ordering id lost");
        require(response.value.snapshots.covariance.quality_flags == 0U,
                "quality flags changed");
        require(response.value.snapshots.covariance.covariance_15x15.size() == 225,
                "covariance incomplete");
    });

    run("measurement_round_trip_preserves_result_and_snapshots", [] {
        jni::HandleRegistry registry;
        const auto handle = create(registry);
        require(registry.propagate(handle, jni::encodeImuBatch(batch())).first
                    == jni::BoundaryStatus::Ok,
                "setup propagation failed");
        const auto [status, bytes] = registry.update(handle, jni::encodeMeasurement(measurement()));
        require(status == jni::BoundaryStatus::Ok, "measurement boundary failed");
        const auto response = jni::decodeMeasurementResponse(bytes);
        require(response.status == jni::BoundaryStatus::Ok, "measurement response malformed");
        require(response.value.result.dimension == 6, "measurement kind/dimension changed");
        require(response.value.result.state_sequence.value
                    == response.value.snapshots.state.sequence.value,
                "measurement state sequence changed");
    });

    run("direct_and_jni_accepted_paths_are_exactly_equivalent", [] {
        api::NavigationCore direct(initialState());
        jni::HandleRegistry registry;
        const auto handle = create(registry);

        const auto propagation_input = batch();
        const auto direct_propagation = direct.propagate(propagation_input);
        const auto boundary_propagation = propagate(registry, handle, propagation_input);
        requireSameResult(direct_propagation, boundary_propagation.result,
                          "accepted propagation");
        requireSameSnapshots(direct, boundary_propagation.snapshots, "accepted propagation");

        const auto measurement_input = measurement();
        const auto direct_measurement = direct.update(measurement_input);
        const auto boundary_measurement = update(registry, handle, measurement_input);
        requireSameResult(direct_measurement, boundary_measurement.result,
                          "accepted measurement");
        requireSameSnapshots(direct, boundary_measurement.snapshots, "accepted measurement");
    });

    run("direct_and_jni_precheck_rejection_consume_the_same_evidence_id", [] {
        api::NavigationCore direct(initialState());
        jni::HandleRegistry registry;
        const auto handle = create(registry);
        auto input = measurement();
        input.measurement_id.value = "precheck-rejected";
        input.state_epoch_ns.nanoseconds = 1'000'000'000;
        input.arrival_timestamp.nanoseconds = 1'000'001'000;
        input.precheck.status = api::MeasurementPrecheckStatus::Rejected;
        input.precheck.reason_code = "provider_accuracy";

        const auto direct_rejection = direct.update(input);
        const auto boundary_rejection = update(registry, handle, input);
        requireSameResult(direct_rejection, boundary_rejection.result, "precheck rejection");
        requireSameSnapshots(direct, boundary_rejection.snapshots, "precheck rejection");
        require(direct_rejection.status == api::MeasurementStatus::RejectedPrecheck,
                "precheck fixture did not reach the intended rejection");

        input.precheck.status = api::MeasurementPrecheckStatus::Passed;
        input.precheck.reason_code = "passed";
        const auto direct_replay = direct.update(input);
        const auto boundary_replay = update(registry, handle, input);
        requireSameResult(direct_replay, boundary_replay.result, "precheck evidence replay");
        requireSameSnapshots(direct, boundary_replay.snapshots, "precheck evidence replay");
        require(direct_replay.status == api::MeasurementStatus::RejectedDuplicateEvidenceIdentifier,
                "precheck-rejected evidence ID was reusable");
    });

    run("direct_and_jni_innovation_rejection_consume_the_same_evidence_id", [] {
        auto state = initialState();
        state.covariance = api::identityCovariance(0.01);
        api::NavigationCore direct(state);
        jni::HandleRegistry registry;
        const auto handle = create(registry, state);
        auto input = measurement();
        input.measurement_id.value = "innovation-rejected";
        input.state_epoch_ns.nanoseconds = 1'000'000'000;
        input.arrival_timestamp.nanoseconds = 1'000'001'000;
        input.kind = api::MeasurementKind::Position;
        input.z = {100.0, -100.0, 30.0, 0.0, 0.0, 0.0};
        input.R = {};
        input.R[0] = 0.01;
        input.R[7] = 0.01;
        input.R[14] = 0.01;

        const auto direct_rejection = direct.update(input);
        const auto boundary_rejection = update(registry, handle, input);
        requireSameResult(direct_rejection, boundary_rejection.result, "innovation rejection");
        requireSameSnapshots(direct, boundary_rejection.snapshots, "innovation rejection");
        require(direct_rejection.status == api::MeasurementStatus::RejectedInnovationGate,
                "outlier fixture did not reach the innovation gate");

        const auto direct_replay = direct.update(input);
        const auto boundary_replay = update(registry, handle, input);
        requireSameResult(direct_replay, boundary_replay.result, "innovation evidence replay");
        requireSameSnapshots(direct, boundary_replay.snapshots, "innovation evidence replay");
        require(direct_replay.status == api::MeasurementStatus::RejectedDuplicateEvidenceIdentifier,
                "innovation-rejected evidence ID was reusable");
    });

    run("direct_and_jni_invalid_imu_consume_the_same_evidence_ids", [] {
        api::NavigationCore direct(initialState());
        jni::HandleRegistry registry;
        const auto handle = create(registry);
        auto input = batch();
        input.samples[0].angular_rate_b_radps[1] =
            std::numeric_limits<double>::quiet_NaN();

        const auto direct_rejection = direct.propagate(input);
        const auto boundary_rejection = propagate(registry, handle, input);
        requireSameResult(direct_rejection, boundary_rejection.result, "non-finite IMU rejection");
        requireSameSnapshots(direct, boundary_rejection.snapshots, "non-finite IMU rejection");
        require(direct_rejection.status == api::PropagationStatus::RejectedNonFinite,
                "non-finite fixture did not reach the intended rejection");

        input.samples[0].angular_rate_b_radps[1] = -0.02;
        const auto direct_replay = direct.propagate(input);
        const auto boundary_replay = propagate(registry, handle, input);
        requireSameResult(direct_replay, boundary_replay.result, "IMU evidence replay");
        requireSameSnapshots(direct, boundary_replay.snapshots, "IMU evidence replay");
        require(direct_replay.status == api::PropagationStatus::RejectedDuplicateEvidenceIdentifier,
                "invalid IMU evidence IDs were reusable");
    });

    run("malformed_wire_does_not_consume_evidence_or_mutate_state", [] {
        api::NavigationCore direct(initialState());
        jni::HandleRegistry registry;
        const auto handle = create(registry);
        const auto before = jni::decodeSnapshotResponse(registry.snapshot(handle).second);
        require(before.status == jni::BoundaryStatus::Ok, "initial snapshot decode failed");

        const auto input = batch();
        auto malformed = jni::encodeImuBatch(input);
        malformed.resize(malformed.size() - 1);
        const auto [malformed_status, malformed_response] = registry.propagate(handle, malformed);
        require(malformed_status == jni::BoundaryStatus::MalformedLength,
                "malformed wire payload reached the core");
        require(malformed_response.empty(), "malformed wire payload returned a core response");
        const auto after = jni::decodeSnapshotResponse(registry.snapshot(handle).second);
        require(after.status == jni::BoundaryStatus::Ok, "post-rejection snapshot decode failed");
        requireSameState(before.value.snapshots.state, after.value.snapshots.state,
                         "malformed wire rejection");
        requireSameCovariance(before.value.snapshots.covariance, after.value.snapshots.covariance,
                              "malformed wire rejection");

        const auto direct_result = direct.propagate(input);
        const auto boundary_result = propagate(registry, handle, input);
        requireSameResult(direct_result, boundary_result.result, "post-malformed propagation");
        requireSameSnapshots(direct, boundary_result.snapshots, "post-malformed propagation");
        require(direct_result.accepted(), "malformed wire payload consumed the valid evidence IDs");
    });

    run("null_stale_and_double_destroy", [] {
        jni::HandleRegistry registry;
        require(registry.destroy(0) == jni::BoundaryStatus::NullHandle,
                "null destroy not rejected");
        require(registry.snapshot(0).first == jni::BoundaryStatus::NullHandle,
                "null snapshot not rejected");
        const auto handle = create(registry);
        require(registry.destroy(handle) == jni::BoundaryStatus::Ok, "destroy failed");
        require(registry.destroy(handle) == jni::BoundaryStatus::StaleHandle,
                "double destroy not stale");
        require(registry.propagate(handle, jni::encodeImuBatch(batch())).first
                    == jni::BoundaryStatus::StaleHandle,
                "stale handle accepted");
    });

    run("malformed_buffers_and_lengths_rejected", [] {
        jni::HandleRegistry registry;
        auto bytes = jni::encodeInitialState(initialState());
        bytes[0] = std::byte{0};
        const auto bad_magic_status = registry.create(bytes).first;
        require(bad_magic_status == jni::BoundaryStatus::InvalidMagic,
                std::string("bad magic returned ") + jni::toString(bad_magic_status));
        const auto handle = create(registry);
        auto encoded = jni::encodeImuBatch(batch());
        encoded.resize(encoded.size() - 1);
        require(registry.propagate(handle, encoded).first == jni::BoundaryStatus::MalformedLength,
                "truncated sample array accepted");

        auto trailing = jni::encodeImuBatch(batch());
        trailing.push_back(std::byte{0});
        require(registry.propagate(handle, trailing).first == jni::BoundaryStatus::MalformedLength,
                "trailing wire payload accepted");

        auto wrong_declared_length = jni::encodeImuBatch(batch());
        wrong_declared_length[8] = std::byte{12};
        wrong_declared_length[9] = std::byte{0};
        wrong_declared_length[10] = std::byte{0};
        wrong_declared_length[11] = std::byte{0};
        require(registry.propagate(handle, wrong_declared_length).first
                    == jni::BoundaryStatus::MalformedLength,
                "incorrect declared wire length accepted");
    });

    run("core_rejections_are_not_repaired", [] {
        jni::HandleRegistry registry;
        const auto handle = create(registry);
        auto empty = batch();
        empty.samples.clear();
        empty.first_seq.value = 0;
        empty.last_seq.value = 0;
        auto response = jni::decodePropagationResponse(
            registry.propagate(handle, jni::encodeImuBatch(empty)).second);
        require(response.value.result.status == api::PropagationStatus::RejectedEmptyBatch,
                "empty batch was repaired");

        auto wrong_clock = batch();
        wrong_clock.clock_id.value = "other-clock";
        response = jni::decodePropagationResponse(
            registry.propagate(handle, jni::encodeImuBatch(wrong_clock)).second);
        require(response.value.result.status == api::PropagationStatus::RejectedClockMismatch,
                "clock mismatch was repaired");

        auto invalid_range = batch();
        invalid_range.first_seq.value = 99;
        response = jni::decodePropagationResponse(
            registry.propagate(handle, jni::encodeImuBatch(invalid_range)).second);
        require(response.value.result.status == api::PropagationStatus::RejectedInvalidSequenceRange,
                "invalid range was repaired");
    });

    run("duplicate_and_nonfinite_evidence_rejected", [] {
        jni::HandleRegistry duplicate_registry;
        const auto duplicate_handle = create(duplicate_registry);
        auto duplicate = batch();
        duplicate.samples[1].evidence_id = duplicate.samples[0].evidence_id;
        auto response = jni::decodePropagationResponse(
            duplicate_registry.propagate(duplicate_handle, jni::encodeImuBatch(duplicate)).second);
        require(response.value.result.status
                    == api::PropagationStatus::RejectedDuplicateEvidenceIdentifier,
                "duplicate evidence accepted");

        jni::HandleRegistry nonfinite_registry;
        const auto nonfinite_handle = create(nonfinite_registry);
        auto nonfinite = batch();
        nonfinite.samples[0].angular_rate_b_radps[1] =
            std::numeric_limits<double>::quiet_NaN();
        response = jni::decodePropagationResponse(
            nonfinite_registry.propagate(nonfinite_handle, jni::encodeImuBatch(nonfinite)).second);
        require(response.value.result.status == api::PropagationStatus::RejectedNonFinite,
                "non-finite value accepted");
        require(response.value.snapshots.state.epoch_ns.nanoseconds == 1'000'000'000,
                "rejected input changed state");
    });

    run("numerical_failure_publishes_invalid_fault", [] {
        jni::HandleRegistry registry;
        const auto handle = create(registry);
        auto overflow = batch();
        overflow.samples.resize(1);
        overflow.first_seq = overflow.samples.front().sequence;
        overflow.last_seq = overflow.samples.front().sequence;
        overflow.samples.front().specific_force_b_mps2 = {1.0e308, 1.0e308, 1.0e308};
        const auto response = jni::decodePropagationResponse(
            registry.propagate(handle, jni::encodeImuBatch(overflow)).second);
        require(response.value.result.status == api::PropagationStatus::NumericalFailure,
                "numerical failure hidden");
        require(response.value.snapshots.state.validity == api::StateValidity::Invalid,
                "numerical failure looked valid");
        require(response.value.snapshots.state.mode == api::NavigationMode::Fault,
                "numerical failure did not publish FAULT");
    });

    run("covariance_is_not_clipped_or_replaced", [] {
        auto state = initialState();
        state.covariance = {};
        for (std::size_t index = 0; index < 3; ++index) state.covariance[index * 15 + index] = 1e-4;
        for (std::size_t index = 3; index < 6; ++index) state.covariance[index * 15 + index] = 1e-4;
        for (std::size_t index = 6; index < 9; ++index) state.covariance[index * 15 + index] = 1e-6;
        jni::HandleRegistry registry;
        const auto handle = create(registry, state);
        const auto response = jni::decodeSnapshotResponse(registry.snapshot(handle).second);
        require(response.status == jni::BoundaryStatus::Ok, "snapshot decode failed");
        require(response.value.snapshots.covariance.covariance_15x15 == state.covariance,
                "covariance was clipped or replaced");
    });

    run("deterministic_repeated_execution", [] {
        jni::HandleRegistry first;
        jni::HandleRegistry second;
        const auto first_handle = create(first);
        const auto second_handle = create(second);
        const auto first_bytes = first.propagate(first_handle, jni::encodeImuBatch(batch())).second;
        const auto second_bytes = second.propagate(second_handle, jni::encodeImuBatch(batch())).second;
        require(first_bytes == second_bytes, "repeated JNI boundary output differs");
    });

    run("concurrent_calls_are_rejected_not_reordered", [] {
        jni::HandleRegistry registry;
        const auto handle = create(registry);
        auto large_batch = batch();
        large_batch.samples.clear();
        for (std::uint64_t index = 0; index < 1024; ++index) {
            large_batch.samples.push_back(sample(
                10 + index, 1'010'000'000 + static_cast<std::int64_t>(index) * 10'000'000,
                "imu-" + std::to_string(10 + index)));
        }
        large_batch.first_seq = large_batch.samples.front().sequence;
        large_batch.last_seq = large_batch.samples.back().sequence;
        const auto encoded = jni::encodeImuBatch(large_batch);

        constexpr int thread_count = 8;
        std::atomic<int> ready{0};
        std::atomic<bool> start{false};
        std::atomic<int> concurrent_rejections{0};
        std::vector<std::thread> threads;
        for (int index = 0; index < thread_count; ++index) {
            threads.emplace_back([&] {
                ready.fetch_add(1);
                while (!start.load()) std::this_thread::yield();
                if (registry.propagate(handle, encoded).first
                    == jni::BoundaryStatus::ConcurrentCall) {
                    concurrent_rejections.fetch_add(1);
                }
            });
        }
        while (ready.load() != thread_count) std::this_thread::yield();
        start.store(true);
        for (auto& thread : threads) thread.join();
        require(concurrent_rejections.load() > 0, "overlapping calls were silently serialized");
    });

    run("jni_exception_translation", [] {
        require(jni::guardedCall(true, [] { return jni::BoundaryStatus::Ok; })
                    == jni::BoundaryStatus::PendingJniException,
                "pending JNI exception ignored");
        require(jni::guardedCall(false, []() -> jni::BoundaryStatus {
                    throw std::bad_alloc();
                }) == jni::BoundaryStatus::AllocationFailure,
                "allocation failure mistranslated");
        require(jni::guardedCall(false, []() -> jni::BoundaryStatus {
                    throw std::runtime_error("native");
                }) == jni::BoundaryStatus::NativeException,
                "native exception mistranslated");
    });

    const int passed = total - failed;
    std::cout << "JNI boundary tests: total=" << total << " passed=" << passed
              << " failed=" << failed << " skipped=0\n";
    return failed == 0 ? 0 : 1;
}
