#include "sih26168/gnss/reacquisition_gate.hpp"

#include <algorithm>
#include <cmath>
#include <utility>

namespace sih26168::gnss {
namespace {

using Mode = contracts::NavigationModeV1;

bool carriesSource(const navigation::MeasurementInput& measurement,
                   const std::string& source_id) {
    return std::any_of(measurement.provider_evidence_ids.begin(),
                       measurement.provider_evidence_ids.end(),
                       [&](const auto& id) { return id.value == source_id; });
}

}  // namespace

ReacquisitionGate::ReacquisitionGate(ReacquisitionPolicy policy,
                                     OutageStateTracker& outage,
                                     FixRejectionScreen& rejection,
                                     navigation::NavigationCore& core)
    : policy_(std::move(policy)), outage_(outage), rejection_(rejection), core_(core) {
    policy_valid_ = !policy_.session_id.empty() && !policy_.boot_id.empty()
        && !policy_.clock_id.empty() && policy_.required_consistent_fixes >= 2
        && policy_.minimum_dwell_ns > 0
        && policy_.maximum_dwell_ns >= policy_.minimum_dwell_ns
        && policy_.maximum_interfix_gap_ns > 0;
}

void ReacquisitionGate::clearStreak() noexcept {
    first_evidence_id_.clear();
    first_epoch_ns_.reset();
    last_epoch_ns_.reset();
    dwell_count_ = 0;
}

void ReacquisitionGate::rejectActive(const OutageContext& context) {
    if (outage_.snapshot().mode == Mode::REACQUIRING
        && !outage_.snapshot().candidate_evidence_id.empty()) {
        (void)outage_.candidateRejected(context,
                                        outage_.snapshot().candidate_evidence_id);
    }
    clearStreak();
}

ReacquisitionResult ReacquisitionGate::present(
    const OutageContext& context, const LocationFix& fix,
    const navigation::MeasurementInput& measurement,
    contracts::HealthIntegrityStateV1 screened_availability) {
    ReacquisitionResult result;
    result.evidence_id = fix.evidence_id;
    // Even a C-09 rejection presents its canonical ID to C-07. A later caller
    // or reconstructed gate must not be able to upgrade the same evidence.
    const auto consume_canonical = [&] { (void)core_.screen(measurement); };
    if (!policy_valid_) {
        consume_canonical();
        return result;
    }
    if (context.session_id != policy_.session_id || context.boot_id != policy_.boot_id
        || context.clock_id != policy_.clock_id) {
        consume_canonical();
        result.reason = ReacquisitionReason::ClockDomainMismatch;
        return result;
    }
    const auto mode = outage_.snapshot().mode;
    if (mode != Mode::BLACKOUT_DR && mode != Mode::REACQUIRING) {
        consume_canonical();
        result.reason = ReacquisitionReason::InvalidMode;
        return result;
    }
    // WP-07.3 owns source identity consumption, provenance and physical
    // plausibility. Present it before local timing/lineage checks so a
    // rejected or malformed first presentation cannot be retried with edits.
    const auto upstream = rejection_.present(fix, context.epoch_ns);
    result.upstream_reason = upstream.reason;
    if (context.epoch_ns < 0 || (last_epoch_ns_ && context.epoch_ns <= *last_epoch_ns_)) {
        consume_canonical();
        if (upstream.forwardToCore()) {
            (void)rejection_.withholdForRecoveryDwell(fix.evidence_id);
        }
        result.reason = ReacquisitionReason::InvalidEpoch;
        // The tracker's monotonic clock cannot accept a regressed epoch. End
        // the active dwell at the last valid epoch instead of leaving it live.
        if (last_epoch_ns_) {
            auto safe_context = context;
            safe_context.epoch_ns = *last_epoch_ns_;
            rejectActive(safe_context);
        }
        return result;
    }
    if (!upstream.forwardToCore() || !upstream.precheck_decision) {
        consume_canonical();
        result.reason = ReacquisitionReason::UpstreamRejected;
        rejectActive(context);
        return result;
    }
    if (fix.evidence_id.empty() || measurement.measurement_id.value.empty()
        || measurement.state_epoch_ns.nanoseconds != context.epoch_ns
        || !carriesSource(measurement, fix.evidence_id)) {
        consume_canonical();
        if (upstream.forwardToCore()) {
            (void)rejection_.withholdForRecoveryDwell(fix.evidence_id);
        }
        result.reason = ReacquisitionReason::InvalidMeasurementLineage;
        rejectActive(context);
        return result;
    }
    // C-09 must independently attest a healthy candidate. Passing source
    // freshness and C-07 innovation alone does not prove GNSS integrity.
    if (screened_availability != contracts::HealthIntegrityStateV1::HEALTHY) {
        consume_canonical();
        (void)rejection_.withholdForRecoveryDwell(fix.evidence_id);
        result.reason = ReacquisitionReason::QualityRejected;
        rejectActive(context);
        return result;
    }
    if (mode == Mode::BLACKOUT_DR) {
        const auto started = outage_.candidateReturned(context, *upstream.precheck_decision);
        if (!started.applied()) {
            consume_canonical();
            (void)rejection_.withholdForRecoveryDwell(fix.evidence_id);
            result.reason = ReacquisitionReason::TrackerRejected;
            return result;
        }
        clearStreak();
        first_evidence_id_ = fix.evidence_id;
        first_epoch_ns_ = context.epoch_ns;
    } else if (!first_epoch_ns_ || !last_epoch_ns_
               || context.epoch_ns - *last_epoch_ns_ > policy_.maximum_interfix_gap_ns
               || context.epoch_ns - *first_epoch_ns_ > policy_.maximum_dwell_ns) {
        consume_canonical();
        (void)rejection_.withholdForRecoveryDwell(fix.evidence_id);
        result.reason = ReacquisitionReason::InconsistentTiming;
        rejectActive(context);
        return result;
    }

    const auto candidate_count = dwell_count_ < policy_.required_consistent_fixes
        ? dwell_count_ + 1 : dwell_count_;
    const bool completes_dwell = candidate_count >= policy_.required_consistent_fixes
        && context.epoch_ns - *first_epoch_ns_ >= policy_.minimum_dwell_ns;
    if (!completes_dwell) {
        const auto screened = core_.screen(measurement);
        result.screen_status = screened.status;
        if (screened.dimension > 0
            && std::isfinite(screened.normalized_innovation_squared)) {
            result.nis = screened.normalized_innovation_squared;
        }
        if (!screened.passesGate()) {
            (void)rejection_.withholdForRecoveryDwell(fix.evidence_id);
            if (screened.status == navigation::MeasurementStatus::NumericalFailure) {
                result.reason = ReacquisitionReason::CoreScreenFailure;
                (void)outage_.coreFault(context);
                clearStreak();
            } else {
                result.reason = screened.status
                    == navigation::MeasurementStatus::RejectedDuplicateEvidenceIdentifier
                    ? ReacquisitionReason::DuplicateMeasurementId
                    : ReacquisitionReason::InnovationRejected;
                rejectActive(context);
            }
            return result;
        }
        last_epoch_ns_ = context.epoch_ns;
        dwell_count_ = candidate_count;
        result.dwell_count = dwell_count_;
        (void)rejection_.withholdForRecoveryDwell(fix.evidence_id);
        result.reason = ReacquisitionReason::Dwell;
        return result;
    }

    // The final candidate has not been screened. C-07 applies its innovation
    // gate and update atomically while consuming this ID on first presentation.
    const auto before_update = core_.stateSnapshot();
    const auto updated = core_.update(measurement);
    const auto finalized = rejection_.finalize(fix.evidence_id, updated.status);
    result.core_status = updated.status;
    if (updated.dimension > 0 && std::isfinite(updated.normalized_innovation_squared)) {
        result.nis = updated.normalized_innovation_squared;
    }
    if (!updated.accepted() || finalized.reason != RejectionReason::AcceptedByCore) {
        result.reason = updated.status
            == navigation::MeasurementStatus::RejectedDuplicateEvidenceIdentifier
            ? ReacquisitionReason::DuplicateMeasurementId
            : updated.status == navigation::MeasurementStatus::RejectedInnovationGate
                ? ReacquisitionReason::InnovationRejected
                : ReacquisitionReason::CoreUpdateRejected;
        if (updated.status == navigation::MeasurementStatus::NumericalFailure) {
            (void)outage_.coreFault(context);
            clearStreak();
        } else {
            rejectActive(context);
        }
        return result;
    }
    result.scientific_update_accepted = true;
    last_epoch_ns_ = context.epoch_ns;
    dwell_count_ = candidate_count;
    result.dwell_count = dwell_count_;
    const auto after_update = core_.stateSnapshot();
    result.scientific_jump_m = std::hypot(
        after_update.position_n_m[0] - before_update.position_n_m[0],
        after_update.position_n_m[1] - before_update.position_n_m[1],
        after_update.position_n_m[2] - before_update.position_n_m[2]);
    const auto restored = outage_.completeRecovery(context, first_evidence_id_,
                                                    fix.evidence_id);
    clearStreak();
    result.reason = restored.applied() ? ReacquisitionReason::Recovered
                                       : ReacquisitionReason::TrackerRejected;
    if (!restored.applied()) (void)outage_.coreFault(context);
    return result;
}

}  // namespace sih26168::gnss
