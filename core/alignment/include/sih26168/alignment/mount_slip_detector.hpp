#pragma once

#include "sih26168/alignment/alignment_estimate.hpp"

#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <unordered_set>

namespace sih26168::alignment {

inline constexpr double kFrozenSlipRotationThresholdRad =
    15.0 * 3.14159265358979323846 / 180.0;
inline constexpr std::int64_t kFrozenMaximumSlipDetectionGapNs =
    1'000'000'000;
inline constexpr const char* kMountSlipDetectorMethodId =
    "S3-MOUNT-SLIP-GEODESIC-v1";

struct MountOrientationObservation {
    std::uint64_t sequence{0};
    std::int64_t epoch_ns{0};
    std::array<double, 4> q_v_b_wxyz{1.0, 0.0, 0.0, 0.0};
    std::string evidence_id;
    std::string quality_evidence_id;
    bool quality_eligible{false};
};

struct MountSlipDetectorConfig {
    std::string config_id;
};

enum class MountSlipOutcome {
    NoSlip,
    SlipSuspected,
    AlreadyLatched,
    NotArmed,
    InvalidConfiguration,
    InvalidInput,
    QualityIneligible,
    SequenceNotIncreasing,
    EpochRegressed,
    MonitoringGap,
    BaselineChanged,
    PublicationRejected,
};

struct MountSlipDecision {
    MountSlipOutcome outcome{MountSlipOutcome::NotArmed};
    std::optional<double> angular_change_rad{std::nullopt};
    AlignmentEstimateError publication_error{AlignmentEstimateError::None};

    [[nodiscard]] bool slipSuspected() const noexcept {
        return outcome == MountSlipOutcome::SlipSuspected;
    }
};

// Monitors quality-eligible C-05 mount-orientation evidence against an armed
// VALID I-06 posterior. It owns no C-07 state and never rewrites raw IMU axes.
// A detected slip is synchronously published through the supplied I-06
// publisher, so dependent aids are disabled before observe() returns.
class MountSlipDetector {
public:
    MountSlipDetector(AlignmentEstimatePublisher& publisher,
                      MountSlipDetectorConfig config);

    // Arms only from the publisher's current structurally valid VALID record.
    // After a latched slip, the publisher must first accept a recovered VALID
    // record with new evidence identity; recovery is never automatic here.
    [[nodiscard]] bool arm();

    [[nodiscard]] MountSlipDecision observe(
        const MountOrientationObservation& observation);

    [[nodiscard]] bool armed() const noexcept;
    [[nodiscard]] bool slipLatched() const noexcept;

private:
    [[nodiscard]] MountSlipDecision fail(MountSlipOutcome outcome) noexcept;
    [[nodiscard]] bool currentBaselineUnchanged() const;
    [[nodiscard]] bool hasNewRecoveryEvidence(
        const contracts::AlignmentEstimate& candidate) const;

    AlignmentEstimatePublisher& publisher_;
    MountSlipDetectorConfig config_;
    std::optional<contracts::AlignmentEstimate> baseline_;
    std::optional<std::uint64_t> last_observation_sequence_;
    std::optional<std::int64_t> last_observation_epoch_ns_;
    std::unordered_set<std::string> consumed_evidence_ids_;
    bool slip_latched_{false};
};

[[nodiscard]] const char* toString(MountSlipOutcome outcome) noexcept;

}  // namespace sih26168::alignment
