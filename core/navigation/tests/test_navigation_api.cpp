#include "sih26168/navigation_core.hpp"

#include "s2_oracle/navigation_core.hpp"

#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <type_traits>

namespace api = sih26168::navigation;

namespace {

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

api::InitialState initialState() {
    api::InitialState state;
    state.state_sequence.value = 7;
    state.source_timestamp.nanoseconds = 1'000'000'000;
    state.clock_id.value = "boot-clock-1";
    state.origin_id.value = "origin-1";
    state.mode = api::NavigationMode::GnssAided;
    state.position_n_m = {1.0, 2.0, 3.0};
    state.velocity_n_mps = {0.1, 0.2, 0.3};
    state.accel_bias_b_mps2 = {0.01, -0.02, 0.03};
    state.gyro_bias_b_radps = {0.001, -0.002, 0.003};
    state.covariance = api::identityCovariance(0.5);
    return state;
}

api::ImuSample stationaryImu(std::uint64_t sequence, std::int64_t timestamp_ns) {
    api::ImuSample input;
    input.sequence.value = sequence;
    input.evidence_id.value = "imu-" + std::to_string(sequence);
    input.source_timestamp.nanoseconds = timestamp_ns;
    input.arrival_timestamp.nanoseconds = timestamp_ns + 1'000;
    input.specific_force_b_mps2 = {0.0, 0.0, -9.80665};
    return input;
}

api::ImuBatch singleBatch(const api::ImuSample& sample) {
    api::ImuBatch batch;
    batch.batch_id.value = "batch-" + std::to_string(sample.sequence.value);
    batch.samples = {sample};
    batch.first_seq = sample.sequence;
    batch.last_seq = sample.sequence;
    batch.clock_id.value = "boot-clock-1";
    return batch;
}

api::MeasurementCovariance diagonalMeasurementCovariance(double value) {
    api::MeasurementCovariance covariance{};
    for (std::size_t index = 0; index < 6; ++index) covariance[index * 6 + index] = value;
    return covariance;
}

api::MeasurementInput positionMeasurement(const std::string& id,
                                          std::uint64_t sequence,
                                          std::int64_t timestamp_ns) {
    api::MeasurementInput input;
    input.sequence.value = sequence;
    input.measurement_id.value = id;
    input.state_epoch_ns.nanoseconds = timestamp_ns;
    input.arrival_timestamp.nanoseconds = timestamp_ns + 1'000;
    input.origin_id.value = "origin-1";
    input.provider_evidence_ids = {api::EvidenceIdentifier{"provider-" + id}};
    input.precheck.status = api::MeasurementPrecheckStatus::Passed;
    input.kind = api::MeasurementKind::Position;
    input.z = {1.1, 2.0, 3.0, 0.0, 0.0, 0.0};
    input.R = diagonalMeasurementCovariance(1.0);
    return input;
}

bool equalState(const api::StateSnapshot& left, const api::StateSnapshot& right) {
    return left.sequence.value == right.sequence.value
        && left.epoch_ns.nanoseconds == right.epoch_ns.nanoseconds
        && left.position_n_m == right.position_n_m
        && left.velocity_n_mps == right.velocity_n_mps
        && left.q_n_b_wxyz == right.q_n_b_wxyz
        && left.accel_bias_b_mps2 == right.accel_bias_b_mps2
        && left.gyro_bias_b_radps == right.gyro_bias_b_radps
        && left.origin_id.value == right.origin_id.value
        && left.mode == right.mode
        && left.validity == right.validity;
}

}  // namespace

