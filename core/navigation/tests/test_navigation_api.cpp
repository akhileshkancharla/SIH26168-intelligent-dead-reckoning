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
    state.position_n_m = {1.0, 2.0, 3.0};
    state.velocity_n_mps = {0.1, 0.2, 0.3};
    state.accel_bias_b_mps2 = {0.01, -0.02, 0.03};
    state.gyro_bias_b_radps = {0.001, -0.002, 0.003};
    state.covariance = api::identityCovariance(0.5);
    return state;
}

api::PropagationInput stationaryImu(std::uint64_t sequence, std::int64_t timestamp_ns) {
    api::PropagationInput input;
    input.sequence.value = sequence;
    input.source_timestamp.nanoseconds = timestamp_ns;
    input.arrival_timestamp.nanoseconds = timestamp_ns + 1'000;
    input.specific_force_b_mps2 = {0.0, 0.0, -9.80665};
    return input;
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
    input.evidence_id.value = id;
    input.source_timestamp.nanoseconds = timestamp_ns;
    input.arrival_timestamp.nanoseconds = timestamp_ns + 1'000;
    input.validity = api::MeasurementValidity::Valid;
    input.kind = api::MeasurementKind::Position;
    input.position_n_m = {1.1, 2.0, 3.0};
    input.covariance = diagonalMeasurementCovariance(1.0);
    return input;
}

bool equalState(const api::StateSnapshot& left, const api::StateSnapshot& right) {
    return left.state_sequence.value == right.state_sequence.value
        && left.source_timestamp.nanoseconds == right.source_timestamp.nanoseconds
        && left.position_n_m == right.position_n_m
        && left.velocity_n_mps == right.velocity_n_mps
        && left.q_n_b_wxyz == right.q_n_b_wxyz
        && left.accel_bias_b_mps2 == right.accel_bias_b_mps2
        && left.gyro_bias_b_radps == right.gyro_bias_b_radps;
}

}  // namespace

