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

constexpr std::uint32_t flagValue(CovarianceQualityFlag flag) {
    return static_cast<std::uint32_t>(flag);
}

CovarianceQualityFlags covarianceQualityFlags(const s2::Mat15& covariance) {
    CovarianceQualityFlags flags = flagValue(CovarianceQualityFlag::None);
    if (!covariance.allFinite()) flags |= flagValue(CovarianceQualityFlag::NonFinite);
    if (covariance.allFinite()
        && (covariance - covariance.transpose()).cwiseAbs().maxCoeff() > 1.0e-12) {
        flags |= flagValue(CovarianceQualityFlag::NonSymmetric);
    }
    if (covariance.allFinite() && (flags & flagValue(CovarianceQualityFlag::NonSymmetric)) == 0U) {
        const Eigen::SelfAdjointEigenSolver<s2::Mat15> solver(covariance);
        if (solver.info() != Eigen::Success || solver.eigenvalues().minCoeff() < -1.0e-12) {
            flags |= flagValue(CovarianceQualityFlag::PsdDefect);
        }
    }
    return flags;
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
        : core(makeState(initial_state)),
          state_sequence(initial_state.state_sequence),
          clock_id(initial_state.clock_id),
          origin_id(initial_state.origin_id),
          mode(initial_state.mode) {
        if (clock_id.value.empty()) throw std::invalid_argument("Initial clock_id must not be empty");
        if (origin_id.value.empty()) throw std::invalid_argument("Initial origin_id must not be empty");
        if (mode == NavigationMode::Fault) {
            throw std::invalid_argument("Initial navigation mode must not be FAULT");
        }
    }

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
        for (int index = 0; index < 3; ++index) {
            if (state.covariance(index, index) < 1.0e-4) {
                throw std::invalid_argument("Initial position variance must be at least 1e-4 m^2");
            }
        }
        for (int index = 3; index < 6; ++index) {
            if (state.covariance(index, index) < 1.0e-4) {
                throw std::invalid_argument(
                    "Initial velocity variance must be at least 1e-4 (m/s)^2");
            }
        }
        for (int index = 6; index < 9; ++index) {
            if (state.covariance(index, index) < 1.0e-6) {
                throw std::invalid_argument("Initial attitude variance must be at least 1e-6 rad^2");
            }
        }
        return state;
    }

    void markFault() {
        mode = NavigationMode::Fault;
        validity = StateValidity::Invalid;
    }

    s2::NavigationCore core;
    SequenceIdentifier state_sequence{};
    ClockIdentifier clock_id{};
    OriginIdentifier origin_id{};
    NavigationMode mode{NavigationMode::Initializing};
    StateValidity validity{StateValidity::Valid};
    std::optional<std::uint64_t> last_propagation_sequence;
    std::optional<std::uint64_t> last_measurement_sequence;
    std::unordered_set<std::string> consumed_evidence_ids;
};

NavigationCore::NavigationCore(const InitialState& initial_state)
    : impl_(std::make_unique<Impl>(initial_state)) {}

NavigationCore::~NavigationCore() = default;
NavigationCore::NavigationCore(NavigationCore&&) noexcept = default;
NavigationCore& NavigationCore::operator=(NavigationCore&&) noexcept = default;

