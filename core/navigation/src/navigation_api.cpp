#include "sih26168/navigation_core.hpp"

#include "s2_oracle/navigation_core.hpp"

#include <Eigen/Core>
#include <Eigen/Eigenvalues>

#include <algorithm>
#include <cmath>
#include <limits>
#include <optional>
#include <stdexcept>
#include <unordered_set>
#include <utility>

namespace sih26168::navigation {
namespace {

template<std::size_t N>
bool allFinite(const std::array<double, N>& values) {
    return std::all_of(values.begin(), values.end(), [](double value) {
        return std::isfinite(value);
    });
}

s2::Vec3 toVec3(const std::array<double, 3>& values) {
    return {values[0], values[1], values[2]};
}

std::array<double, 3> fromVec3(const s2::Vec3& value) {
    return {value.x(), value.y(), value.z()};
}

s2::Mat15 toMat15(const Covariance15& values) {
    s2::Mat15 result;
    for (int row = 0; row < 15; ++row) {
        for (int column = 0; column < 15; ++column) {
            result(row, column) = values[static_cast<std::size_t>(row * 15 + column)];
        }
    }
    return result;
}

Covariance15 fromMat15(const s2::Mat15& value) {
    Covariance15 result{};
    for (int row = 0; row < 15; ++row) {
        for (int column = 0; column < 15; ++column) {
            result[static_cast<std::size_t>(row * 15 + column)] = value(row, column);
        }
    }
    return result;
}

s2::Mat6 toMat6(const MeasurementCovariance& values) {
    s2::Mat6 result;
    for (int row = 0; row < 6; ++row) {
        for (int column = 0; column < 6; ++column) {
            result(row, column) = values[static_cast<std::size_t>(row * 6 + column)];
        }
    }
    return result;
}

template<int N>
bool isSymmetricPositiveSemidefinite(const Eigen::Matrix<double, N, N>& value) {
    if ((value - value.transpose()).cwiseAbs().maxCoeff() > 1.0e-12) return false;
    const Eigen::SelfAdjointEigenSolver<Eigen::Matrix<double, N, N>> solver(value);
    return solver.info() == Eigen::Success && solver.eigenvalues().minCoeff() >= -1.0e-12;
}

bool validMeasurementKind(MeasurementKind kind) {
    return kind == MeasurementKind::Position
        || kind == MeasurementKind::Velocity
        || kind == MeasurementKind::PositionVelocity;
}

s2::MeasurementKind toS2Kind(MeasurementKind kind) {
    switch (kind) {
        case MeasurementKind::Position:
            return s2::MeasurementKind::Position;
        case MeasurementKind::Velocity:
            return s2::MeasurementKind::Velocity;
        case MeasurementKind::PositionVelocity:
            return s2::MeasurementKind::PositionVelocity;
    }
    throw std::invalid_argument("Unknown measurement kind");
}

PropagationStatus mapPropagationStatus(const s2::PropagationResult& result) {
    if (result.status == "accepted") return PropagationStatus::Accepted;
    if (result.status == "accepted_gap") return PropagationStatus::AcceptedGap;
    if (result.status == "invalid_nonmonotonic_timestamp") {
        return PropagationStatus::RejectedNonMonotonicSourceTimestamp;
    }
    if (result.status == "invalid_nonfinite_imu") return PropagationStatus::RejectedNonFinite;
    if (result.status == "invalid_dt") return PropagationStatus::RejectedInvalidDeltaTime;
    return PropagationStatus::NumericalFailure;
}

MeasurementStatus mapMeasurementStatus(const s2::MeasurementResult& result) {
    if (result.status == "accepted") return MeasurementStatus::Accepted;
    if (result.status == "duplicate_measurement_id") {
        return MeasurementStatus::RejectedDuplicateEvidenceIdentifier;
    }
    if (result.status == "measurement_timestamp_mismatch") {
        return MeasurementStatus::RejectedTimestampMismatch;
    }
    if (result.status == "invalid_nonfinite_measurement") {
        return MeasurementStatus::RejectedNonFinite;
    }
    if (result.status == "invalid_innovation_covariance") {
        return MeasurementStatus::RejectedInnovationCovariance;
    }
    if (result.status == "rejected_nis_gate") {
        return MeasurementStatus::RejectedInnovationGate;
    }
    return MeasurementStatus::NumericalFailure;
}

}  // namespace

Covariance15 identityCovariance(double diagonal) {
    Covariance15 result{};
    for (std::size_t index = 0; index < 15; ++index) {
        result[index * 15 + index] = diagonal;
    }
    return result;
}

bool PropagationResult::accepted() const {
    return status == PropagationStatus::Accepted || status == PropagationStatus::AcceptedGap;
}

bool MeasurementResult::accepted() const {
    return status == MeasurementStatus::Accepted;
}

class NavigationCore::Impl {
public:
    explicit Impl(const InitialState& initial_state)
        : core(makeState(initial_state)), state_sequence(initial_state.state_sequence) {}

