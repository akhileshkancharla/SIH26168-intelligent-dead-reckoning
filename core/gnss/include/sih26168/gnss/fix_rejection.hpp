#pragma once

#include "sih26168/gnss/fix_precheck.hpp"
#include "sih26168/navigation_core.hpp"

#include <cstdint>
#include <optional>
#include <string>

namespace sih26168::gnss {

// The operational bound must come from a separately approved, frozen run
// policy. This component deliberately supplies no empirical speed threshold.
struct RejectionPolicy {
    Policy precheck;
    double max_ground_speed_mps{0.0};
    double max_horizontal_accuracy_m{0.0};
};

enum class RejectionReason {
    ForwardToCore,
    AcceptedByCore,
    InvalidPolicy,
    PrecheckRejected,
    UnusableAccuracy,
    ImplausibleDisplacement,
    InvalidGeometry,
    CoreInnovationRejected,
    CoreRejected,
    WithheldForRecoveryDwell,
    PendingCoreDecision,
    NoPendingFix,
    EvidenceMismatch,
};

struct RejectionDecision {
    RejectionReason reason{RejectionReason::InvalidPolicy};
    std::string evidence_id;
    std::optional<Reason> precheck_reason;
    std::optional<Decision> precheck_decision;
    std::optional<navigation::MeasurementStatus> core_status;
    std::optional<double> displacement_m;
    std::optional<double> displacement_bound_m;

    [[nodiscard]] bool forwardToCore() const noexcept {
        return reason == RejectionReason::ForwardToCore;
    }
};

// C-09's bounded screening and reason accounting. A fix must pass WP-07.1 and
// physical plausibility before the caller constructs I-12. C-07 remains the
// sole owner of the innovation gate, accepted update, state and covariance.
// The caller must pass the actual C-07 result for the same evidence ID to
// finalize(); this host component cannot authenticate a fabricated result.
class FixRejectionScreen {
public:
    explicit FixRejectionScreen(RejectionPolicy policy);

    [[nodiscard]] RejectionDecision present(const LocationFix& fix,
                                            std::int64_t now_elapsed_realtime_ns);
    [[nodiscard]] RejectionDecision finalize(
        const std::string& evidence_id,
        navigation::MeasurementStatus core_status);
    // Release a screened candidate without claiming a C-07 update or changing
    // the accepted displacement baseline. Its WP-07.1 identity stays consumed.
    [[nodiscard]] RejectionDecision withholdForRecoveryDwell(
        const std::string& evidence_id);

    [[nodiscard]] std::size_t consumedCount() const noexcept {
        return precheck_.consumedCount();
    }

private:
    RejectionPolicy policy_;
    FixPrecheck precheck_;
    bool policy_valid_{false};
    std::optional<LocationFix> last_core_accepted_fix_;
    std::optional<LocationFix> pending_fix_;
};

}  // namespace sih26168::gnss