PropagationResult NavigationCore::propagate(const ImuBatch& input) {
    PropagationResult output;
    output.state_sequence = impl_->state_sequence;

    if (input.batch_id.value.empty()) {
        output.status = PropagationStatus::RejectedEmptyBatchIdentifier;
        return output;
    }
    if (input.clock_id.value.empty()) {
        output.status = PropagationStatus::RejectedEmptyClockIdentifier;
        return output;
    }
    if (input.clock_id.value != impl_->clock_id.value) {
        output.status = PropagationStatus::RejectedClockMismatch;
        return output;
    }
    if (input.samples.empty()) {
        output.status = PropagationStatus::RejectedEmptyBatch;
        return output;
    }
    if (input.first_seq.value != input.samples.front().sequence.value
        || input.last_seq.value != input.samples.back().sequence.value
        || input.first_seq.value > input.last_seq.value) {
        output.status = PropagationStatus::RejectedInvalidSequenceRange;
        return output;
    }

    bool empty_evidence = false;
    bool duplicate_evidence = false;
    for (const ImuSample& sample : input.samples) {
        if (sample.evidence_id.value.empty()) {
            empty_evidence = true;
        } else if (!impl_->consumed_evidence_ids.insert(sample.evidence_id.value).second) {
            duplicate_evidence = true;
        }
    }
    if (empty_evidence) {
        output.status = PropagationStatus::RejectedEmptyEvidenceIdentifier;
        return output;
    }
    if (duplicate_evidence) {
        output.status = PropagationStatus::RejectedDuplicateEvidenceIdentifier;
        return output;
    }

    std::uint64_t prior_sequence = 0;
    bool first = true;
    for (const ImuSample& sample : input.samples) {
        if ((!first && sample.sequence.value <= prior_sequence)
            || (impl_->last_propagation_sequence
                && sample.sequence.value <= *impl_->last_propagation_sequence)) {
            output.status = PropagationStatus::RejectedInvalidSequence;
            return output;
        }
        first = false;
        prior_sequence = sample.sequence.value;
        if (sample.body_frame != BodyFrame::PhysicalImuBody) {
            output.status = PropagationStatus::RejectedInvalidFrame;
            return output;
        }
        if (sample.arrival_timestamp.nanoseconds < sample.source_timestamp.nanoseconds) {
            output.status = PropagationStatus::RejectedArrivalBeforeSource;
            return output;
        }
        if (!allFinite(sample.specific_force_b_mps2) || !allFinite(sample.angular_rate_b_radps)) {
            output.status = PropagationStatus::RejectedNonFinite;
            return output;
        }
    }

    output.status = PropagationStatus::Accepted;
    output.gap_detected = input.gap_flags != static_cast<ImuGapFlags>(ImuGapFlag::None);
    for (const ImuSample& input_sample : input.samples) {
        impl_->last_propagation_sequence = input_sample.sequence.value;
        s2::ImuSample sample;
        sample.timestamp_ns = input_sample.source_timestamp.nanoseconds;
        sample.specific_force_b = toVec3(input_sample.specific_force_b_mps2);
        sample.angular_rate_b = toVec3(input_sample.angular_rate_b_radps);
        try {
            const s2::PropagationResult result = impl_->core.propagate(sample);
            output.status = mapPropagationStatus(result);
            output.delta_time_seconds += result.dt_s;
            output.gap_detected = output.gap_detected || result.gap_detected;
        } catch (const std::runtime_error&) {
            output.status = PropagationStatus::NumericalFailure;
        }
        if (!output.accepted()) {
            if (output.status == PropagationStatus::NumericalFailure) impl_->markFault();
            output.state_sequence = impl_->state_sequence;
            return output;
        }
        ++impl_->state_sequence.value;
    }
    if (output.gap_detected) output.status = PropagationStatus::AcceptedGap;
    output.state_sequence = impl_->state_sequence;
    return output;
}

