#include "sih26168/alignment/mount_slip_detector.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>

namespace sih26168::alignment {
namespace {

bool finiteQuaternion(const std::array<double, 4>& quaternion) noexcept {
    return std::all_of(quaternion.begin(), quaternion.end(), [](double value) {
        return std::isfinite(value);
    });
}

bool validQuaternion(const std::array<double, 4>& quaternion) noexcept {
    if (!finiteQuaternion(quaternion) || quaternion[0] < 0.0) return false;
    double norm_squared = 0.0;
    for (const double component : quaternion) norm_squared += component * component;
    const double norm = std::sqrt(norm_squared);
    return std::isfinite(norm)
        && std::abs(norm - 1.0) <= kAlignmentQuaternionNormTolerance;
}

double geodesicChangeRad(const std::array<double, 4>& baseline,
                         const std::array<double, 4>& observation) noexcept {
    double dot = 0.0;
    for (std::size_t index = 0; index < baseline.size(); ++index) {
        dot += baseline[index] * observation[index];
    }
    return 2.0 * std::acos(std::clamp(std::abs(dot), 0.0, 1.0));
}

bool thresholdReached(double angular_change_rad) noexcept {
    constexpr double kComparisonTolerance =
        64.0 * std::numeric_limits<double>::epsilon();
    return angular_change_rad + kComparisonTolerance
        >= kFrozenSlipRotationThresholdRad;
}

}  // namespace

MountSlipDetector::MountSlipDetector(AlignmentEstimatePublisher& publisher,
                                     MountSlipDetectorConfig config)
    : publisher_(publisher), config_(std::move(config)) {}

bool MountSlipDetector::arm() {
    const auto& latest = publisher_.latest();
    if (config_.config_id.empty() || !latest.has_value()
        || !dependentAidsEligible(*latest) || !publisher_.dependentAidsEligible()) {
        publisher_.failClosed();
        return false;
    }
    if (slip_latched_ && !hasNewRecoveryEvidence(*latest)) {
        publisher_.failClosed();
        return false;
    }

    baseline_ = *latest;
    last_observation_sequence_.reset();
    last_observation_epoch_ns_.reset();
    consumed_evidence_ids_.clear();
    consumed_evidence_ids_.insert(
        baseline_->evidence_ids.begin(), baseline_->evidence_ids.end());
    slip_latched_ = false;
    return true;
}

MountSlipDecision MountSlipDetector::observe(
    const MountOrientationObservation& observation) {
    if (config_.config_id.empty()) return fail(MountSlipOutcome::InvalidConfiguration);
    if (!baseline_.has_value()) return fail(MountSlipOutcome::NotArmed);
    if (slip_latched_) {
        publisher_.failClosed();
        return {MountSlipOutcome::AlreadyLatched, std::nullopt,
                AlignmentEstimateError::None};
    }
    if (!currentBaselineUnchanged()) return fail(MountSlipOutcome::BaselineChanged);
    if (!validQuaternion(observation.q_v_b_wxyz)
        || observation.epoch_ns < 0 || observation.evidence_id.empty()
        || observation.quality_evidence_id.empty()
        || observation.evidence_id == observation.quality_evidence_id) {
        return fail(MountSlipOutcome::InvalidInput);
    }
    if (!observation.quality_eligible) return fail(MountSlipOutcome::QualityIneligible);
    if (last_observation_sequence_.has_value()
        && observation.sequence <= *last_observation_sequence_) {
        return fail(MountSlipOutcome::SequenceNotIncreasing);
    }
    const std::int64_t previous_epoch = last_observation_epoch_ns_.value_or(
        baseline_->epoch_ns);
    if (observation.epoch_ns < previous_epoch) {
        return fail(MountSlipOutcome::EpochRegressed);
    }
    if (observation.epoch_ns - previous_epoch > kFrozenMaximumSlipDetectionGapNs) {
        return fail(MountSlipOutcome::MonitoringGap);
    }
    if (consumed_evidence_ids_.contains(observation.evidence_id)
        || consumed_evidence_ids_.contains(observation.quality_evidence_id)) {
        return fail(MountSlipOutcome::InvalidInput);
    }

    const double angular_change = geodesicChangeRad(
        baseline_->q_v_b_wxyz, observation.q_v_b_wxyz);
    last_observation_sequence_ = observation.sequence;
    last_observation_epoch_ns_ = observation.epoch_ns;
    consumed_evidence_ids_.insert(observation.evidence_id);
    consumed_evidence_ids_.insert(observation.quality_evidence_id);
    if (!thresholdReached(angular_change)) {
        return {MountSlipOutcome::NoSlip, angular_change,
                AlignmentEstimateError::None};
    }

    if (baseline_->sequence == std::numeric_limits<std::uint64_t>::max()) {
        return fail(MountSlipOutcome::PublicationRejected);
    }
    auto slip = *baseline_;
    slip.sequence = baseline_->sequence + 1;
    slip.epoch_ns = observation.epoch_ns;
    slip.status = contracts::AlignmentStatusV1::SLIP_SUSPECTED;
    slip.slip_probability = std::nullopt;
    slip.method_id += "|";
    slip.method_id += kMountSlipDetectorMethodId;
    slip.config_id = baseline_->config_id + "|" + config_.config_id;
    slip.evidence_ids.push_back(observation.evidence_id);
    slip.evidence_ids.push_back(observation.quality_evidence_id);
    const auto publication = publisher_.publish(slip);
    if (!publication.accepted) {
        publisher_.failClosed();
        return {MountSlipOutcome::PublicationRejected, angular_change,
                publication.error};
    }

    slip_latched_ = true;
    return {MountSlipOutcome::SlipSuspected, angular_change,
            AlignmentEstimateError::None};
}

bool MountSlipDetector::armed() const noexcept {
    return baseline_.has_value();
}

bool MountSlipDetector::slipLatched() const noexcept {
    return slip_latched_;
}

MountSlipDecision MountSlipDetector::fail(MountSlipOutcome outcome) noexcept {
    publisher_.failClosed();
    if (!slip_latched_) {
        baseline_.reset();
        last_observation_sequence_.reset();
        last_observation_epoch_ns_.reset();
        consumed_evidence_ids_.clear();
    }
    return {outcome, std::nullopt, AlignmentEstimateError::None};
}

bool MountSlipDetector::currentBaselineUnchanged() const {
    const auto& latest = publisher_.latest();
    return latest.has_value() && baseline_.has_value()
        && latest->sequence == baseline_->sequence
        && latest->epoch_ns == baseline_->epoch_ns
        && latest->status == contracts::AlignmentStatusV1::VALID
        && latest->evidence_ids == baseline_->evidence_ids
        && publisher_.dependentAidsEligible();
}

bool MountSlipDetector::hasNewRecoveryEvidence(
    const contracts::AlignmentEstimate& candidate) const {
    if (!baseline_.has_value()) return true;
    const std::unordered_set<std::string> baseline_ids(
        baseline_->evidence_ids.begin(), baseline_->evidence_ids.end());
    return std::any_of(candidate.evidence_ids.begin(), candidate.evidence_ids.end(),
                       [&baseline_ids](const std::string& evidence_id) {
                           return !baseline_ids.contains(evidence_id);
                       });
}

const char* toString(MountSlipOutcome outcome) noexcept {
    switch (outcome) {
        case MountSlipOutcome::NoSlip: return "no_slip";
        case MountSlipOutcome::SlipSuspected: return "slip_suspected";
        case MountSlipOutcome::AlreadyLatched: return "already_latched";
        case MountSlipOutcome::NotArmed: return "not_armed";
        case MountSlipOutcome::InvalidConfiguration: return "invalid_configuration";
        case MountSlipOutcome::InvalidInput: return "invalid_input";
        case MountSlipOutcome::QualityIneligible: return "quality_ineligible";
        case MountSlipOutcome::SequenceNotIncreasing: return "sequence_not_increasing";
        case MountSlipOutcome::EpochRegressed: return "epoch_regressed";
        case MountSlipOutcome::MonitoringGap: return "monitoring_gap";
        case MountSlipOutcome::BaselineChanged: return "baseline_changed";
        case MountSlipOutcome::PublicationRejected: return "publication_rejected";
    }
    return "unknown";
}

}  // namespace sih26168::alignment