    static s2::NominalState makeState(const InitialState& input) {
        if (input.navigation_frame != NavigationFrame::LocalNorthEastDown
            || input.body_frame != BodyFrame::PhysicalImuBody) {
            throw std::invalid_argument("Unsupported initial coordinate frame");
        }
        if (input.source_timestamp.nanoseconds < 0
            || !allFinite(input.position_n_m)
            || !allFinite(input.velocity_n_mps)
            || !allFinite(input.q_n_b_wxyz)
            || !allFinite(input.accel_bias_b_mps2)
            || !allFinite(input.gyro_bias_b_radps)
            || !allFinite(input.covariance)) {
            throw std::invalid_argument("Initial state contains an invalid value");
        }
        const double quaternion_squared_norm =
            input.q_n_b_wxyz[0] * input.q_n_b_wxyz[0]
            + input.q_n_b_wxyz[1] * input.q_n_b_wxyz[1]
            + input.q_n_b_wxyz[2] * input.q_n_b_wxyz[2]
            + input.q_n_b_wxyz[3] * input.q_n_b_wxyz[3];
        if (!(quaternion_squared_norm > 0.0) || !std::isfinite(quaternion_squared_norm)) {
            throw std::invalid_argument("Initial quaternion must be finite and nonzero");
        }

        s2::NominalState state;
        state.timestamp_ns = input.source_timestamp.nanoseconds;
        state.position_n = toVec3(input.position_n_m);
        state.velocity_n = toVec3(input.velocity_n_mps);
        state.q_n_b = Eigen::Quaterniond(input.q_n_b_wxyz[0], input.q_n_b_wxyz[1],
                                         input.q_n_b_wxyz[2], input.q_n_b_wxyz[3]);
        state.accel_bias_b = toVec3(input.accel_bias_b_mps2);
        state.gyro_bias_b = toVec3(input.gyro_bias_b_radps);
        state.covariance = toMat15(input.covariance);
        if (!isSymmetricPositiveSemidefinite<15>(state.covariance)) {
            throw std::invalid_argument("Initial covariance must be symmetric positive semidefinite");
        }
        return state;
    }

