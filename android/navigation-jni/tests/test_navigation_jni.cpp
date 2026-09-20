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
