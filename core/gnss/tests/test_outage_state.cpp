#include "sih26168/gnss/outage_state.hpp"

#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

namespace gnss = sih26168::gnss;
namespace contracts = sih26168::contracts;

namespace {

using Availability = contracts::HealthIntegrityStateV1;
using Mode = contracts::NavigationModeV1;
using Error = gnss::OutageError;
using Cause = gnss::OutageTransitionCause;

int failures = 0;
int total = 0;

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

void run(const char* name, const std::function<void()>& test) {
    ++total;
    try {
        test();
        std::cout << "PASS " << name << '\n';
    } catch (const std::exception& error) {
        ++failures;
        std::cerr << "FAIL " << name << ": " << error.what() << '\n';
    }
}

gnss::OutagePolicy policy() {
    return {"session-1", "boot-1", "elapsed-realtime", 100, 300};
}

gnss::OutageContext at(std::int64_t epoch_ns) {
    return {"session-1", "boot-1", "elapsed-realtime", epoch_ns};
}

void anchor(gnss::OutageStateTracker& tracker, std::int64_t epoch_ns = 1'000) {
    const auto result = tracker.acceptedAid(at(epoch_ns), "anchor", true,
                                            Availability::HEALTHY);
    require(result.applied() && result.state_changed
                && result.cause == Cause::AcceptedAid,
            "accepted initial anchor did not enter GNSS_AIDED");
}

void blackout(gnss::OutageStateTracker& tracker, std::int64_t anchor_ns = 1'000) {
    anchor(tracker, anchor_ns);
    const auto result = tracker.advance(at(anchor_ns + 300));
    require(result.applied() && result.state_changed
                && result.cause == Cause::TimedOutage,
            "timeout did not enter blackout");
}

void expect(const gnss::OutageResult& result, Error error) {
    require(result.error == error, "unexpected outage error");
    require(result.applied() == (error == Error::None), "wrong applied flag");
}

}  // namespace

