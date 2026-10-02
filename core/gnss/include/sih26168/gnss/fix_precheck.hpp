#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace sih26168::gnss {

enum class SourceKind { Live, Replay };

// I-02 values plus the session/boot/clock identity carried by the source
// envelope. Optional fields are present precisely when named by field_mask.
struct LocationFix {
    std::int32_t schema_version{1};
    std::string evidence_id;
    std::string session_id;
    std::string boot_id;
    std::string clock_id;
    SourceKind source_kind{SourceKind::Live};
    std::string provider;
    std::uint64_t sequence{0};
    std::int64_t source_timestamp_ns{0};
    std::int64_t arrival_elapsed_realtime_ns{0};
    double lat_deg{0.0};
    double lon_deg{0.0};
    double hacc_m{0.0};
    std::optional<double> alt_m;
    std::optional<double> vacc_m;
    std::optional<double> speed_mps;
    std::optional<double> speed_acc_mps;
    std::optional<double> bearing_deg;
    std::optional<double> bearing_acc_deg;
    bool is_mock{false};
    std::vector<std::string> field_mask;
};

// The maximum age is supplied by the owner of the C-09 policy. WP-07.1 does
// not freeze an empirical freshness threshold or recovery dwell.
struct Policy {
    std::string session_id;
    std::string boot_id;
    std::string clock_id;
    SourceKind source_kind{SourceKind::Live};
    std::string provider{"gps"};
    std::int64_t max_age_ns{0};
};

enum class Reason {
    Eligible,
    EmptyEvidenceId,
    DuplicateEvidenceId,
    InvalidPolicy,
    UnsupportedSchema,
    ProvenanceMismatch,
    MockFix,
    InvalidTimestamp,
    FutureFix,
    StaleFix,
    OutOfOrderFix,
    InvalidFieldMask,
    InvalidMeasurement,
};

struct Decision {
    Reason reason{Reason::InvalidPolicy};
    bool eligible{false};
    std::int64_t age_ns{0};
    std::string evidence_id;
};

// One instance belongs to one scientific session. Any nonempty evidence ID is
// consumed on first presentation, including rejected and malformed fixes.
// This precheck only authorizes further screening; it never accepts an I-12
// update into C-07 or changes navigation, outage, or reacquisition state.
class FixPrecheck {
public:
    explicit FixPrecheck(Policy policy);
    Decision present(const LocationFix& fix, std::int64_t now_elapsed_realtime_ns);
    std::size_t consumedCount() const noexcept { return consumed_ids_.size(); }

private:
    Policy policy_;
    std::unordered_set<std::string> consumed_ids_;
    std::unordered_map<std::string, std::uint64_t> last_sequence_by_provider_;
    std::unordered_map<std::string, std::int64_t> last_source_ns_by_provider_;
    std::optional<std::int64_t> last_now_ns_;
};

}  // namespace sih26168::gnss
