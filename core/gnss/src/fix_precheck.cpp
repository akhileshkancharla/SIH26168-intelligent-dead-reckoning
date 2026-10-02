#include "sih26168/gnss/fix_precheck.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <string_view>
#include <utility>

namespace sih26168::gnss {
namespace {

constexpr std::array<std::string_view, 6> kOptionalFields = {
    "alt_m", "vacc_m", "speed_mps", "speed_acc_mps", "bearing_deg", "bearing_acc_deg"};

bool finiteWithin(double value, double lower, double upper) {
    return std::isfinite(value) && value >= lower && value <= upper;
}

bool validOptional(const std::optional<double>& value, bool named, double lower, double upper) {
    return value.has_value() == named
        && (!value || finiteWithin(*value, lower, upper));
}

bool validMask(const LocationFix& fix) {
    std::unordered_set<std::string> names;
    for (const auto& name : fix.field_mask) {
        if (std::find(kOptionalFields.begin(), kOptionalFields.end(), name) == kOptionalFields.end()
            || !names.insert(name).second) {
            return false;
        }
    }
    const auto has = [&](std::string_view name) { return names.contains(std::string(name)); };
    return validOptional(fix.alt_m, has("alt_m"), -std::numeric_limits<double>::max(),
                         std::numeric_limits<double>::max())
        && validOptional(fix.vacc_m, has("vacc_m"), 0.0, std::numeric_limits<double>::max())
        && validOptional(fix.speed_mps, has("speed_mps"), 0.0, 100.0)
        && validOptional(fix.speed_acc_mps, has("speed_acc_mps"), 0.0,
                         std::numeric_limits<double>::max())
        && fix.bearing_deg.has_value() == has("bearing_deg")
        && (!fix.bearing_deg || (std::isfinite(*fix.bearing_deg)
                                  && *fix.bearing_deg >= 0.0 && *fix.bearing_deg < 360.0))
        && validOptional(fix.bearing_acc_deg, has("bearing_acc_deg"), 0.0, 180.0);
}

}  // namespace

FixPrecheck::FixPrecheck(Policy policy) : policy_(std::move(policy)) {}

Decision FixPrecheck::present(const LocationFix& fix, std::int64_t now_elapsed_realtime_ns) {
    const auto reject = [&](Reason reason, std::int64_t age = 0) {
        return Decision{reason, false, age, fix.evidence_id};
    };
    if (fix.evidence_id.empty()) return reject(Reason::EmptyEvidenceId);
    if (!consumed_ids_.insert(fix.evidence_id).second) return reject(Reason::DuplicateEvidenceId);

    if (policy_.session_id.empty() || policy_.boot_id.empty() || policy_.clock_id.empty()
        || policy_.provider.empty() || policy_.max_age_ns < 0) {
        return reject(Reason::InvalidPolicy);
    }
    if (fix.schema_version != 1) return reject(Reason::UnsupportedSchema);
    if (fix.session_id != policy_.session_id || fix.boot_id != policy_.boot_id
        || fix.clock_id != policy_.clock_id || fix.source_kind != policy_.source_kind
        || fix.provider != policy_.provider) {
        return reject(Reason::ProvenanceMismatch);
    }
    if (fix.is_mock) return reject(Reason::MockFix);
    if (fix.source_timestamp_ns < 0 || fix.arrival_elapsed_realtime_ns < 0
        || now_elapsed_realtime_ns < 0) {
        return reject(Reason::InvalidTimestamp);
    }
    if (fix.source_timestamp_ns > fix.arrival_elapsed_realtime_ns
        || fix.arrival_elapsed_realtime_ns > now_elapsed_realtime_ns) {
        return reject(Reason::FutureFix);
    }
    if (last_now_ns_ && now_elapsed_realtime_ns < *last_now_ns_) {
        return reject(Reason::InvalidTimestamp);
    }
    last_now_ns_ = now_elapsed_realtime_ns;
    // The ordered comparison above makes this subtraction safe from overflow.
    const auto age = now_elapsed_realtime_ns - fix.source_timestamp_ns;
    if (age > policy_.max_age_ns) return reject(Reason::StaleFix, age);
    if (const auto it = last_sequence_by_provider_.find(fix.provider);
        it != last_sequence_by_provider_.end()
        && (fix.sequence <= it->second
            || fix.source_timestamp_ns <= last_source_ns_by_provider_.at(fix.provider))) {
        return reject(Reason::OutOfOrderFix, age);
    }
    if (!validMask(fix)) return reject(Reason::InvalidFieldMask, age);
    if (!finiteWithin(fix.lat_deg, -90.0, 90.0)
        || !finiteWithin(fix.lon_deg, -180.0, 180.0)
        || !finiteWithin(fix.hacc_m, 0.1, std::numeric_limits<double>::max())) {
        return reject(Reason::InvalidMeasurement, age);
    }
    last_sequence_by_provider_[fix.provider] = fix.sequence;
    last_source_ns_by_provider_[fix.provider] = fix.source_timestamp_ns;
    return Decision{Reason::Eligible, true, age, fix.evidence_id};
}

}  // namespace sih26168::gnss
