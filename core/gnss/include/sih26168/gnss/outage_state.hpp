#pragma once

#include "sih26168/contracts/enums.hpp"
#include "sih26168/gnss/fix_precheck.hpp"

#include <cstdint>
#include <optional>
#include <string>
#include <unordered_set>

namespace sih26168::gnss {

// All epochs belong to one boot-scoped monotonic clock. Durations are supplied
// by the frozen run configuration; this module does not choose a threshold.
struct OutagePolicy {
    std::string session_id;
    std::string boot_id;
    std::string clock_id;
    std::int64_t degrade_after_ns{0};
    std::int64_t unavailable_after_ns{0};
};

struct OutageContext {
    std::string session_id;
    std::string boot_id;
    std::string clock_id;
    std::int64_t epoch_ns{0};
};

enum class OutageKind { Natural, Quality, SoftwareSimulated };

// A software-simulated declaration requires the identity of a separately
// validated, frozen C-12 mask. This tracker never applies or edits that mask.
struct OutageDeclaration {
    OutageKind kind{OutageKind::Natural};
    std::string reason;
    std::string mask_id;
};

enum class OutageError {
    None,
    InvalidPolicy,
    ClockDomainMismatch,
    InvalidEpoch,
    EpochRegressed,
    MissingEvidenceId,
    IneligibleAid,
    DuplicateEvidenceId,
    NonIncreasingAidEpoch,
    InvalidDeclaration,
    IneligibleCandidate,
    CandidateMismatch,
    InvalidTransition,
    TerminalFault,
};

enum class OutageTransitionCause {
    None,
    AcceptedAid,
    QualityDegraded,
    TimedDegradation,
    TimedOutage,
    DeclaredOutage,
    CandidateReturn,
    CandidateRejected,
    CoreFault,
};

struct OutageSnapshot {
    contracts::HealthIntegrityStateV1 availability{
        contracts::HealthIntegrityStateV1::UNAVAILABLE};
    contracts::NavigationModeV1 mode{contracts::NavigationModeV1::INITIALIZING};
    std::optional<std::int64_t> last_accepted_aid_ns;
    std::optional<std::int64_t> outage_start_ns;
    std::optional<OutageKind> outage_kind;
    std::string outage_reason;
    std::string mask_id;
    std::string candidate_evidence_id;
    std::uint64_t transition_sequence{0};
};

struct OutageResult {
    OutageError error{OutageError::None};
    OutageTransitionCause cause{OutageTransitionCause::None};
    bool state_changed{false};
    std::optional<std::int64_t> effective_epoch_ns;

    [[nodiscard]] bool applied() const noexcept {
        return error == OutageError::None;
    }
};

// C-09 advisory state only. The caller may report an aid as accepted only
// after C-07 has accepted the corresponding canonical update and C-09 has
// independently classified the fix HEALTHY. No method can
// restore aiding from BLACKOUT_DR/REACQUIRING; WP-07.4 owns that gate.
class OutageStateTracker {
public:
    explicit OutageStateTracker(OutagePolicy policy);

    [[nodiscard]] OutageResult acceptedAid(const OutageContext& context,
                                           const std::string& evidence_id,
                                           bool core_update_accepted,
                                           contracts::HealthIntegrityStateV1 screened_availability);
    [[nodiscard]] OutageResult qualityDegraded(const OutageContext& context);
    [[nodiscard]] OutageResult advance(const OutageContext& context);
    [[nodiscard]] OutageResult declareOutage(const OutageContext& context,
                                             const OutageDeclaration& declaration);
    [[nodiscard]] OutageResult candidateReturned(const OutageContext& context,
                                                  const Decision& precheck);
    [[nodiscard]] OutageResult candidateRejected(const OutageContext& context,
                                                  const std::string& evidence_id);
    [[nodiscard]] OutageResult coreFault(const OutageContext& context);

    [[nodiscard]] const OutageSnapshot& snapshot() const noexcept { return state_; }

private:
    [[nodiscard]] OutageError validate(const OutageContext& context) const;
    [[nodiscard]] bool outageOverdue(std::int64_t epoch_ns) const noexcept;
    void observeEpoch(std::int64_t epoch_ns) noexcept;
    void enterBlackout(std::int64_t start_ns, OutageKind kind,
                       const std::string& reason, const std::string& mask_id);

    OutagePolicy policy_;
    bool policy_valid_{false};
    OutageSnapshot state_;
    std::optional<std::int64_t> last_observed_epoch_ns_;
    std::unordered_set<std::string> accepted_aid_ids_;
    std::unordered_set<std::string> candidate_ids_;
};

}  // namespace sih26168::gnss