    s2::NavigationCore core;
    SequenceIdentifier state_sequence{};
    std::optional<std::uint64_t> last_propagation_sequence;
    std::optional<std::uint64_t> last_measurement_sequence;
    std::unordered_set<std::string> consumed_evidence_ids;
};

NavigationCore::NavigationCore(const InitialState& initial_state)
    : impl_(std::make_unique<Impl>(initial_state)) {}

NavigationCore::~NavigationCore() = default;
NavigationCore::NavigationCore(NavigationCore&&) noexcept = default;
NavigationCore& NavigationCore::operator=(NavigationCore&&) noexcept = default;

PropagationResult NavigationCore::propagate(const PropagationInput& input) {
    PropagationResult output;
    output.state_sequence = impl_->state_sequence;

    if (impl_->last_propagation_sequence
        && input.sequence.value <= *impl_->last_propagation_sequence) {
        output.status = PropagationStatus::RejectedInvalidSequence;
        return output;
    }
    impl_->last_propagation_sequence = input.sequence.value;

    if (input.body_frame != BodyFrame::PhysicalImuBody) {
        output.status = PropagationStatus::RejectedInvalidFrame;
        return output;
    }
    if (input.arrival_timestamp.nanoseconds < input.source_timestamp.nanoseconds) {
        output.status = PropagationStatus::RejectedArrivalBeforeSource;
        return output;
    }
    if (!allFinite(input.specific_force_b_mps2) || !allFinite(input.angular_rate_b_radps)) {
        output.status = PropagationStatus::RejectedNonFinite;
        return output;
    }

    s2::ImuSample sample;
    sample.timestamp_ns = input.source_timestamp.nanoseconds;
    sample.specific_force_b = toVec3(input.specific_force_b_mps2);
    sample.angular_rate_b = toVec3(input.angular_rate_b_radps);
    const s2::PropagationResult result = impl_->core.propagate(sample);
    output.status = mapPropagationStatus(result);
    output.delta_time_seconds = result.dt_s;
    output.gap_detected = result.gap_detected;
    if (output.accepted()) {
        ++impl_->state_sequence.value;
        output.state_sequence = impl_->state_sequence;
    }
    return output;
}

MeasurementResult NavigationCore::update(const MeasurementInput& input) {
    MeasurementResult output;
    output.state_sequence = impl_->state_sequence;

    if (input.evidence_id.value.empty()) {
        output.status = MeasurementStatus::RejectedEmptyEvidenceIdentifier;
        return output;
    }
    if (!impl_->consumed_evidence_ids.insert(input.evidence_id.value).second) {
        output.status = MeasurementStatus::RejectedDuplicateEvidenceIdentifier;
        return output;
    }
    if (impl_->last_measurement_sequence
        && input.sequence.value <= *impl_->last_measurement_sequence) {
        output.status = MeasurementStatus::RejectedInvalidSequence;
        return output;
    }
    impl_->last_measurement_sequence = input.sequence.value;

    if (input.validity != MeasurementValidity::Valid) {
        output.status = MeasurementStatus::RejectedInvalidValidity;
        return output;
    }
    if (input.navigation_frame != NavigationFrame::LocalNorthEastDown) {
        output.status = MeasurementStatus::RejectedInvalidFrame;
        return output;
    }
    if (!validMeasurementKind(input.kind)) {
        output.status = MeasurementStatus::RejectedInvalidKind;
        return output;
    }
    if (input.arrival_timestamp.nanoseconds < input.source_timestamp.nanoseconds) {
        output.status = MeasurementStatus::RejectedArrivalBeforeSource;
        return output;
    }
    if (input.source_timestamp.nanoseconds != impl_->core.state().timestamp_ns) {
        output.status = MeasurementStatus::RejectedTimestampMismatch;
        return output;
    }
    if (!allFinite(input.position_n_m) || !allFinite(input.velocity_n_mps)
        || !allFinite(input.covariance)) {
        output.status = MeasurementStatus::RejectedNonFinite;
        return output;
    }

    const s2::Mat6 covariance = toMat6(input.covariance);
    const bool covariance_valid = input.kind == MeasurementKind::PositionVelocity
        ? isSymmetricPositiveSemidefinite<6>(covariance)
        : isSymmetricPositiveSemidefinite<3>(covariance.topLeftCorner<3, 3>());
    if (!covariance_valid) {
        output.status = MeasurementStatus::RejectedInvalidCovariance;
        return output;
    }

    s2::GnssMeasurement measurement;
    measurement.id = input.evidence_id.value;
    measurement.timestamp_ns = input.source_timestamp.nanoseconds;
    measurement.kind = toS2Kind(input.kind);
    if (input.kind == MeasurementKind::Velocity) {
        measurement.value.head<3>() = toVec3(input.velocity_n_mps);
    } else {
        measurement.value.head<3>() = toVec3(input.position_n_m);
        if (input.kind == MeasurementKind::PositionVelocity) {
            measurement.value.tail<3>() = toVec3(input.velocity_n_mps);
        }
    }
    measurement.covariance = covariance;

    try {
        const s2::MeasurementResult result = impl_->core.update(measurement);
        output.status = mapMeasurementStatus(result);
        output.dimension = result.dimension;
        output.normalized_innovation_squared = result.nis;
    } catch (const std::runtime_error&) {
        output.status = MeasurementStatus::NumericalFailure;
        return output;
    }
    if (output.accepted()) {
        ++impl_->state_sequence.value;
        output.state_sequence = impl_->state_sequence;
    }
    return output;
}

StateSnapshot NavigationCore::stateSnapshot() const {
    const s2::NominalState& state = impl_->core.state();
    StateSnapshot output;
    output.state_sequence = impl_->state_sequence;
    output.source_timestamp.nanoseconds = state.timestamp_ns;
    output.position_n_m = fromVec3(state.position_n);
    output.velocity_n_mps = fromVec3(state.velocity_n);
    output.q_n_b_wxyz = {state.q_n_b.w(), state.q_n_b.x(), state.q_n_b.y(), state.q_n_b.z()};
    output.accel_bias_b_mps2 = fromVec3(state.accel_bias_b);
    output.gyro_bias_b_radps = fromVec3(state.gyro_bias_b);
    return output;
}

CovarianceSnapshot NavigationCore::covarianceSnapshot() const {
    CovarianceSnapshot output;
    output.state_sequence = impl_->state_sequence;
    output.source_timestamp.nanoseconds = impl_->core.state().timestamp_ns;
    output.covariance = fromMat15(impl_->core.state().covariance);
    return output;
}

std::size_t NavigationCore::consumedEvidenceCount() const {
    return impl_->consumed_evidence_ids.size();
}

const char* toString(PropagationStatus status) {
    switch (status) {
        case PropagationStatus::Accepted: return "accepted";
        case PropagationStatus::AcceptedGap: return "accepted_gap";
        case PropagationStatus::RejectedInvalidSequence: return "rejected_invalid_sequence";
        case PropagationStatus::RejectedNonMonotonicSourceTimestamp:
            return "rejected_nonmonotonic_source_timestamp";
        case PropagationStatus::RejectedArrivalBeforeSource: return "rejected_arrival_before_source";
        case PropagationStatus::RejectedInvalidFrame: return "rejected_invalid_frame";
        case PropagationStatus::RejectedNonFinite: return "rejected_nonfinite";
        case PropagationStatus::RejectedInvalidDeltaTime: return "rejected_invalid_delta_time";
        case PropagationStatus::NumericalFailure: return "numerical_failure";
    }
    return "unknown";
}

const char* toString(MeasurementStatus status) {
    switch (status) {
        case MeasurementStatus::Accepted: return "accepted";
        case MeasurementStatus::RejectedEmptyEvidenceIdentifier:
            return "rejected_empty_evidence_identifier";
        case MeasurementStatus::RejectedDuplicateEvidenceIdentifier:
            return "rejected_duplicate_evidence_identifier";
        case MeasurementStatus::RejectedInvalidSequence: return "rejected_invalid_sequence";
        case MeasurementStatus::RejectedInvalidValidity: return "rejected_invalid_validity";
        case MeasurementStatus::RejectedTimestampMismatch: return "rejected_timestamp_mismatch";
        case MeasurementStatus::RejectedArrivalBeforeSource: return "rejected_arrival_before_source";
        case MeasurementStatus::RejectedInvalidFrame: return "rejected_invalid_frame";
        case MeasurementStatus::RejectedInvalidKind: return "rejected_invalid_kind";
        case MeasurementStatus::RejectedNonFinite: return "rejected_nonfinite";
        case MeasurementStatus::RejectedInvalidCovariance: return "rejected_invalid_covariance";
        case MeasurementStatus::RejectedInnovationCovariance:
            return "rejected_innovation_covariance";
        case MeasurementStatus::RejectedInnovationGate: return "rejected_innovation_gate";
        case MeasurementStatus::NumericalFailure: return "numerical_failure";
    }
    return "unknown";
}

}  // namespace sih26168::navigation
