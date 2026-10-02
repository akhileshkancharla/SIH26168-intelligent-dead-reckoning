#include "sih26168/alignment/alignment_estimate.hpp"

#include <Eigen/Core>
#include <Eigen/Eigenvalues>

#include <algorithm>
#include <cmath>
#include <limits>
#include <unordered_set>

namespace sih26168::alignment {
namespace {

bool finite(double value) noexcept {
    return std::isfinite(value);
}

template <std::size_t Size>
bool finiteArray(const std::array<double, Size>& values) noexcept {
    return std::all_of(values.begin(), values.end(), finite);
}

bool knownStatus(contracts::AlignmentStatusV1 status) noexcept {
    switch (status) {
        case contracts::AlignmentStatusV1::UNINITIALIZED:
        case contracts::AlignmentStatusV1::VALID:
        case contracts::AlignmentStatusV1::UNCERTAIN:
        case contracts::AlignmentStatusV1::SLIP_SUSPECTED:
            return true;
    }
    return false;
}

bool covarianceSymmetric(const Eigen::Matrix3d& covariance) noexcept {
    constexpr double kScale = 64.0 * std::numeric_limits<double>::epsilon();
    for (Eigen::Index row = 0; row < covariance.rows(); ++row) {
        for (Eigen::Index column = row + 1; column < covariance.cols(); ++column) {
            const double lhs = covariance(row, column);
            const double rhs = covariance(column, row);
            const double tolerance = kScale * std::max({1.0, std::abs(lhs), std::abs(rhs)});
            if (std::abs(lhs - rhs) > tolerance) return false;
        }
    }
    return true;
}

bool covariancePositiveSemidefinite(const Eigen::Matrix3d& covariance) {
    const Eigen::SelfAdjointEigenSolver<Eigen::Matrix3d> decomposition(
        covariance, Eigen::EigenvaluesOnly);
    if (decomposition.info() != Eigen::Success
        || !decomposition.eigenvalues().array().isFinite().all()) {
        return false;
    }
    const double scale = std::max(
        1.0, decomposition.eigenvalues().cwiseAbs().maxCoeff());
    constexpr double kToleranceScale =
        64.0 * std::numeric_limits<double>::epsilon();
    return decomposition.eigenvalues().minCoeff()
        >= -kToleranceScale * scale;
}

bool containsNewEvidence(const std::unordered_set<std::string>& previous_ids,
                         const contracts::AlignmentEstimate& candidate) {
    return std::any_of(candidate.evidence_ids.begin(), candidate.evidence_ids.end(),
                       [&previous_ids](const std::string& evidence_id) {
                           return !previous_ids.contains(evidence_id);
                       });
}

}  // namespace

AlignmentEstimateValidation validateAlignmentEstimate(
    const contracts::AlignmentEstimate& estimate) {
    if (estimate.epoch_ns < 0) {
        return {AlignmentEstimateError::NegativeEpoch};
    }
    if (!finiteArray(estimate.q_v_b_wxyz)) {
        return {AlignmentEstimateError::NonFiniteQuaternion};
    }
    double norm_squared = 0.0;
    for (const double component : estimate.q_v_b_wxyz) {
        norm_squared += component * component;
    }
    const double norm = std::sqrt(norm_squared);
    if (!finite(norm)
        || std::abs(norm - 1.0) > kAlignmentQuaternionNormTolerance) {
        return {AlignmentEstimateError::NonUnitQuaternion};
    }
    if (estimate.q_v_b_wxyz[0] < 0.0) {
        return {AlignmentEstimateError::NonCanonicalQuaternion};
    }
    if (!finiteArray(estimate.covariance_3x3)) {
        return {AlignmentEstimateError::NonFiniteCovariance};
    }

    Eigen::Matrix3d covariance;
    for (Eigen::Index row = 0; row < covariance.rows(); ++row) {
        for (Eigen::Index column = 0; column < covariance.cols(); ++column) {
            covariance(row, column) = estimate.covariance_3x3[
                static_cast<std::size_t>(row * covariance.cols() + column)];
        }
    }
    if (!covarianceSymmetric(covariance)) {
        return {AlignmentEstimateError::NonSymmetricCovariance};
    }
    if (!covariancePositiveSemidefinite(covariance)) {
        return {AlignmentEstimateError::NonPositiveSemidefiniteCovariance};
    }
    if (!knownStatus(estimate.status)) {
        return {AlignmentEstimateError::UnknownStatus};
    }
    if (!finite(estimate.observability)
        || estimate.observability < 0.0 || estimate.observability > 1.0) {
        return {AlignmentEstimateError::InvalidObservability};
    }
    if (estimate.slip_probability.has_value()
        && (!finite(*estimate.slip_probability)
            || *estimate.slip_probability < 0.0
            || *estimate.slip_probability > 1.0)) {
        return {AlignmentEstimateError::InvalidSlipProbability};
    }
    if (estimate.method_id.empty()) {
        return {AlignmentEstimateError::MissingMethodId};
    }
    std::unordered_set<std::string> evidence_ids;
    for (const auto& evidence_id : estimate.evidence_ids) {
        if (evidence_id.empty()) {
            return {AlignmentEstimateError::MissingEvidenceId};
        }
        if (!evidence_ids.insert(evidence_id).second) {
            return {AlignmentEstimateError::DuplicateEvidenceId};
        }
    }
    if (evidence_ids.empty()) {
        return {AlignmentEstimateError::MissingEvidenceId};
    }
    if (estimate.config_id.empty()) {
        return {AlignmentEstimateError::MissingConfigId};
    }
    return {};
}

bool dependentAidsEligible(const contracts::AlignmentEstimate& estimate) {
    return estimate.status == contracts::AlignmentStatusV1::VALID
        && validateAlignmentEstimate(estimate).valid();
}

const char* toString(AlignmentEstimateError error) noexcept {
    switch (error) {
        case AlignmentEstimateError::None: return "none";
        case AlignmentEstimateError::NegativeEpoch: return "negative_epoch";
        case AlignmentEstimateError::NonFiniteQuaternion: return "non_finite_quaternion";
        case AlignmentEstimateError::NonUnitQuaternion: return "non_unit_quaternion";
        case AlignmentEstimateError::NonCanonicalQuaternion: return "non_canonical_quaternion";
        case AlignmentEstimateError::NonFiniteCovariance: return "non_finite_covariance";
        case AlignmentEstimateError::NonSymmetricCovariance: return "non_symmetric_covariance";
        case AlignmentEstimateError::NonPositiveSemidefiniteCovariance:
            return "non_positive_semidefinite_covariance";
        case AlignmentEstimateError::UnknownStatus: return "unknown_status";
        case AlignmentEstimateError::InvalidObservability: return "invalid_observability";
        case AlignmentEstimateError::InvalidSlipProbability: return "invalid_slip_probability";
        case AlignmentEstimateError::MissingMethodId: return "missing_method_id";
        case AlignmentEstimateError::MissingEvidenceId: return "missing_evidence_id";
        case AlignmentEstimateError::DuplicateEvidenceId: return "duplicate_evidence_id";
        case AlignmentEstimateError::MissingConfigId: return "missing_config_id";
        case AlignmentEstimateError::SequenceNotIncreasing: return "sequence_not_increasing";
        case AlignmentEstimateError::EpochRegressed: return "epoch_regressed";
        case AlignmentEstimateError::MissingRecoveryEvidence: return "missing_recovery_evidence";
    }
    return "unknown";
}

AlignmentPublicationResult AlignmentEstimatePublisher::publish(
    const contracts::AlignmentEstimate& estimate) {
    const auto validation = validateAlignmentEstimate(estimate);
    if (!validation.valid()) {
        publication_healthy_ = false;
        return {false, validation.error};
    }
    if (latest_.has_value() && estimate.sequence <= latest_->sequence) {
        publication_healthy_ = false;
        return {false, AlignmentEstimateError::SequenceNotIncreasing};
    }
    if (latest_.has_value() && estimate.epoch_ns < latest_->epoch_ns) {
        publication_healthy_ = false;
        return {false, AlignmentEstimateError::EpochRegressed};
    }
    if (slip_recovery_required_
        && estimate.status == contracts::AlignmentStatusV1::VALID
        && !containsNewEvidence(slip_recovery_baseline_evidence_ids_, estimate)) {
        publication_healthy_ = false;
        return {false, AlignmentEstimateError::MissingRecoveryEvidence};
    }

    latest_ = estimate;
    if (estimate.status == contracts::AlignmentStatusV1::SLIP_SUSPECTED
        && !slip_recovery_required_) {
        slip_recovery_baseline_evidence_ids_.clear();
        slip_recovery_required_ = true;
    }
    if (slip_recovery_required_
        && estimate.status != contracts::AlignmentStatusV1::VALID) {
        slip_recovery_baseline_evidence_ids_.insert(
            estimate.evidence_ids.begin(), estimate.evidence_ids.end());
    } else if (slip_recovery_required_) {
        slip_recovery_baseline_evidence_ids_.clear();
        slip_recovery_required_ = false;
    }
    publication_healthy_ = true;
    return {true, AlignmentEstimateError::None};
}

const std::optional<contracts::AlignmentEstimate>&
AlignmentEstimatePublisher::latest() const noexcept {
    return latest_;
}

bool AlignmentEstimatePublisher::dependentAidsEligible() const {
    return publication_healthy_ && latest_.has_value()
        && alignment::dependentAidsEligible(*latest_);
}

}  // namespace sih26168::alignment
