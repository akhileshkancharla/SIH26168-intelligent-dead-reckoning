#include "sih26168/gnss/fix_rejection.hpp"

#include <cstdlib>
#include <iostream>
#include <limits>
#include <string>
#include <utility>

using namespace sih26168::gnss;
using sih26168::navigation::MeasurementStatus;

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

RejectionPolicy policy() {
    return {Policy{"session-1", "boot-1", "elapsed-1", SourceKind::Live,
                   "gps", 200'000'000}, 40.0, 25.0};
}

LocationFix fix(std::string id, std::uint64_t sequence,
                std::int64_t source_ns, double lat_deg = 12.5,
                double lon_deg = 77.5) {
    LocationFix result;
    result.evidence_id = std::move(id);
    result.session_id = "session-1";
    result.boot_id = "boot-1";
    result.clock_id = "elapsed-1";
    result.provider = "gps";
    result.sequence = sequence;
    result.source_timestamp_ns = source_ns;
    result.arrival_elapsed_realtime_ns = source_ns + 10'000'000;
    result.lat_deg = lat_deg;
    result.lon_deg = lon_deg;
    result.hacc_m = 3.0;
    return result;
}

}  // namespace

int main() {
    {
        FixRejectionScreen screen(policy());
        require(screen.present(fix("first", 1, 1'000'000'000), 1'020'000'000)
                    .forwardToCore(), "first source fix should be forwarded, not accepted");
        require(screen.present(fix("busy", 2, 1'100'000'000), 1'120'000'000).reason
                    == RejectionReason::PendingCoreDecision,
                "second fix entered before the first core decision");
        require(screen.consumedCount() == 2,
                "busy fix did not consume its source identity");
        const auto duplicate_while_pending =
            screen.present(fix("busy", 2, 1'100'000'000), 1'120'000'000);
        require(duplicate_while_pending.reason == RejectionReason::PrecheckRejected
                    && duplicate_while_pending.precheck_reason == Reason::DuplicateEvidenceId,
                "duplicate busy evidence was hidden by the pending-core gate");
        auto malformed_while_pending = fix("malformed", 3, 1'130'000'000);
        malformed_while_pending.provider = "other";
        const auto malformed_result = screen.present(malformed_while_pending, 1'150'000'000);
        require(malformed_result.reason == RejectionReason::PrecheckRejected
                    && malformed_result.precheck_reason == Reason::ProvenanceMismatch
                    && screen.consumedCount() == 3,
                "malformed busy evidence was not consumed and diagnosed");
        const auto malformed_repeat = screen.present(malformed_while_pending, 1'150'000'000);
        require(malformed_repeat.reason == RejectionReason::PrecheckRejected
                    && malformed_repeat.precheck_reason == Reason::DuplicateEvidenceId,
                "malformed busy evidence was allowed a second presentation");
        const auto empty_while_pending =
            screen.present(fix("", 3, 1'130'000'000), 1'150'000'000);
        require(empty_while_pending.reason == RejectionReason::PrecheckRejected
                    && empty_while_pending.precheck_reason == Reason::EmptyEvidenceId
                    && screen.consumedCount() == 3,
                "empty busy identity was not rejected without ledger mutation");
        require(screen.finalize("wrong", MeasurementStatus::Accepted).reason
                    == RejectionReason::EvidenceMismatch,
                "mismatched core evidence finalized a candidate");
        require(screen.finalize("first", MeasurementStatus::Accepted).reason
                    == RejectionReason::AcceptedByCore,
                "valid first core update was not recorded");
        const auto busy_repeated = screen.present(fix("busy", 2, 1'100'000'000),
                                                   1'120'000'000);
        require(busy_repeated.reason == RejectionReason::PrecheckRejected
                    && busy_repeated.precheck_reason == Reason::DuplicateEvidenceId
                    && !busy_repeated.forwardToCore(),
                "busy source evidence was allowed a second presentation");
        const auto repeated = screen.present(fix("first", 1, 1'000'000'000),
                                             1'020'000'000);
        require(repeated.reason == RejectionReason::PrecheckRejected
                    && repeated.precheck_reason == Reason::DuplicateEvidenceId,
                "accepted source evidence was allowed a second presentation");

        const auto stale = screen.present(fix("stale", 2, 1'100'000'000), 1'300'000'001);
        require(stale.reason == RejectionReason::PrecheckRejected
                    && stale.precheck_reason == Reason::StaleFix,
                "stale fix was not rejected before core");
        const auto duplicate = screen.present(fix("stale", 2, 1'100'000'000), 1'120'000'000);
        require(duplicate.reason == RejectionReason::PrecheckRejected
                    && duplicate.precheck_reason == Reason::DuplicateEvidenceId,
                "rejected source evidence was allowed a second presentation");

        const auto jump = screen.present(fix("jump", 3, 2'000'000'000, 13.5, 77.5),
                                         2'020'000'000);
        require(jump.reason == RejectionReason::ImplausibleDisplacement
                    && jump.displacement_m && jump.displacement_bound_m
                    && *jump.displacement_m > *jump.displacement_bound_m,
                "physically implausible biased jump was forwarded to core");
        require(screen.finalize("jump", MeasurementStatus::Accepted).reason
                    == RejectionReason::NoPendingFix,
                "screened jump was improperly finalized as accepted");

        auto uncertain = fix("uncertain", 4, 2'500'000'000);
        uncertain.hacc_m = 1'000.0;
        require(screen.present(uncertain, 2'520'000'000).reason
                    == RejectionReason::UnusableAccuracy,
                "unbounded reported uncertainty was forwarded to core");

        const auto nearby = screen.present(fix("nearby", 5, 3'000'000'000, 12.5001, 77.5),
                                           3'020'000'000);
        require(nearby.forwardToCore(), "legitimate fix was poisoned by rejected jump");
        require(screen.finalize("nearby", MeasurementStatus::RejectedInnovationGate).reason
                    == RejectionReason::CoreInnovationRejected,
                "core NIS rejection was not preserved as a distinct reason");
        const auto later = screen.present(fix("later", 6, 4'000'000'000, 12.5001, 77.5),
                                          4'020'000'000);
        require(later.forwardToCore(), "core-rejected fix poisoned the physical baseline");
        require(screen.finalize("later", MeasurementStatus::Accepted).reason
                    == RejectionReason::AcceptedByCore,
                "consistent later core update was not recorded");
    }
    {
        FixRejectionScreen screen(policy());
        require(screen.present(fix("candidate", 1, 1'000'000'000), 1'020'000'000)
                    .forwardToCore(), "candidate failed precheck");
        require(screen.finalize("candidate", MeasurementStatus::RejectedPrecheck).reason
                    == RejectionReason::CoreRejected,
                "non-innovation core rejection was mislabeled as bias");
        require(screen.present(fix("next", 2, 2'000'000'000, 14.0, 77.5),
                               2'020'000'000).forwardToCore(),
                "unaccepted first candidate incorrectly set a physical baseline");
    }
    {
        auto invalid = policy();
        invalid.max_ground_speed_mps = std::numeric_limits<double>::quiet_NaN();
        FixRejectionScreen screen(invalid);
        require(screen.present(fix("invalid-policy", 1, 1'000'000'000),
                               1'020'000'000).reason == RejectionReason::InvalidPolicy,
                "non-finite policy was accepted");
        require(screen.consumedCount() == 1,
                "invalid policy did not preserve evidence-once accounting");
    }
    {
        auto invalid = policy();
        invalid.max_ground_speed_mps = 0.0;
        FixRejectionScreen screen(invalid);
        require(screen.present(fix("no-speed-bound", 1, 1'000'000'000),
                               1'020'000'000).reason == RejectionReason::InvalidPolicy,
                "missing operational speed bound was accepted");
    }
    {
        auto invalid = policy();
        invalid.max_horizontal_accuracy_m = 0.0;
        FixRejectionScreen screen(invalid);
        require(screen.present(fix("no-accuracy-bound", 1, 1'000'000'000),
                               1'020'000'000).reason == RejectionReason::InvalidPolicy,
                "missing operational accuracy bound was accepted");
    }
    {
        FixRejectionScreen screen(policy());
        require(screen.present(fix("date-line-a", 1, 1'000'000'000, 0.0, 179.99999),
                               1'020'000'000).forwardToCore(),
                "first date-line fix failed");
        require(screen.finalize("date-line-a", MeasurementStatus::Accepted).reason
                    == RejectionReason::AcceptedByCore, "date-line baseline was lost");
        require(screen.present(fix("date-line-b", 2, 2'000'000'000, 0.0, -179.99999),
                               2'020'000'000).forwardToCore(),
                "date-line wrapping produced a false physical rejection");
    }
    {
        FixRejectionScreen screen(policy());
        auto replay = fix("wrong-source", 1, 1'000'000'000);
        replay.source_kind = SourceKind::Replay;
        const auto result = screen.present(replay, 1'020'000'000);
        require(result.reason == RejectionReason::PrecheckRejected
                    && result.precheck_reason == Reason::ProvenanceMismatch,
                "wrong source provenance was forwarded");
    }
    std::cout << "gnss-rejection-native: PASS\n";
}
