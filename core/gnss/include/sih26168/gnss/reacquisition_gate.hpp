#pragma once

#include "sih26168/gnss/fix_rejection.hpp"
#include "sih26168/gnss/outage_state.hpp"

#include <cstdint>
#include <optional>
#include <string>
#include <unordered_set>

namespace sih26168::gnss {

// Counts and durations are frozen by the run configuration, not selected by
// this host component. At least two distinct fixes and positive dwell are
// mandatory. All epochs use the session's boot-scoped monotonic clock.
struct ReacquisitionPolicy {
    std::string session_id;
    std::string boot_id;
    std::string clock_id;
    std::uint32_t required_consistent_fixes{0};
    std::int64_t minimum_dwell_ns{0};
    std::int64_t maximum_dwell_ns{0};
    std::int64_t maximum_interfix_gap_ns{0};
};

enum class ReacquisitionReason {
    Dwell,
    Recovered,
    InvalidPolicy,
    ClockDomainMismatch,
    InvalidEpoch,
    InvalidMode,
    InvalidMeasurementLineage,
    UpstreamRejected,
    QualityRejected,
    DuplicateMeasurementId,
    InconsistentTiming,
    InnovationRejected,
    CoreScreenFailure,
    CoreUpdateRejected,
    TrackerRejected,
};

struct ReacquisitionResult {
    ReacquisitionReason reason{ReacquisitionReason::InvalidPolicy};
    std::string evidence_id;
    std::uint32_t dwell_count{0};
    std::optional<double> nis;
    std::optional<RejectionReason> upstream_reason;
    std::optional<navigation::MeasurementStatus> screen_status;
    std::optional<navigation::MeasurementStatus> core_status;
    std::optional<double> scientific_jump_m;
    bool scientific_update_accepted{false};
};

// C-09 policy gate on the serial C-06 executor. Each source fix first passes
// WP-07.1/07.3; C-07 then screens the same canonical measurement without an
// update. Earlier passing fixes are withheld. Only the final fix, after a
// policy-supplied dwell, may be submitted once to C-07's authoritative update.
class ReacquisitionGate {
public:
    ReacquisitionGate(ReacquisitionPolicy policy,
                      OutageStateTracker& outage,
                      FixRejectionScreen& rejection,
                      navigation::NavigationCore& core);

    [[nodiscard]] ReacquisitionResult present(const OutageContext& context,
                                               const LocationFix& fix,
                                               const navigation::MeasurementInput& measurement,
                                               contracts::HealthIntegrityStateV1 screened_availability);

private:
    void clearStreak() noexcept;
    void rejectActive(const OutageContext& context);

    ReacquisitionPolicy policy_;
    OutageStateTracker& outage_;
    FixRejectionScreen& rejection_;
    navigation::NavigationCore& core_;
    bool policy_valid_{false};
    std::string first_evidence_id_;
    std::optional<std::int64_t> first_epoch_ns_;
    std::optional<std::int64_t> last_epoch_ns_;
    std::uint32_t dwell_count_{0};
    std::unordered_set<std::string> consumed_measurement_ids_;
};

}  // namespace sih26168::gnss
