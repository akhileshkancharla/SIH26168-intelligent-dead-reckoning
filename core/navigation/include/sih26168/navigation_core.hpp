#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>

namespace sih26168::navigation {

// All timestamps are nanoseconds in one boot-scoped monotonic clock domain.
// SourceTimestamp records when the producer sampled the value. ArrivalTimestamp
// records when the callback or adapter received it; no conversion is performed.
struct SourceTimestamp {
    std::int64_t nanoseconds{0};
};

struct ArrivalTimestamp {
    std::int64_t nanoseconds{0};
};

struct SequenceIdentifier {
    std::uint64_t value{0};
};

struct EvidenceIdentifier {
    std::string value;
};

enum class NavigationFrame {
    LocalNorthEastDown,
};

enum class BodyFrame {
    PhysicalImuBody,
};

enum class MeasurementValidity {
    Valid,
    Invalid,
};

enum class MeasurementKind {
    Position,
    Velocity,
    PositionVelocity,
};

using Covariance15 = std::array<double, 15 * 15>;
using MeasurementCovariance = std::array<double, 6 * 6>;

// Returns a row-major 15x15 covariance with the requested diagonal.
Covariance15 identityCovariance(double diagonal = 1.0);

struct InitialState {
    SequenceIdentifier state_sequence{};
    SourceTimestamp source_timestamp{};
    NavigationFrame navigation_frame{NavigationFrame::LocalNorthEastDown};
    BodyFrame body_frame{BodyFrame::PhysicalImuBody};
    std::array<double, 3> position_n_m{};          // local NED [north,east,down], metres
    std::array<double, 3> velocity_n_mps{};       // local NED, metres/second
    std::array<double, 4> q_n_b_wxyz{1.0, 0.0, 0.0, 0.0};  // active body-to-NED quaternion
    std::array<double, 3> accel_bias_b_mps2{};    // physical IMU body, metres/second^2
    std::array<double, 3> gyro_bias_b_radps{};    // physical IMU body, radians/second
    Covariance15 covariance{identityCovariance()}; // row-major S2 error ordering; squared SI units
};

struct PropagationInput {
    SequenceIdentifier sequence{};
    SourceTimestamp source_timestamp{};
    ArrivalTimestamp arrival_timestamp{};
    BodyFrame body_frame{BodyFrame::PhysicalImuBody};
    std::array<double, 3> specific_force_b_mps2{}; // physical IMU body, metres/second^2
    std::array<double, 3> angular_rate_b_radps{};  // physical IMU body, radians/second
};

struct MeasurementInput {
    SequenceIdentifier sequence{};
    EvidenceIdentifier evidence_id{};
    SourceTimestamp source_timestamp{};
    ArrivalTimestamp arrival_timestamp{};
    MeasurementValidity validity{MeasurementValidity::Invalid};
    MeasurementKind kind{MeasurementKind::Position};
    NavigationFrame navigation_frame{NavigationFrame::LocalNorthEastDown};
    std::array<double, 3> position_n_m{};       // local NED, metres
    std::array<double, 3> velocity_n_mps{};    // local NED, metres/second
    // Row-major. Position covariance occupies [0:3,0:3], velocity-only also
    // uses [0:3,0:3], and combined position/velocity uses the full 6x6 matrix.
    // Entries carry the squared/cross SI units implied by measurement kind.
    MeasurementCovariance covariance{};
};

enum class PropagationStatus {
    Accepted,
    AcceptedGap,
    RejectedInvalidSequence,
    RejectedNonMonotonicSourceTimestamp,
    RejectedArrivalBeforeSource,
    RejectedInvalidFrame,
    RejectedNonFinite,
    RejectedInvalidDeltaTime,
    NumericalFailure,
};

enum class MeasurementStatus {
    Accepted,
    RejectedEmptyEvidenceIdentifier,
    RejectedDuplicateEvidenceIdentifier,
    RejectedInvalidSequence,
    RejectedInvalidValidity,
    RejectedTimestampMismatch,
    RejectedArrivalBeforeSource,
    RejectedInvalidFrame,
    RejectedInvalidKind,
    RejectedNonFinite,
    RejectedInvalidCovariance,
    RejectedInnovationCovariance,
    RejectedInnovationGate,
    NumericalFailure,
};

struct PropagationResult {
    PropagationStatus status{PropagationStatus::NumericalFailure};
    double delta_time_seconds{0.0};
    bool gap_detected{false};
    SequenceIdentifier state_sequence{};

    [[nodiscard]] bool accepted() const;
};

struct MeasurementResult {
    MeasurementStatus status{MeasurementStatus::NumericalFailure};
    int dimension{0};
    double normalized_innovation_squared{0.0};
    SequenceIdentifier state_sequence{};

    [[nodiscard]] bool accepted() const;
};

struct StateSnapshot {
    SequenceIdentifier state_sequence{};
    SourceTimestamp source_timestamp{};
    NavigationFrame navigation_frame{NavigationFrame::LocalNorthEastDown};
    BodyFrame body_frame{BodyFrame::PhysicalImuBody};
    std::array<double, 3> position_n_m{};
    std::array<double, 3> velocity_n_mps{};
    std::array<double, 4> q_n_b_wxyz{};
    std::array<double, 3> accel_bias_b_mps2{};
    std::array<double, 3> gyro_bias_b_radps{};
};

struct CovarianceSnapshot {
    SequenceIdentifier state_sequence{};
    SourceTimestamp source_timestamp{};
    // Row-major covariance in S2 order [position_n_m, velocity_n_mps,
    // attitude_error_rad, accel_bias_b_mps2, gyro_bias_b_radps].
    Covariance15 covariance{};
};

class NavigationCore {
public:
    explicit NavigationCore(const InitialState& initial_state);
    ~NavigationCore();

    NavigationCore(NavigationCore&&) noexcept;
    NavigationCore& operator=(NavigationCore&&) noexcept;
    NavigationCore(const NavigationCore&) = delete;
    NavigationCore& operator=(const NavigationCore&) = delete;

    PropagationResult propagate(const PropagationInput& input);
    MeasurementResult update(const MeasurementInput& input);

    [[nodiscard]] StateSnapshot stateSnapshot() const;
    [[nodiscard]] CovarianceSnapshot covarianceSnapshot() const;
    [[nodiscard]] std::size_t consumedEvidenceCount() const;

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

const char* toString(PropagationStatus status);
const char* toString(MeasurementStatus status);

}  // namespace sih26168::navigation