int main() {
    static_assert(!std::is_same_v<api::SourceTimestamp, api::ArrivalTimestamp>);
    static_assert(!std::is_reference_v<decltype(std::declval<const api::NavigationCore&>().stateSnapshot())>);
    static_assert(!std::is_reference_v<decltype(std::declval<const api::NavigationCore&>().covarianceSnapshot())>);

    run("screen_consumes_identity_without_scientific_correction", [] {
        api::NavigationCore core(initialState());
        const auto input = positionMeasurement("return", 1, 1'000'000'000);
        const auto before_state = core.stateSnapshot();
        const auto before_covariance = core.covarianceSnapshot();
        const auto before_count = core.consumedEvidenceCount();
        const auto first = core.screen(input);
        const auto repeated = core.screen(input);
        require(first.passesGate() && first.dimension == 3
                    && repeated.status
                        == api::MeasurementStatus::RejectedDuplicateEvidenceIdentifier,
                "screened evidence was not consumed by C-07");
        require(equalState(core.stateSnapshot(), before_state)
                    && core.covarianceSnapshot().covariance_15x15
                        == before_covariance.covariance_15x15
                    && core.consumedEvidenceCount() == before_count + 1,
                "screening changed scientific state/covariance or missed the evidence ledger");
        const auto bypass = core.update(input);
        require(bypass.status == api::MeasurementStatus::RejectedDuplicateEvidenceIdentifier
                    && equalState(core.stateSnapshot(), before_state),
                "screened ID was accepted through the direct C-07 update API");
        auto later = input;
        later.measurement_id.value = "independent-return";
        later.sequence.value = 2;
        const auto applied = core.update(later);
        require(applied.accepted()
                    && applied.normalized_innovation_squared
                        == first.normalized_innovation_squared
                    && core.consumedEvidenceCount() == before_count + 2,
                "independent final fix did not enter C-07 exactly once");
    });

    run("screen_rejects_biased_fix_without_scientific_update", [] {
        api::NavigationCore core(initialState());
        auto input = positionMeasurement("biased-return", 1, 1'000'000'000);
        input.z[0] = 100.0;
        const auto before = core.stateSnapshot();
        const auto screened = core.screen(input);
        require(screened.status == api::MeasurementStatus::RejectedInnovationGate
                    && !screened.passesGate()
                    && equalState(core.stateSnapshot(), before)
                    && core.consumedEvidenceCount() == 1
                    && core.update(input).status
                        == api::MeasurementStatus::RejectedDuplicateEvidenceIdentifier,
                "biased return influenced C-07 during screening");
    });

    run("malformed_screen_cannot_be_upgraded_on_representation", [] {
        api::NavigationCore core(initialState());
        auto input = positionMeasurement("malformed", 1, 1'000'000'000);
        input.precheck.status = api::MeasurementPrecheckStatus::Rejected;
        require(core.screen(input).status == api::MeasurementStatus::RejectedPrecheck
                    && core.consumedEvidenceCount() == 1,
                "malformed canonical evidence was not consumed on presentation");
        input.precheck.status = api::MeasurementPrecheckStatus::Passed;
        require(core.update(input).status
                    == api::MeasurementStatus::RejectedDuplicateEvidenceIdentifier,
                "malformed screened evidence was upgraded and accepted");
    });

    run("construction_and_initialization", [] {
        api::NavigationCore core(initialState());
        const auto state = core.stateSnapshot();
        require(state.sequence.value == 7, "initial state sequence changed");
        require(state.epoch_ns.nanoseconds == 1'000'000'000, "initial timestamp changed");
        require(state.position_n_m == std::array<double, 3>{1.0, 2.0, 3.0},
                "initial position changed");
        require(state.navigation_frame == api::NavigationFrame::LocalNorthEastDown,
                "navigation frame changed");
        require(state.body_frame == api::BodyFrame::PhysicalImuBody, "body frame changed");
        require(state.origin_id.value == "origin-1", "origin identity changed");
        require(state.mode == api::NavigationMode::GnssAided, "navigation mode changed");
        require(state.validity == api::StateValidity::Valid, "valid state marked invalid");
    });

    run("construction_rejects_nonfinite", [] {
        auto state = initialState();
        state.position_n_m[0] = std::numeric_limits<double>::quiet_NaN();
        bool rejected = false;
        try {
            api::NavigationCore core(state);
        } catch (const std::invalid_argument&) {
            rejected = true;
        }
        require(rejected, "non-finite initial state accepted");
    });

    run("construction_accepts_exact_covariance_floors_without_clipping", [] {
        auto state = initialState();
        state.covariance = {};
        for (std::size_t index = 0; index < 3; ++index) {
            state.covariance[index * 15 + index] = 1.0e-4;
        }
        for (std::size_t index = 3; index < 6; ++index) {
            state.covariance[index * 15 + index] = 1.0e-4;
        }
        for (std::size_t index = 6; index < 9; ++index) {
            state.covariance[index * 15 + index] = 1.0e-6;
        }
        api::NavigationCore core(state);
        const auto covariance = core.covarianceSnapshot().covariance_15x15;
        require(covariance[0] == 1.0e-4 && covariance[3 * 15 + 3] == 1.0e-4
                    && covariance[6 * 15 + 6] == 1.0e-6,
                "boundary covariance was clipped or replaced");
        require(covariance[9 * 15 + 9] == 0.0,
                "an unauthorized bias variance floor was introduced");
    });

    run("construction_rejects_below_position_variance_floor", [] {
        auto state = initialState();
        state.covariance[0] = std::nextafter(1.0e-4, 0.0);
        bool rejected = false;
        try { api::NavigationCore core(state); } catch (const std::invalid_argument&) { rejected = true; }
        require(rejected, "below-floor position variance accepted");
    });

    run("construction_rejects_below_velocity_variance_floor", [] {
        auto state = initialState();
        state.covariance[3 * 15 + 3] = std::nextafter(1.0e-4, 0.0);
        bool rejected = false;
        try { api::NavigationCore core(state); } catch (const std::invalid_argument&) { rejected = true; }
        require(rejected, "below-floor velocity variance accepted");
    });

    run("construction_rejects_below_attitude_variance_floor", [] {
        auto state = initialState();
        state.covariance[6 * 15 + 6] = std::nextafter(1.0e-6, 0.0);
        bool rejected = false;
        try { api::NavigationCore core(state); } catch (const std::invalid_argument&) { rejected = true; }
        require(rejected, "below-floor attitude variance accepted");
    });

    run("construction_rejects_zero_covariance", [] {
        auto state = initialState();
        state.covariance = {};
        bool rejected = false;
        try { api::NavigationCore core(state); } catch (const std::invalid_argument&) { rejected = true; }
        require(rejected, "zero covariance accepted");
    });

    run("explicit_units_and_frame_contract", [] {
        auto input = stationaryImu(1, 1'010'000'000);
        require(input.body_frame == api::BodyFrame::PhysicalImuBody, "IMU body frame not explicit");
        require(input.source_timestamp.nanoseconds == 1'010'000'000, "source ns changed");
        require(input.arrival_timestamp.nanoseconds == 1'010'001'000, "arrival ns changed");
        require(std::string(api::toString(api::PropagationStatus::Accepted)) == "accepted",
                "propagation status mapping changed");
        require(std::string(api::toString(api::MeasurementStatus::RejectedInnovationGate))
                    == "rejected_innovation_gate",
                "measurement status mapping changed");
    });

    run("propagation_and_monotonic_validation", [] {
        api::NavigationCore core(initialState());
        const auto accepted = core.propagate(singleBatch(stationaryImu(10, 1'010'000'000)));
        require(accepted.accepted(), "valid propagation rejected");
        require(accepted.state_sequence.value == 8, "accepted propagation did not advance state sequence");

        auto repeated_sequence_sample = stationaryImu(10, 1'020'000'000);
        repeated_sequence_sample.evidence_id.value = "imu-repeated-sequence";
        const auto repeated_sequence = core.propagate(singleBatch(repeated_sequence_sample));
        require(repeated_sequence.status == api::PropagationStatus::RejectedInvalidSequence,
                "duplicate propagation sequence accepted");

        const auto repeated_time = core.propagate(singleBatch(stationaryImu(11, 1'010'000'000)));
        require(repeated_time.status == api::PropagationStatus::RejectedNonMonotonicSourceTimestamp,
                "non-monotonic source timestamp accepted");
    });

    run("imu_batch_preserves_clock_range_gap_and_constituent_evidence", [] {
        api::NavigationCore core(initialState());
        api::ImuBatch batch;
        batch.batch_id.value = "batch-provenance";
        batch.samples = {stationaryImu(10, 1'010'000'000), stationaryImu(11, 1'020'000'000)};
        batch.first_seq = batch.samples.front().sequence;
        batch.last_seq = batch.samples.back().sequence;
        batch.gap_flags = static_cast<api::ImuGapFlags>(api::ImuGapFlag::MissingSamples);
        batch.clock_id.value = "boot-clock-1";
        const auto result = core.propagate(batch);
        require(result.status == api::PropagationStatus::AcceptedGap, "declared gap was discarded");
        require(result.state_sequence.value == 9, "batch samples did not advance state individually");
        require(core.consumedEvidenceCount() == 2, "constituent evidence was not retained");
    });

    run("imu_batch_rejects_clock_mismatch_and_duplicate_evidence", [] {
        api::NavigationCore wrong_clock(initialState());
        auto batch = singleBatch(stationaryImu(1, 1'010'000'000));
        batch.clock_id.value = "different-clock";
        require(wrong_clock.propagate(batch).status == api::PropagationStatus::RejectedClockMismatch,
                "cross-domain IMU batch accepted");

        api::NavigationCore duplicate(initialState());
        batch = singleBatch(stationaryImu(1, 1'010'000'000));
        auto second = stationaryImu(2, 1'020'000'000);
        second.evidence_id = batch.samples.front().evidence_id;
        batch.samples.push_back(second);
        batch.last_seq = second.sequence;
        require(duplicate.propagate(batch).status
                    == api::PropagationStatus::RejectedDuplicateEvidenceIdentifier,
                "duplicate constituent evidence accepted");
    });

    run("arrival_and_nonfinite_propagation_rejection", [] {
        api::NavigationCore core(initialState());
        auto arrival = stationaryImu(1, 1'010'000'000);
        arrival.arrival_timestamp.nanoseconds = arrival.source_timestamp.nanoseconds - 1;
        require(core.propagate(singleBatch(arrival)).status
                    == api::PropagationStatus::RejectedArrivalBeforeSource,
                "arrival-before-source input accepted");

        auto nonfinite = stationaryImu(2, 1'010'000'000);
        nonfinite.angular_rate_b_radps[1] = std::numeric_limits<double>::infinity();
        require(core.propagate(singleBatch(nonfinite)).status
                    == api::PropagationStatus::RejectedNonFinite,
                "non-finite IMU input accepted");
        require(core.stateSnapshot().epoch_ns.nanoseconds == 1'000'000'000,
                "rejected propagation changed state");
    });

    run("accepted_measurement_result", [] {
        api::NavigationCore core(initialState());
        const auto result = core.update(positionMeasurement("accepted", 1, 1'000'000'000));
        require(result.accepted(), "inlier measurement rejected");
        require(result.dimension == 3, "wrong measurement dimension");
        require(result.state_sequence.value == 8, "accepted measurement did not advance state sequence");
    });

    run("rejected_measurement_result", [] {
        auto state = initialState();
        state.covariance = api::identityCovariance(0.01);
        api::NavigationCore core(state);
        auto measurement = positionMeasurement("outlier", 1, 1'000'000'000);
        measurement.z = {100.0, -100.0, 30.0, 0.0, 0.0, 0.0};
        measurement.R = diagonalMeasurementCovariance(0.01);
        const auto result = core.update(measurement);
        require(result.status == api::MeasurementStatus::RejectedInnovationGate,
                "outlier measurement was not gated");
        require(result.state_sequence.value == 7, "rejected measurement changed state sequence");
    });

    run("duplicate_evidence_identifier_protection", [] {
        api::NavigationCore core(initialState());
        const auto measurement = positionMeasurement("once", 1, 1'000'000'000);
        require(core.update(measurement).accepted(), "first evidence presentation rejected");
        const auto duplicate = core.update(measurement);
        require(duplicate.status == api::MeasurementStatus::RejectedDuplicateEvidenceIdentifier,
                "duplicate evidence accepted");
        require(core.consumedEvidenceCount() == 1, "evidence count changed on duplicate");
    });

    run("invalid_measurement_is_consumed", [] {
        api::NavigationCore core(initialState());
        auto measurement = positionMeasurement("invalid", 1, 1'000'000'000);
        measurement.precheck.status = api::MeasurementPrecheckStatus::Rejected;
        measurement.precheck.reason_code = "provider_accuracy";
        require(core.update(measurement).status == api::MeasurementStatus::RejectedPrecheck,
                "invalid measurement was not rejected");
        measurement.precheck.status = api::MeasurementPrecheckStatus::Passed;
        require(core.update(measurement).status
                    == api::MeasurementStatus::RejectedDuplicateEvidenceIdentifier,
                "invalid evidence identifier was reusable");
    });

    run("measurement_origin_provider_and_precheck_are_enforced", [] {
        api::NavigationCore origin_core(initialState());
        auto wrong_origin = positionMeasurement("wrong-origin", 1, 1'000'000'000);
        wrong_origin.origin_id.value = "origin-2";
        require(origin_core.update(wrong_origin).status == api::MeasurementStatus::RejectedOriginMismatch,
                "measurement for a different origin was accepted");
        wrong_origin.origin_id.value = "origin-1";
        require(origin_core.update(wrong_origin).status
                    == api::MeasurementStatus::RejectedDuplicateEvidenceIdentifier,
                "origin-rejected measurement ID was reusable");

        api::NavigationCore provider_core(initialState());
        auto no_provider = positionMeasurement("no-provider", 1, 1'000'000'000);
        no_provider.provider_evidence_ids.clear();
        require(provider_core.update(no_provider).status
                    == api::MeasurementStatus::RejectedEmptyProviderEvidence,
                "measurement without provider provenance was accepted");
    });

    run("nonfinite_measurement_rejection", [] {
        api::NavigationCore core(initialState());
        auto measurement = positionMeasurement("nan", 1, 1'000'000'000);
        measurement.z[0] = std::numeric_limits<double>::quiet_NaN();
        require(core.update(measurement).status == api::MeasurementStatus::RejectedNonFinite,
                "non-finite measurement accepted");
        require(core.consumedEvidenceCount() == 1, "rejected evidence was not consumed");
    });

    run("invalid_covariance_rejection", [] {
        api::NavigationCore core(initialState());
        auto measurement = positionMeasurement("bad-covariance", 1, 1'000'000'000);
        measurement.R[1] = 2.0;
        require(core.update(measurement).status
                    == api::MeasurementStatus::RejectedInvalidCovariance,
                "asymmetric measurement covariance accepted");
        require(core.consumedEvidenceCount() == 1, "invalid covariance evidence was not consumed");
    });

    run("state_and_covariance_snapshots_are_copies", [] {
        api::NavigationCore core(initialState());
        auto state = core.stateSnapshot();
        auto covariance = core.covarianceSnapshot();
        state.position_n_m[0] = 999.0;
        covariance.covariance_15x15[0] = 999.0;
        require(core.stateSnapshot().position_n_m[0] == 1.0, "caller mutated internal state");
        require(core.covarianceSnapshot().covariance_15x15[0] == 0.5,
                "caller mutated internal covariance");
        require(core.covarianceSnapshot().state_sequence.value == 7,
                "covariance snapshot sequence mismatch");
    });

    run("state_and_uncertainty_snapshots_share_sequence_and_epoch", [] {
        api::NavigationCore core(initialState());
        const auto state = core.stateSnapshot();
        const auto uncertainty = core.covarianceSnapshot();
        require(state.sequence.value == uncertainty.state_sequence.value,
                "uncertainty is tied to a different state sequence");
        require(state.epoch_ns.nanoseconds == uncertainty.epoch_ns.nanoseconds,
                "uncertainty is tied to a different scientific epoch");
        require(uncertainty.ordering_id
                    == "s2-error-state-v1:p_n,v_n,theta_b,bias_accel_b,bias_gyro_b",
                "covariance ordering identifier changed");
        require(uncertainty.quality_flags
                    == static_cast<api::CovarianceQualityFlags>(api::CovarianceQualityFlag::None),
                "healthy covariance reported a quality defect");
    });

    run("numerical_failure_surfaces_invalid_fault_state", [] {
        api::NavigationCore core(initialState());
        auto sample = stationaryImu(1, 1'010'000'000);
        sample.specific_force_b_mps2 = {1.0e308, 1.0e308, 1.0e308};
        require(core.propagate(singleBatch(sample)).status == api::PropagationStatus::NumericalFailure,
                "overflowing propagation did not surface a numerical failure");
        const auto state = core.stateSnapshot();
        require(state.validity == api::StateValidity::Invalid,
                "numerical failure returned an apparently valid state");
        require(state.mode == api::NavigationMode::Fault,
                "numerical failure did not enter FAULT mode");
    });

    run("deterministic_repeated_execution", [] {
        api::NavigationCore first(initialState());
        api::NavigationCore second(initialState());
        for (std::uint64_t sequence = 1; sequence <= 5; ++sequence) {
            const auto timestamp = 1'000'000'000 + static_cast<std::int64_t>(sequence) * 10'000'000;
            require(first.propagate(singleBatch(stationaryImu(sequence, timestamp))).status
                        == second.propagate(singleBatch(stationaryImu(sequence, timestamp))).status,
                    "propagation decisions differ");
        }
        auto measurement = positionMeasurement("deterministic", 1, 1'050'000'000);
        require(first.update(measurement).status == second.update(measurement).status,
                "measurement decisions differ");
        require(equalState(first.stateSnapshot(), second.stateSnapshot()),
                "repeated state execution differs");
        require(first.covarianceSnapshot().covariance_15x15
                    == second.covarianceSnapshot().covariance_15x15,
                "repeated covariance execution differs");
    });

    run("accepted_s2_behavior_compatibility", [] {
        auto initial = initialState();
        api::NavigationCore wrapper(initial);

        s2::NominalState raw_state;
        raw_state.timestamp_ns = initial.source_timestamp.nanoseconds;
        raw_state.position_n = s2::Vec3(1.0, 2.0, 3.0);
        raw_state.velocity_n = s2::Vec3(0.1, 0.2, 0.3);
        raw_state.accel_bias_b = s2::Vec3(0.01, -0.02, 0.03);
        raw_state.gyro_bias_b = s2::Vec3(0.001, -0.002, 0.003);
        raw_state.covariance = s2::Mat15::Identity() * 0.5;
        s2::NavigationCore accepted(raw_state);

        const auto input = stationaryImu(1, 1'010'000'000);
        require(wrapper.propagate(singleBatch(input)).accepted(), "wrapper propagation rejected");
        s2::ImuSample raw_sample;
        raw_sample.timestamp_ns = input.source_timestamp.nanoseconds;
        raw_sample.specific_force_b = s2::Vec3(0.0, 0.0, -9.80665);
        require(accepted.propagate(raw_sample).accepted, "accepted S2 propagation rejected");

        const auto snapshot = wrapper.stateSnapshot();
        require(snapshot.position_n_m[0] == accepted.state().position_n.x()
                    && snapshot.position_n_m[1] == accepted.state().position_n.y()
                    && snapshot.position_n_m[2] == accepted.state().position_n.z(),
                "wrapper changed accepted S2 position behavior");
        require(wrapper.covarianceSnapshot().covariance_15x15[0]
                    == accepted.state().covariance(0, 0),
                "wrapper changed accepted S2 covariance behavior");

        auto public_measurement = positionMeasurement("compatibility", 1, 1'010'000'000);
        const auto public_result = wrapper.update(public_measurement);
        s2::GnssMeasurement raw_measurement;
        raw_measurement.id = "compatibility";
        raw_measurement.timestamp_ns = 1'010'000'000;
        raw_measurement.kind = s2::MeasurementKind::Position;
        raw_measurement.value.head<3>() = s2::Vec3(1.1, 2.0, 3.0);
        raw_measurement.covariance = s2::Mat6::Identity();
        const auto raw_result = accepted.update(raw_measurement);
        require(public_result.accepted() == raw_result.accepted,
                "wrapper changed accepted S2 measurement decision");
        require(wrapper.stateSnapshot().position_n_m[0] == accepted.state().position_n.x(),
                "wrapper changed accepted S2 measurement state");
        require(wrapper.covarianceSnapshot().covariance_15x15[0]
                    == accepted.state().covariance(0, 0),
                "wrapper changed accepted S2 measurement covariance");
    });

    const int passed = total - failures;
    std::cout << "Portable API tests: total=" << total << " passed=" << passed
              << " failed=" << failures << " skipped=0\n";
    return failures == 0 ? 0 : 1;
}
