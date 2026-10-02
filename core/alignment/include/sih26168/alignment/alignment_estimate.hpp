#pragma once

#include "sih26168/contracts/alignment_estimate.hpp"

#include <optional>
#include <string>
#include <unordered_set>

namespace sih26168::alignment {

inline constexpr double kAlignmentQuaternionNormTolerance = 1.0e-6;

enum class AlignmentEstimateError {
    None,
    NegativeEpoch,
    NonFiniteQuaternion,
    NonUnitQuaternion,
    NonCanonicalQuaternion,
    NonFiniteCovariance,
    NonSymmetricCovariance,
    NonPositiveSemidefiniteCovariance,
    UnknownStatus,
    InvalidObservability,
    InvalidSlipProbability,
    MissingMethodId,
    MissingEvidenceId,
    DuplicateEvidenceId,
    MissingConfigId,
    SequenceNotIncreasing,
    EpochRegressed,
    MissingRecoveryEvidence,
};

struct AlignmentEstimateValidation {
    AlignmentEstimateError error{AlignmentEstimateError::None};

    [[nodiscard]] bool valid() const noexcept {
        return error == AlignmentEstimateError::None;
    }
};

[[nodiscard]] AlignmentEstimateValidation validateAlignmentEstimate(
    const contracts::AlignmentEstimate& estimate);

// This is a safety gate only, not a scientific acceptance decision. No
// threshold is inferred from observability or slip_probability.
[[nodiscard]] bool dependentAidsEligible(
    const contracts::AlignmentEstimate& estimate);

[[nodiscard]] const char* toString(AlignmentEstimateError error) noexcept;

struct AlignmentPublicationResult {
    bool accepted{false};
    AlignmentEstimateError error{AlignmentEstimateError::None};
};

// Owns only the I-06 publication history. It never modifies C-07 navigation
// state. Rejected input does not overwrite the latest accepted posterior and
// immediately makes the dependent-aid gate fail closed.
class AlignmentEstimatePublisher {
public:
    [[nodiscard]] AlignmentPublicationResult publish(
        const contracts::AlignmentEstimate& estimate);

    [[nodiscard]] const std::optional<contracts::AlignmentEstimate>& latest()
        const noexcept;
    [[nodiscard]] bool dependentAidsEligible() const;

private:
    std::optional<contracts::AlignmentEstimate> latest_;
    std::unordered_set<std::string> slip_recovery_baseline_evidence_ids_;
    bool slip_recovery_required_{false};
    bool publication_healthy_{false};
};

}  // namespace sih26168::alignment