int main() {
    run("initializing_never_pretends_to_dead_reckon", [] {
        gnss::OutageStateTracker tracker(policy());
        require(tracker.snapshot().mode == Mode::INITIALIZING
                    && tracker.snapshot().availability == Availability::UNAVAILABLE,
                "initial state is not explicit");
        const auto tick = tracker.advance(at(5'000));
        require(tick.applied() && !tick.state_changed, "tick invented an anchor");
        expect(tracker.declareOutage(at(5'001),
                                     {gnss::OutageKind::Natural, "no-signal", ""}),
               Error::InvalidTransition);
        expect(tracker.candidateReturned(at(5'001),
                                          {gnss::Reason::Eligible, true, 0, "candidate"}),
               Error::InvalidTransition);
        require(!tracker.snapshot().outage_start_ns,
                "outage interval opened before scientific initialization");
    });

    run("invalid_policy_and_clock_domain_fail_closed", [] {
        auto malformed = policy();
        malformed.degrade_after_ns = malformed.unavailable_after_ns;
        gnss::OutageStateTracker bad_thresholds(malformed);
        expect(bad_thresholds.acceptedAid(at(1'000), "anchor", true,
                                          Availability::HEALTHY), Error::InvalidPolicy);
        malformed = policy();
        malformed.boot_id.clear();
        gnss::OutageStateTracker bad_identity(malformed);
        expect(bad_identity.advance(at(1'000)), Error::InvalidPolicy);

        gnss::OutageStateTracker tracker(policy());
        auto wrong = at(1'000);
        wrong.boot_id = "other-boot";
        expect(tracker.acceptedAid(wrong, "anchor", true, Availability::HEALTHY),
               Error::ClockDomainMismatch);
        wrong = at(1'000);
        wrong.clock_id = "wall-clock";
        expect(tracker.acceptedAid(wrong, "anchor", true, Availability::HEALTHY),
               Error::ClockDomainMismatch);
        expect(tracker.acceptedAid(at(-1), "anchor", true, Availability::HEALTHY),
               Error::InvalidEpoch);
        anchor(tracker);
        const auto before = tracker.snapshot().transition_sequence;
        expect(tracker.advance(at(999)), Error::EpochRegressed);
        require(tracker.snapshot().mode == Mode::GNSS_AIDED
                    && tracker.snapshot().transition_sequence == before,
                "regressed epoch altered state");
    });

    run("rejected_event_still_advances_monotonic_clock_high_water", [] {
        gnss::OutageStateTracker tracker(policy());
        anchor(tracker);
        expect(tracker.acceptedAid(at(1'050), "", true, Availability::HEALTHY),
               Error::MissingEvidenceId);
        expect(tracker.advance(at(1'049)), Error::EpochRegressed);
        require(tracker.snapshot().mode == Mode::GNSS_AIDED
                    && tracker.snapshot().last_accepted_aid_ns == 1'000,
                "rejected event moved the accepted-aid baseline");
    });

    run("timeout_edges_and_explicit_hysteresis", [] {
        gnss::OutageStateTracker tracker(policy());
        anchor(tracker);
        require(!tracker.advance(at(1'099)).state_changed,
                "degraded before caller threshold");
        const auto degraded = tracker.advance(at(1'100));
        require(degraded.applied() && degraded.state_changed
                    && degraded.cause == Cause::TimedDegradation
                    && degraded.effective_epoch_ns == 1'100,
                "degradation boundary incorrect");
        require(tracker.snapshot().availability == Availability::DEGRADED
                    && tracker.snapshot().mode == Mode::DEGRADED,
                "availability and navigation mode were conflated");
        require(!tracker.advance(at(1'299)).state_changed,
                "outage before caller threshold");
        const auto unavailable = tracker.advance(at(1'300));
        require(unavailable.applied() && unavailable.state_changed
                    && unavailable.cause == Cause::TimedOutage
                    && unavailable.effective_epoch_ns == 1'300,
                "outage boundary incorrect");
        require(tracker.snapshot().mode == Mode::BLACKOUT_DR
                    && tracker.snapshot().availability == Availability::UNAVAILABLE
                    && tracker.snapshot().outage_start_ns == 1'300
                    && tracker.snapshot().outage_kind == gnss::OutageKind::Natural
                    && tracker.snapshot().transition_sequence == 3,
                "timeout did not publish exact blackout onset");
        require(!tracker.advance(at(9'000)).state_changed,
                "blackout tick invented recovery");
    });

    run("late_tick_uses_exact_threshold_epoch", [] {
        gnss::OutageStateTracker tracker(policy());
        blackout(tracker);
        require(tracker.snapshot().outage_start_ns == 1'300,
                "late tick did not use configured threshold epoch");
        gnss::OutageStateTracker late(policy());
        anchor(late);
        const auto result = late.advance(at(2'000));
        require(result.cause == Cause::TimedOutage
                    && result.effective_epoch_ns == 1'300
                    && late.snapshot().outage_start_ns == 1'300,
                "late observation mislabeled the outage start as its arrival");
    });

    run("late_fix_cannot_skip_blackout_when_tick_was_missed", [] {
        gnss::OutageStateTracker tracker(policy());
        anchor(tracker);
        const auto late = tracker.acceptedAid(at(1'500), "late-fix", true,
                                               Availability::HEALTHY);
        require(!late.applied() && late.error == Error::InvalidTransition
                    && late.state_changed && late.cause == Cause::TimedOutage
                    && tracker.snapshot().mode == Mode::BLACKOUT_DR
                    && tracker.snapshot().outage_start_ns == 1'300
                    && tracker.snapshot().last_accepted_aid_ns == 1'000,
                "late accepted fix silently reset the outage timer");
        expect(tracker.acceptedAid(at(1'501), "late-fix", true,
                                   Availability::HEALTHY),
               Error::InvalidTransition);

        gnss::OutageStateTracker quality(policy());
        anchor(quality);
        const auto late_quality = quality.qualityDegraded(at(1'500));
        require(!late_quality.applied() && late_quality.state_changed
                    && late_quality.cause == Cause::TimedOutage,
                "late quality event hid the timeout");
        gnss::OutageStateTracker declared(policy());
        anchor(declared);
        const auto late_declaration = declared.declareOutage(
            at(1'500), {gnss::OutageKind::SoftwareSimulated, "mask", "mask-1"});
        require(!late_declaration.applied() && late_declaration.state_changed
                    && late_declaration.cause == Cause::TimedOutage
                    && declared.snapshot().outage_kind == gnss::OutageKind::Natural,
                "late declaration overwrote the true outage onset");
    });

    run("accepted_aid_is_evidence_once_and_degraded_recovery_is_explicit", [] {
        gnss::OutageStateTracker tracker(policy());
        expect(tracker.acceptedAid(at(999), "not-core-accepted", false,
                                   Availability::HEALTHY), Error::IneligibleAid);
        expect(tracker.acceptedAid(at(999), "not-healthy", true,
                                   Availability::DEGRADED), Error::IneligibleAid);
        expect(tracker.acceptedAid(at(999), "unknown-integrity", true,
                                   static_cast<Availability>(99)), Error::IneligibleAid);
        require(tracker.snapshot().mode == Mode::INITIALIZING,
                "unattested aid initialized navigation");
        anchor(tracker);
        expect(tracker.acceptedAid(at(1'001), "anchor", true,
                                   Availability::HEALTHY), Error::DuplicateEvidenceId);
        expect(tracker.acceptedAid(at(1'000), "same-epoch", true,
                                   Availability::HEALTHY),
               Error::NonIncreasingAidEpoch);
        const auto degraded = tracker.qualityDegraded(at(1'050));
        require(degraded.applied() && degraded.state_changed
                    && degraded.cause == Cause::QualityDegraded,
                "quality rejection did not enter DEGRADED");
        const auto recovered = tracker.acceptedAid(at(1'060), "core-accepted-2", true,
                                                    Availability::HEALTHY);
        require(recovered.applied() && recovered.state_changed
                    && tracker.snapshot().mode == Mode::GNSS_AIDED,
                "explicit accepted aid did not restore DEGRADED state");
        require(!tracker.advance(at(1'159)).state_changed,
                "accepted aid did not reset the age baseline");
        require(tracker.advance(at(1'160)).cause == Cause::TimedDegradation,
                "reset age baseline had wrong boundary");
    });

    run("declaration_requires_valid_kind_and_mask_provenance", [] {
        gnss::OutageStateTracker tracker(policy());
        anchor(tracker);
        const auto baseline = tracker.snapshot().transition_sequence;
        expect(tracker.declareOutage(at(1'010),
                                     {static_cast<gnss::OutageKind>(9), "outage", ""}),
               Error::InvalidDeclaration);
        expect(tracker.declareOutage(at(1'010),
                                     {gnss::OutageKind::SoftwareSimulated, "mask", ""}),
               Error::InvalidDeclaration);
        expect(tracker.declareOutage(at(1'010),
                                     {gnss::OutageKind::Natural, "outage", "mask-1"}),
               Error::InvalidDeclaration);
        expect(tracker.declareOutage(at(1'010),
                                     {gnss::OutageKind::Natural, "", ""}),
               Error::InvalidDeclaration);
        require(tracker.snapshot().transition_sequence == baseline,
                "malformed declaration changed state");
        const auto result = tracker.declareOutage(
            at(1'010), {gnss::OutageKind::SoftwareSimulated, "frozen-mask", "mask-1"});
        require(result.applied() && result.cause == Cause::DeclaredOutage
                    && tracker.snapshot().mode == Mode::BLACKOUT_DR
                    && tracker.snapshot().outage_start_ns == 1'010
                    && tracker.snapshot().mask_id == "mask-1",
                "controlled declaration did not retain mask identity");
        expect(tracker.acceptedAid(at(1'011), "first-fix", true,
                                   Availability::HEALTHY), Error::InvalidTransition);
    });

    run("precheck_candidate_never_reaids_on_first_fix", [] {
        gnss::OutageStateTracker tracker(policy());
        blackout(tracker);
        const auto onset = tracker.snapshot().outage_start_ns;
        expect(tracker.candidateReturned(
                   at(1'310), {gnss::Reason::StaleFix, false, 310, "stale"}),
               Error::IneligibleCandidate);
        expect(tracker.candidateReturned(
                   at(1'310), {gnss::Reason::InvalidPolicy, true, 0, "forged"}),
               Error::IneligibleCandidate);
        expect(tracker.candidateReturned(
                   at(1'310), {gnss::Reason::Eligible, true, 0, ""}),
               Error::IneligibleCandidate);
        const auto candidate = tracker.candidateReturned(
            at(1'310), {gnss::Reason::Eligible, true, 0, "return-1"});
        require(candidate.applied() && candidate.cause == Cause::CandidateReturn
                    && tracker.snapshot().mode == Mode::REACQUIRING
                    && tracker.snapshot().availability == Availability::CANDIDATE_RETURN
                    && tracker.snapshot().outage_start_ns == onset,
                "returning fix did not remain a screening candidate");
        expect(tracker.acceptedAid(at(1'311), "return-1", true,
                                   Availability::HEALTHY), Error::InvalidTransition);
        expect(tracker.candidateRejected(at(1'312), "other"), Error::CandidateMismatch);
        const auto rejected = tracker.candidateRejected(at(1'312), "return-1");
        require(rejected.applied() && rejected.cause == Cause::CandidateRejected
                    && tracker.snapshot().mode == Mode::BLACKOUT_DR
                    && tracker.snapshot().outage_start_ns == onset,
                "rejected candidate did not resume the same outage");
        expect(tracker.candidateReturned(
                   at(1'313), {gnss::Reason::Eligible, true, 0, "return-1"}),
               Error::DuplicateEvidenceId);
    });

    run("actual_replay_precheck_decision_is_screening_only", [] {
        gnss::OutageStateTracker tracker(policy());
        blackout(tracker);
        gnss::Policy precheck_policy{"session-1", "boot-1", "elapsed-realtime",
                                     gnss::SourceKind::Replay, "gps", 100};
        gnss::FixPrecheck precheck(precheck_policy);
        gnss::LocationFix fix;
        fix.evidence_id = "replay-fix";
        fix.session_id = "session-1";
        fix.boot_id = "boot-1";
        fix.clock_id = "elapsed-realtime";
        fix.source_kind = gnss::SourceKind::Replay;
        fix.provider = "gps";
        fix.sequence = 1;
        fix.source_timestamp_ns = 1'310;
        fix.arrival_elapsed_realtime_ns = 1'311;
        fix.lat_deg = 12.5;
        fix.lon_deg = 77.5;
        fix.hacc_m = 3.0;
        const auto decision = precheck.present(fix, 1'312);
        require(decision.eligible && decision.reason == gnss::Reason::Eligible,
                "replay fix did not pass the real WP-07.1 precheck");
        require(tracker.candidateReturned(at(1'312), decision).applied()
                    && tracker.snapshot().mode == Mode::REACQUIRING,
                "precheck candidate was granted aid instead of screening");
        require(!precheck.present(fix, 1'312).eligible,
                "duplicate replay evidence was accepted by the precheck");
    });

    run("core_fault_is_terminal_and_never_holds_valid_navigation", [] {
        gnss::OutageStateTracker tracker(policy());
        blackout(tracker);
        const auto fault = tracker.coreFault(at(1'301));
        require(fault.applied() && fault.cause == Cause::CoreFault
                    && tracker.snapshot().mode == Mode::FAULT
                    && tracker.snapshot().availability == Availability::UNAVAILABLE,
                "core fault did not invalidate navigation mode");
        expect(tracker.advance(at(1'302)), Error::TerminalFault);
        expect(tracker.acceptedAid(at(1'302), "fake-recovery", true,
                                   Availability::HEALTHY), Error::TerminalFault);
        expect(tracker.candidateReturned(
                   at(1'302), {gnss::Reason::Eligible, true, 0, "candidate"}),
               Error::TerminalFault);
    });

    run("near_int64_limit_timeout_is_overflow_safe", [] {
        auto configuration = policy();
        configuration.degrade_after_ns = 5;
        configuration.unavailable_after_ns = 10;
        gnss::OutageStateTracker tracker(configuration);
        const auto initial_ns = std::numeric_limits<std::int64_t>::max() - 20;
        anchor(tracker, initial_ns);
        const auto result = tracker.advance(at(initial_ns + 10));
        require(result.applied() && result.cause == Cause::TimedOutage
                    && tracker.snapshot().outage_start_ns == initial_ns + 10,
                "near-limit age or onset overflowed");
    });

    std::cout << "RESULT " << (total - failures) << '/' << total << " tests passed\n";
    return failures == 0 ? 0 : 1;
}