int main() {
    static_assert(!std::is_same_v<api::SourceTimestamp, api::ArrivalTimestamp>);
    static_assert(!std::is_reference_v<decltype(std::declval<const api::NavigationCore&>().stateSnapshot())>);
    static_assert(!std::is_reference_v<decltype(std::declval<const api::NavigationCore&>().covarianceSnapshot())>);

    run("construction_and_initialization", [] {
        api::NavigationCore core(initialState());
        const auto state = core.stateSnapshot();
        require(state.state_sequence.value == 7, "initial state sequence changed");
        require(state.source_timestamp.nanoseconds == 1'000'000'000, "initial timestamp changed");
        require(state.position_n_m == std::array<double, 3>{1.0, 2.0, 3.0},
                "initial position changed");
        require(state.navigation_frame == api::NavigationFrame::LocalNorthEastDown,
                "navigation frame changed");
        require(state.body_frame == api::BodyFrame::PhysicalImuBody, "body frame changed");
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
        const auto accepted = core.propagate(stationaryImu(10, 1'010'000'000));
        require(accepted.accepted(), "valid propagation rejected");
        require(accepted.state_sequence.value == 8, "accepted propagation did not advance state sequence");

        const auto repeated_sequence = core.propagate(stationaryImu(10, 1'020'000'000));
        require(repeated_sequence.status == api::PropagationStatus::RejectedInvalidSequence,
                "duplicate propagation sequence accepted");

        const auto repeated_time = core.propagate(stationaryImu(11, 1'010'000'000));
        require(repeated_time.status == api::PropagationStatus::RejectedNonMonotonicSourceTimestamp,
                "non-monotonic source timestamp accepted");
    });

    run("arrival_and_nonfinite_propagation_rejection", [] {
        api::NavigationCore core(initialState());
        auto arrival = stationaryImu(1, 1'010'000'000);
        arrival.arrival_timestamp.nanoseconds = arrival.source_timestamp.nanoseconds - 1;
        require(core.propagate(arrival).status == api::PropagationStatus::RejectedArrivalBeforeSource,
                "arrival-before-source input accepted");

        auto nonfinite = stationaryImu(2, 1'010'000'000);
        nonfinite.angular_rate_b_radps[1] = std::numeric_limits<double>::infinity();
        require(core.propagate(nonfinite).status == api::PropagationStatus::RejectedNonFinite,
                "non-finite IMU input accepted");
        require(core.stateSnapshot().source_timestamp.nanoseconds == 1'000'000'000,
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
        measurement.position_n_m = {100.0, -100.0, 30.0};
        measurement.covariance = diagonalMeasurementCovariance(0.01);
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
        measurement.validity = api::MeasurementValidity::Invalid;
        require(core.update(measurement).status == api::MeasurementStatus::RejectedInvalidValidity,
                "invalid measurement was not rejected");
        measurement.validity = api::MeasurementValidity::Valid;
        require(core.update(measurement).status
                    == api::MeasurementStatus::RejectedDuplicateEvidenceIdentifier,
                "invalid evidence identifier was reusable");
    });

    run("nonfinite_measurement_rejection", [] {
        api::NavigationCore core(initialState());
        auto measurement = positionMeasurement("nan", 1, 1'000'000'000);
        measurement.position_n_m[0] = std::numeric_limits<double>::quiet_NaN();
        require(core.update(measurement).status == api::MeasurementStatus::RejectedNonFinite,
                "non-finite measurement accepted");
        require(core.consumedEvidenceCount() == 1, "rejected evidence was not consumed");
    });

    run("invalid_covariance_rejection", [] {
        api::NavigationCore core(initialState());
        auto measurement = positionMeasurement("bad-covariance", 1, 1'000'000'000);
        measurement.covariance[1] = 2.0;
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
        covariance.covariance[0] = 999.0;
        require(core.stateSnapshot().position_n_m[0] == 1.0, "caller mutated internal state");
        require(core.covarianceSnapshot().covariance[0] == 0.5,
                "caller mutated internal covariance");
        require(core.covarianceSnapshot().state_sequence.value == 7,
                "covariance snapshot sequence mismatch");
    });

    run("deterministic_repeated_execution", [] {
        api::NavigationCore first(initialState());
        api::NavigationCore second(initialState());
        for (std::uint64_t sequence = 1; sequence <= 5; ++sequence) {
            const auto timestamp = 1'000'000'000 + static_cast<std::int64_t>(sequence) * 10'000'000;
            require(first.propagate(stationaryImu(sequence, timestamp)).status
                        == second.propagate(stationaryImu(sequence, timestamp)).status,
                    "propagation decisions differ");
        }
        auto measurement = positionMeasurement("deterministic", 1, 1'050'000'000);
        require(first.update(measurement).status == second.update(measurement).status,
                "measurement decisions differ");
        require(equalState(first.stateSnapshot(), second.stateSnapshot()),
                "repeated state execution differs");
        require(first.covarianceSnapshot().covariance == second.covarianceSnapshot().covariance,
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
        require(wrapper.propagate(input).accepted(), "wrapper propagation rejected");
        s2::ImuSample raw_sample;
        raw_sample.timestamp_ns = input.source_timestamp.nanoseconds;
        raw_sample.specific_force_b = s2::Vec3(0.0, 0.0, -9.80665);
        require(accepted.propagate(raw_sample).accepted, "accepted S2 propagation rejected");

        const auto snapshot = wrapper.stateSnapshot();
        require(snapshot.position_n_m[0] == accepted.state().position_n.x()
                    && snapshot.position_n_m[1] == accepted.state().position_n.y()
                    && snapshot.position_n_m[2] == accepted.state().position_n.z(),
                "wrapper changed accepted S2 position behavior");
        require(wrapper.covarianceSnapshot().covariance[0] == accepted.state().covariance(0, 0),
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
        require(wrapper.covarianceSnapshot().covariance[0] == accepted.state().covariance(0, 0),
                "wrapper changed accepted S2 measurement covariance");
    });

    const int passed = total - failures;
    std::cout << "Portable API tests: total=" << total << " passed=" << passed
              << " failed=" << failures << " skipped=0\n";
    return failures == 0 ? 0 : 1;
}
