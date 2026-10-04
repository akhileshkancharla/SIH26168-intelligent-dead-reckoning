#include "sih26168/gnss/outage_state.hpp"

#include <utility>

namespace sih26168::gnss {
namespace {

using Availability = contracts::HealthIntegrityStateV1;
using Mode = contracts::NavigationModeV1;

OutageResult rejected(OutageError error) {
    return {error, OutageTransitionCause::None, false, std::nullopt};
}

OutageResult applied(OutageTransitionCause cause, bool changed,
                     std::int64_t effective_epoch_ns) {
    return {OutageError::None, cause, changed, effective_epoch_ns};
}

bool validKind(OutageKind kind) {
    switch (kind) {
        case OutageKind::Natural:
        case OutageKind::Quality:
        case OutageKind::SoftwareSimulated:
            return true;
    }
    return false;
}

bool validDeclaration(const OutageDeclaration& declaration) {
    if (!validKind(declaration.kind) || declaration.reason.empty()) return false;
    return declaration.kind == OutageKind::SoftwareSimulated
        ? !declaration.mask_id.empty() : declaration.mask_id.empty();
}

}  // namespace

OutageStateTracker::OutageStateTracker(OutagePolicy policy)
    : policy_(std::move(policy)) {
    policy_valid_ = !policy_.session_id.empty() && !policy_.boot_id.empty()
        && !policy_.clock_id.empty() && policy_.degrade_after_ns > 0
        && policy_.unavailable_after_ns > policy_.degrade_after_ns;
}

OutageError OutageStateTracker::validate(const OutageContext& context) const {
    if (!policy_valid_) return OutageError::InvalidPolicy;
    if (context.session_id != policy_.session_id || context.boot_id != policy_.boot_id
        || context.clock_id != policy_.clock_id) {
        return OutageError::ClockDomainMismatch;
    }
    if (context.epoch_ns < 0) return OutageError::InvalidEpoch;
    if (last_observed_epoch_ns_ && context.epoch_ns < *last_observed_epoch_ns_) {
        return OutageError::EpochRegressed;
    }
    if (state_.mode == Mode::FAULT) return OutageError::TerminalFault;
    return OutageError::None;
}

bool OutageStateTracker::outageOverdue(std::int64_t epoch_ns) const noexcept {
    return (state_.mode == Mode::GNSS_AIDED || state_.mode == Mode::DEGRADED)
        && state_.last_accepted_aid_ns.has_value()
        && epoch_ns - *state_.last_accepted_aid_ns >= policy_.unavailable_after_ns;
}

void OutageStateTracker::observeEpoch(std::int64_t epoch_ns) noexcept {
    last_observed_epoch_ns_ = epoch_ns;
}

void OutageStateTracker::enterBlackout(std::int64_t start_ns, OutageKind kind,
                                       const std::string& reason,
                                       const std::string& mask_id) {
    state_.availability = Availability::UNAVAILABLE;
    state_.mode = Mode::BLACKOUT_DR;
    state_.outage_start_ns = start_ns;
    state_.outage_kind = kind;
    state_.outage_reason = reason;
    state_.mask_id = mask_id;
    state_.candidate_evidence_id.clear();
    ++state_.transition_sequence;
}

OutageResult OutageStateTracker::acceptedAid(const OutageContext& context,
                                             const std::string& evidence_id,
                                             bool core_update_accepted,
                                             Availability screened_availability) {
    if (const auto error = validate(context); error != OutageError::None) {
        return rejected(error);
    }
    observeEpoch(context.epoch_ns);
    // A late returning fix is a candidate, not an aid. Apply the exact outage
    // boundary first even if the caller missed its periodic advance tick.
    if (outageOverdue(context.epoch_ns)) {
        auto timeout = advance(context);
        timeout.error = OutageError::InvalidTransition;
        return timeout;
    }
    if (state_.mode != Mode::INITIALIZING && state_.mode != Mode::GNSS_AIDED
        && state_.mode != Mode::DEGRADED) {
        return rejected(OutageError::InvalidTransition);
    }
    if (!core_update_accepted || screened_availability != Availability::HEALTHY) {
        return rejected(OutageError::IneligibleAid);
    }
    if (evidence_id.empty()) return rejected(OutageError::MissingEvidenceId);
    if (accepted_aid_ids_.contains(evidence_id) || candidate_ids_.contains(evidence_id)) {
        return rejected(OutageError::DuplicateEvidenceId);
    }
    if (state_.last_accepted_aid_ns
        && context.epoch_ns <= *state_.last_accepted_aid_ns) {
        return rejected(OutageError::NonIncreasingAidEpoch);
    }

    const bool changed = state_.mode != Mode::GNSS_AIDED;
    accepted_aid_ids_.insert(evidence_id);
    state_.last_accepted_aid_ns = context.epoch_ns;
    state_.availability = Availability::HEALTHY;
    state_.mode = Mode::GNSS_AIDED;
    if (changed) ++state_.transition_sequence;
    return applied(OutageTransitionCause::AcceptedAid, changed, context.epoch_ns);
}

OutageResult OutageStateTracker::qualityDegraded(const OutageContext& context) {
    if (const auto error = validate(context); error != OutageError::None) {
        return rejected(error);
    }
    observeEpoch(context.epoch_ns);
    if (outageOverdue(context.epoch_ns)) {
        auto timeout = advance(context);
        timeout.error = OutageError::InvalidTransition;
        return timeout;
    }
    if (state_.mode != Mode::GNSS_AIDED && state_.mode != Mode::DEGRADED) {
        return rejected(OutageError::InvalidTransition);
    }
    const bool changed = state_.mode == Mode::GNSS_AIDED;
    state_.availability = Availability::DEGRADED;
    state_.mode = Mode::DEGRADED;
    if (changed) ++state_.transition_sequence;
    return applied(OutageTransitionCause::QualityDegraded, changed, context.epoch_ns);
}

OutageResult OutageStateTracker::advance(const OutageContext& context) {
    if (const auto error = validate(context); error != OutageError::None) {
        return rejected(error);
    }
    observeEpoch(context.epoch_ns);
    if (state_.mode != Mode::GNSS_AIDED && state_.mode != Mode::DEGRADED) {
        return applied(OutageTransitionCause::None, false, context.epoch_ns);
    }
    // acceptedAid is the only way to establish this timestamp in these modes.
    const auto last_aid_ns = *state_.last_accepted_aid_ns;
    const auto elapsed_ns = context.epoch_ns - last_aid_ns;
    if (elapsed_ns >= policy_.unavailable_after_ns) {
        const auto start_ns = last_aid_ns + policy_.unavailable_after_ns;
        enterBlackout(start_ns, OutageKind::Natural, "accepted_aid_timeout", "");
        return applied(OutageTransitionCause::TimedOutage, true, start_ns);
    }
    if (elapsed_ns >= policy_.degrade_after_ns && state_.mode == Mode::GNSS_AIDED) {
        const auto degraded_ns = last_aid_ns + policy_.degrade_after_ns;
        state_.availability = Availability::DEGRADED;
        state_.mode = Mode::DEGRADED;
        ++state_.transition_sequence;
        return applied(OutageTransitionCause::TimedDegradation, true, degraded_ns);
    }
    return applied(OutageTransitionCause::None, false, context.epoch_ns);
}

OutageResult OutageStateTracker::declareOutage(
    const OutageContext& context, const OutageDeclaration& declaration) {
    if (const auto error = validate(context); error != OutageError::None) {
        return rejected(error);
    }
    observeEpoch(context.epoch_ns);
    if (outageOverdue(context.epoch_ns)) {
        auto timeout = advance(context);
        timeout.error = OutageError::InvalidTransition;
        return timeout;
    }
    if (!validDeclaration(declaration)) return rejected(OutageError::InvalidDeclaration);
    if (state_.mode != Mode::GNSS_AIDED && state_.mode != Mode::DEGRADED) {
        return rejected(OutageError::InvalidTransition);
    }
    enterBlackout(context.epoch_ns, declaration.kind, declaration.reason,
                  declaration.mask_id);
    return applied(OutageTransitionCause::DeclaredOutage, true, context.epoch_ns);
}

OutageResult OutageStateTracker::candidateReturned(const OutageContext& context,
                                                    const Decision& precheck) {
    if (const auto error = validate(context); error != OutageError::None) {
        return rejected(error);
    }
    observeEpoch(context.epoch_ns);
    if (state_.mode != Mode::BLACKOUT_DR) {
        return rejected(OutageError::InvalidTransition);
    }
    if (!precheck.eligible || precheck.reason != Reason::Eligible
        || precheck.age_ns < 0 || precheck.evidence_id.empty()) {
        return rejected(OutageError::IneligibleCandidate);
    }
    if (candidate_ids_.contains(precheck.evidence_id)
        || accepted_aid_ids_.contains(precheck.evidence_id)) {
        return rejected(OutageError::DuplicateEvidenceId);
    }
    candidate_ids_.insert(precheck.evidence_id);
    state_.candidate_evidence_id = precheck.evidence_id;
    state_.availability = Availability::CANDIDATE_RETURN;
    state_.mode = Mode::REACQUIRING;
    ++state_.transition_sequence;
    return applied(OutageTransitionCause::CandidateReturn, true, context.epoch_ns);
}

OutageResult OutageStateTracker::candidateRejected(const OutageContext& context,
                                                    const std::string& evidence_id) {
    if (const auto error = validate(context); error != OutageError::None) {
        return rejected(error);
    }
    observeEpoch(context.epoch_ns);
    if (state_.mode != Mode::REACQUIRING) {
        return rejected(OutageError::InvalidTransition);
    }
    if (evidence_id.empty() || evidence_id != state_.candidate_evidence_id) {
        return rejected(OutageError::CandidateMismatch);
    }
    state_.candidate_evidence_id.clear();
    state_.availability = Availability::UNAVAILABLE;
    state_.mode = Mode::BLACKOUT_DR;
    ++state_.transition_sequence;
    return applied(OutageTransitionCause::CandidateRejected, true, context.epoch_ns);
}

OutageResult OutageStateTracker::coreFault(const OutageContext& context) {
    if (const auto error = validate(context); error != OutageError::None) {
        return rejected(error);
    }
    state_.candidate_evidence_id.clear();
    state_.availability = Availability::UNAVAILABLE;
    state_.mode = Mode::FAULT;
    ++state_.transition_sequence;
    observeEpoch(context.epoch_ns);
    return applied(OutageTransitionCause::CoreFault, true, context.epoch_ns);
}

}  // namespace sih26168::gnss
