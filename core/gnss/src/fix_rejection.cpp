#include "sih26168/gnss/fix_rejection.hpp"

#include <algorithm>
#include <cmath>
#include <utility>

namespace sih26168::gnss {
namespace {

constexpr double kEarthMeanRadiusM = 6'371'008.8;
constexpr double kRadiansPerDegree = 0.017453292519943295769;

double greatCircleDistanceM(const LocationFix& first, const LocationFix& second) {
    const double lat_a = first.lat_deg * kRadiansPerDegree;
    const double lat_b = second.lat_deg * kRadiansPerDegree;
    const double d_lat = (second.lat_deg - first.lat_deg) * kRadiansPerDegree;
    const double d_lon = std::remainder(second.lon_deg - first.lon_deg, 360.0)
        * kRadiansPerDegree;
    const double sin_lat = std::sin(d_lat / 2.0);
    const double sin_lon = std::sin(d_lon / 2.0);
    const double haversine = sin_lat * sin_lat
        + std::cos(lat_a) * std::cos(lat_b) * sin_lon * sin_lon;
    return 2.0 * kEarthMeanRadiusM
        * std::asin(std::sqrt(std::clamp(haversine, 0.0, 1.0)));
}

bool validPolicy(const RejectionPolicy& policy) {
    return !policy.precheck.session_id.empty() && !policy.precheck.boot_id.empty()
        && !policy.precheck.clock_id.empty() && !policy.precheck.provider.empty()
        && policy.precheck.max_age_ns >= 0
        && std::isfinite(policy.max_ground_speed_mps)
        && policy.max_ground_speed_mps > 0.0
        && std::isfinite(policy.max_horizontal_accuracy_m)
        && policy.max_horizontal_accuracy_m > 0.0;
}

RejectionDecision decision(RejectionReason reason, const std::string& evidence_id) {
    RejectionDecision result;
    result.reason = reason;
    result.evidence_id = evidence_id;
    return result;
}

}  // namespace

FixRejectionScreen::FixRejectionScreen(RejectionPolicy policy)
    : policy_(std::move(policy)), precheck_(policy_.precheck),
      policy_valid_(validPolicy(policy_)) {}

RejectionDecision FixRejectionScreen::present(
    const LocationFix& fix, std::int64_t now_elapsed_realtime_ns) {
    // WP-07.1 owns the evidence-once ledger. Even an invalid screen policy
    // or an outstanding core decision must not leave an incoming nonempty
    // source identity available for a later presentation.
    const Decision prechecked = precheck_.present(fix, now_elapsed_realtime_ns);
    if (!policy_valid_) {
        auto result = decision(RejectionReason::InvalidPolicy, fix.evidence_id);
        result.precheck_reason = prechecked.reason;
        return result;
    }
    if (!prechecked.eligible) {
        auto result = decision(RejectionReason::PrecheckRejected, fix.evidence_id);
        result.precheck_reason = prechecked.reason;
        return result;
    }
    if (pending_fix_) return decision(RejectionReason::PendingCoreDecision, fix.evidence_id);
    if (fix.hacc_m > policy_.max_horizontal_accuracy_m) {
        return decision(RejectionReason::UnusableAccuracy, fix.evidence_id);
    }

    if (last_core_accepted_fix_) {
        const auto& previous = *last_core_accepted_fix_;
        if (fix.source_timestamp_ns <= previous.source_timestamp_ns) {
            return decision(RejectionReason::InvalidGeometry, fix.evidence_id);
        }
        const double delta_seconds =
            static_cast<double>(fix.source_timestamp_ns - previous.source_timestamp_ns) * 1e-9;
        const double displacement_m = greatCircleDistanceM(previous, fix);
        // The reported horizontal-accuracy radii are a conservative allowance
        // around the two observations, not proof that either is unbiased.
        const double bound_m = policy_.max_ground_speed_mps * delta_seconds
            + previous.hacc_m + fix.hacc_m;
        if (!std::isfinite(displacement_m) || !std::isfinite(bound_m)) {
            return decision(RejectionReason::InvalidGeometry, fix.evidence_id);
        }
        if (displacement_m > bound_m) {
            auto result = decision(RejectionReason::ImplausibleDisplacement, fix.evidence_id);
            result.displacement_m = displacement_m;
            result.displacement_bound_m = bound_m;
            return result;
        }
    }

    pending_fix_ = fix;
    return decision(RejectionReason::ForwardToCore, fix.evidence_id);
}

RejectionDecision FixRejectionScreen::finalize(
    const std::string& evidence_id, navigation::MeasurementStatus core_status) {
    if (!pending_fix_) return decision(RejectionReason::NoPendingFix, evidence_id);
    if (evidence_id != pending_fix_->evidence_id) {
        return decision(RejectionReason::EvidenceMismatch, evidence_id);
    }
    auto result = decision(RejectionReason::CoreRejected, evidence_id);
    result.core_status = core_status;
    if (core_status == navigation::MeasurementStatus::Accepted) {
        result.reason = RejectionReason::AcceptedByCore;
        last_core_accepted_fix_ = *pending_fix_;
    } else if (core_status == navigation::MeasurementStatus::RejectedInnovationGate) {
        result.reason = RejectionReason::CoreInnovationRejected;
    }
    pending_fix_.reset();
    return result;
}

}  // namespace sih26168::gnss