MeasurementResult NavigationCore::update(const MeasurementInput& input) {
    MeasurementResult output;
    output.state_sequence = impl_->state_sequence;

    if (input.measurement_id.value.empty()) {
        output.status = MeasurementStatus::RejectedEmptyEvidenceIdentifier;
        return output;
    }
    if (!impl_->consumed_evidence_ids.insert(input.measurement_id.value).second) {
        output.status = MeasurementStatus::RejectedDuplicateEvidenceIdentifier;
        return output;
    }
    if (impl_->last_measurement_sequence
        && input.sequence.value <= *impl_->last_measurement_sequence) {
        output.status = MeasurementStatus::RejectedInvalidSequence;
        return output;
    }
    impl_->last_measurement_sequence = input.sequence.value;

    if (input.precheck.status != MeasurementPrecheckStatus::Passed) {
        output.status = MeasurementStatus::RejectedPrecheck;
        return output;
    }
    if (input.origin_id.value.empty()) {
        output.status = MeasurementStatus::RejectedEmptyOriginIdentifier;
        return output;
    }
    if (input.origin_id.value != impl_->origin_id.value) {
        output.status = MeasurementStatus::RejectedOriginMismatch;
        return output;
    }
    if (input.provider_evidence_ids.empty()
        || std::any_of(input.provider_evidence_ids.begin(), input.provider_evidence_ids.end(),
                       [](const EvidenceIdentifier& id) { return id.value.empty(); })) {
        output.status = MeasurementStatus::RejectedEmptyProviderEvidence;
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
    if (input.arrival_timestamp.nanoseconds < input.state_epoch_ns.nanoseconds) {
        output.status = MeasurementStatus::RejectedArrivalBeforeSource;
        return output;
    }
    if (input.state_epoch_ns.nanoseconds != impl_->core.state().timestamp_ns) {
        output.status = MeasurementStatus::RejectedTimestampMismatch;
        return output;
    }
    if (!allFinite(input.z) || !allFinite(input.R)) {
        output.status = MeasurementStatus::RejectedNonFinite;
        return output;
    }

    const s2::Mat6 covariance = toMat6(input.R);
    const bool covariance_valid = input.kind == MeasurementKind::PositionVelocity
        ? isSymmetricPositiveSemidefinite<6>(covariance)
        : isSymmetricPositiveSemidefinite<3>(covariance.topLeftCorner<3, 3>());
    if (!covariance_valid) {
        output.status = MeasurementStatus::RejectedInvalidCovariance;
        return output;
    }

    s2::GnssMeasurement measurement;
    measurement.id = input.measurement_id.value;
    measurement.timestamp_ns = input.state_epoch_ns.nanoseconds;
    measurement.kind = toS2Kind(input.kind);
    if (input.kind == MeasurementKind::Velocity) {
        measurement.value.head<3>() = toVec3({input.z[0], input.z[1], input.z[2]});
    } else {
        measurement.value.head<3>() = toVec3({input.z[0], input.z[1], input.z[2]});
        if (input.kind == MeasurementKind::PositionVelocity) {
            measurement.value.tail<3>() = toVec3({input.z[3], input.z[4], input.z[5]});
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
        impl_->markFault();
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
    output.sequence = impl_->state_sequence;
    output.epoch_ns.nanoseconds = state.timestamp_ns;
    output.position_n_m = fromVec3(state.position_n);
    output.velocity_n_mps = fromVec3(state.velocity_n);
    output.q_n_b_wxyz = {state.q_n_b.w(), state.q_n_b.x(), state.q_n_b.y(), state.q_n_b.z()};
    output.accel_bias_b_mps2 = fromVec3(state.accel_bias_b);
    output.gyro_bias_b_radps = fromVec3(state.gyro_bias_b);
    output.origin_id = impl_->origin_id;
    output.mode = impl_->mode;
    output.validity = impl_->validity;
    if (covarianceQualityFlags(state.covariance) != 0U || !state.position_n.allFinite()
        || !state.velocity_n.allFinite() || !state.q_n_b.coeffs().allFinite()
        || !state.accel_bias_b.allFinite() || !state.gyro_bias_b.allFinite()) {
        output.mode = NavigationMode::Fault;
        output.validity = StateValidity::Invalid;
    }
    return output;
}

CovarianceSnapshot NavigationCore::covarianceSnapshot() const {
    CovarianceSnapshot output;
    output.state_sequence = impl_->state_sequence;
    output.epoch_ns.nanoseconds = impl_->core.state().timestamp_ns;
    output.ordering_id = "s2-error-state-v1:p_n,v_n,theta_b,bias_accel_b,bias_gyro_b";
    output.covariance_15x15 = fromMat15(impl_->core.state().covariance);
    output.quality_flags = covarianceQualityFlags(impl_->core.state().covariance);
    return output;
}

std::size_t NavigationCore::consumedEvidenceCount() const {
    return impl_->consumed_evidence_ids.size();
}

const char* toString(PropagationStatus status) {
    switch (status) {
        case PropagationStatus::Accepted: return "accepted";
        case PropagationStatus::AcceptedGap: return "accepted_gap";
        case PropagationStatus::RejectedEmptyBatch: return "rejected_empty_batch";
        case PropagationStatus::RejectedEmptyBatchIdentifier:
            return "rejected_empty_batch_identifier";
        case PropagationStatus::RejectedEmptyClockIdentifier:
            return "rejected_empty_clock_identifier";
        case PropagationStatus::RejectedClockMismatch: return "rejected_clock_mismatch";
        case PropagationStatus::RejectedInvalidSequenceRange:
            return "rejected_invalid_sequence_range";
        case PropagationStatus::RejectedEmptyEvidenceIdentifier:
            return "rejected_empty_evidence_identifier";
        case PropagationStatus::RejectedDuplicateEvidenceIdentifier:
            return "rejected_duplicate_evidence_identifier";
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
        case MeasurementStatus::RejectedPrecheck: return "rejected_precheck";
        case MeasurementStatus::RejectedEmptyOriginIdentifier:
            return "rejected_empty_origin_identifier";
        case MeasurementStatus::RejectedOriginMismatch: return "rejected_origin_mismatch";
        case MeasurementStatus::RejectedEmptyProviderEvidence:
            return "rejected_empty_provider_evidence";
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
