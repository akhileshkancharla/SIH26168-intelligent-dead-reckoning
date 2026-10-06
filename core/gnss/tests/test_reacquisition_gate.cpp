#include "sih26168/gnss/reacquisition_gate.hpp"

#include <cmath>
#include <functional>
#include <iostream>
#include <stdexcept>

namespace gnss = sih26168::gnss;
namespace nav = sih26168::navigation;
namespace contracts = sih26168::contracts;

namespace {

constexpr auto kHealthy = contracts::HealthIntegrityStateV1::HEALTHY;

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

constexpr std::int64_t kAnchor = 1'000'000'000;
constexpr std::int64_t kFirst = kAnchor + 30'000'000;
constexpr std::int64_t kSecond = kAnchor + 40'000'000;

nav::InitialState initial() {
    nav::InitialState state;
    state.source_timestamp.nanoseconds = kAnchor;
    state.clock_id.value = "elapsed";
    state.origin_id.value = "origin";
    state.mode = nav::NavigationMode::BlackoutDeadReckoning;
    state.covariance = nav::identityCovariance(1.0);
    return state;
}

gnss::OutageContext at(std::int64_t epoch) {
    return {"session", "boot", "elapsed", epoch};
}

gnss::OutagePolicy outagePolicy() {
    return {"session", "boot", "elapsed", 10'000'000, 20'000'000};
}

gnss::RejectionPolicy rejectionPolicy() {
    return {gnss::Policy{"session", "boot", "elapsed", gnss::SourceKind::Live,
                         "gps", 20'000'000}, 40.0, 25.0};
}

gnss::ReacquisitionPolicy recoveryPolicy() {
    return {"session", "boot", "elapsed", 2, 10'000'000,
            100'000'000, 30'000'000};
}

gnss::LocationFix fix(const char* id, std::uint64_t sequence,
                      std::int64_t epoch) {
    gnss::LocationFix value;
    value.evidence_id = id;
    value.session_id = "session";
    value.boot_id = "boot";
    value.clock_id = "elapsed";
    value.provider = "gps";
    value.sequence = sequence;
    value.source_timestamp_ns = epoch - 1'000'000;
    value.arrival_elapsed_realtime_ns = epoch;
    value.lat_deg = 12.5;
    value.lon_deg = 77.5;
    value.hacc_m = 3.0;
    return value;
}

nav::MeasurementInput measurement(const char* id, std::uint64_t sequence,
                                  std::int64_t epoch, double north = 0.0) {
    nav::MeasurementInput value;
    value.sequence.value = sequence;
    value.measurement_id.value = std::string("measurement-") + id;
    value.state_epoch_ns.nanoseconds = epoch;
    value.arrival_timestamp.nanoseconds = epoch;
    value.origin_id.value = "origin";
    value.provider_evidence_ids = {nav::EvidenceIdentifier{id}};
    value.precheck.status = nav::MeasurementPrecheckStatus::Passed;
    value.kind = nav::MeasurementKind::Position;
    value.z = {north, 0.0, 0.0, 0.0, 0.0, 0.0};
    for (int index = 0; index < 3; ++index) value.R[index * 6 + index] = 1.0;
    return value;
}

void advance(nav::NavigationCore& core, std::uint64_t sequence,
             std::int64_t epoch) {
    nav::ImuSample imu;
    imu.sequence.value = sequence;
    imu.evidence_id.value = "imu-" + std::to_string(sequence);
    imu.source_timestamp.nanoseconds = epoch;
    imu.arrival_timestamp.nanoseconds = epoch;
    imu.specific_force_b_mps2 = {0.0, 0.0, -9.80665};
    nav::ImuBatch batch;
    batch.batch_id.value = "batch-" + std::to_string(sequence);
    batch.samples = {imu};
    batch.first_seq = imu.sequence;
    batch.last_seq = imu.sequence;
    batch.clock_id.value = "elapsed";
    require(core.propagate(batch).accepted(), "core propagation failed");
}

struct Scenario {
    gnss::OutageStateTracker outage{outagePolicy()};
    gnss::FixRejectionScreen rejection{rejectionPolicy()};
    nav::NavigationCore core{initial()};
    gnss::ReacquisitionGate gate{recoveryPolicy(), outage, rejection, core};

    Scenario() {
        require(outage.acceptedAid(at(kAnchor), "anchor", true,
                                  contracts::HealthIntegrityStateV1::HEALTHY).applied(),
                "initial aid failed");
        require(outage.advance(at(kAnchor + 20'000'000)).applied()
                    && outage.snapshot().mode == contracts::NavigationModeV1::BLACKOUT_DR,
                "blackout did not start");
    }
};

}  // namespace

int main() {
    int failures = 0;
    const auto run = [&](const char* name, const std::function<void()>& body) {
        try {
            body();
            std::cout << "PASS " << name << '\n';
        } catch (const std::exception& error) {
            ++failures;
            std::cerr << "FAIL " << name << ": " << error.what() << '\n';
        }
    };

    run("first_fix_has_no_scientific_influence_then_second_recovers", [] {
        Scenario s;
        advance(s.core, 1, kFirst);
        const auto before = s.core.stateSnapshot();
        const auto covariance = s.core.covarianceSnapshot();
        const auto used = s.core.consumedEvidenceCount();
        const auto first = s.gate.present(at(kFirst), fix("first", 1, kFirst),
                                          measurement("first", 1, kFirst), kHealthy);
        require(first.reason == gnss::ReacquisitionReason::Dwell
                    && first.dwell_count == 1 && !first.scientific_update_accepted,
                "first returning fix received scientific influence");
        require(s.core.stateSnapshot().position_n_m == before.position_n_m
                    && s.core.stateSnapshot().sequence.value == before.sequence.value
                    && s.core.covarianceSnapshot().covariance_15x15
                        == covariance.covariance_15x15
                    && s.core.consumedEvidenceCount() == used + 1,
                "screening changed state/covariance or failed to consume C-07 identity");
        require(s.core.update(measurement("first", 1, kFirst)).status
                    == nav::MeasurementStatus::RejectedDuplicateEvidenceIdentifier,
                "withheld first fix bypassed recovery through direct C-07 update");
        advance(s.core, 2, kSecond);
        const auto before_update = s.core.consumedEvidenceCount();
        const auto second = s.gate.present(at(kSecond), fix("second", 2, kSecond),
                                           measurement("second", 2, kSecond), kHealthy);
        require(second.reason == gnss::ReacquisitionReason::Recovered
                    && second.dwell_count == 2 && second.scientific_update_accepted
                    && second.core_status == nav::MeasurementStatus::Accepted
                    && s.outage.snapshot().mode == contracts::NavigationModeV1::GNSS_AIDED
                    && s.core.consumedEvidenceCount() == before_update + 1,
                "second consistent fix did not restore aiding exactly once");
    });

    run("biased_second_fix_rejects_without_core_update", [] {
        Scenario s;
        advance(s.core, 1, kFirst);
        require(s.gate.present(at(kFirst), fix("first", 1, kFirst),
                               measurement("first", 1, kFirst), kHealthy).reason
                    == gnss::ReacquisitionReason::Dwell, "first dwell failed");
        advance(s.core, 2, kSecond);
        const auto used = s.core.consumedEvidenceCount();
        const auto bad = s.gate.present(at(kSecond), fix("biased", 2, kSecond),
                                        measurement("biased", 2, kSecond, 100.0), kHealthy);
        require(bad.reason == gnss::ReacquisitionReason::InnovationRejected
                    && !bad.scientific_update_accepted
                    && s.outage.snapshot().mode == contracts::NavigationModeV1::BLACKOUT_DR
                    && s.core.consumedEvidenceCount() == used + 1,
                "biased return escaped the innovation screen");
    });

    run("biased_first_fix_never_starts_a_usable_dwell", [] {
        Scenario s;
        advance(s.core, 1, kFirst);
        const auto before = s.core.stateSnapshot();
        const auto count = s.core.consumedEvidenceCount();
        const auto result = s.gate.present(
            at(kFirst), fix("biased-first", 1, kFirst),
            measurement("biased-first", 1, kFirst, 100.0), kHealthy);
        require(result.reason == gnss::ReacquisitionReason::InnovationRejected
                    && s.outage.snapshot().mode == contracts::NavigationModeV1::BLACKOUT_DR
                    && s.core.consumedEvidenceCount() == count + 1
                    && s.core.stateSnapshot().position_n_m == before.position_n_m,
                "first biased return gained scientific influence");
    });

    run("intermittent_return_resets_dwell", [] {
        Scenario s;
        advance(s.core, 1, kFirst);
        require(s.gate.present(at(kFirst), fix("first", 1, kFirst),
                               measurement("first", 1, kFirst), kHealthy).reason
                    == gnss::ReacquisitionReason::Dwell, "first dwell failed");
        const auto late = kFirst + 40'000'000;
        advance(s.core, 2, late);
        const auto gap = s.gate.present(at(late), fix("late", 2, late),
                                        measurement("late", 2, late), kHealthy);
        require(gap.reason == gnss::ReacquisitionReason::InconsistentTiming
                    && s.outage.snapshot().mode == contracts::NavigationModeV1::BLACKOUT_DR,
                "intermittent return did not reset to the same blackout");
    });

    run("regressed_return_epoch_cannot_keep_active_dwell", [] {
        Scenario s;
        advance(s.core, 1, kFirst);
        require(s.gate.present(at(kFirst), fix("first", 1, kFirst),
                               measurement("first", 1, kFirst), kHealthy).reason
                    == gnss::ReacquisitionReason::Dwell, "first dwell failed");
        auto earlier = fix("regressed", 2, kFirst - 1);
        const auto result = s.gate.present(
            at(kFirst - 1), earlier, measurement("regressed", 2, kFirst - 1),
            kHealthy);
        require(result.reason == gnss::ReacquisitionReason::InvalidEpoch
                    && s.outage.snapshot().mode == contracts::NavigationModeV1::BLACKOUT_DR,
                "regressed return retained an active reacquisition dwell");
    });

    run("invalid_policy_cannot_recover", [] {
        Scenario s;
        auto policy = recoveryPolicy();
        policy.required_consistent_fixes = 1;
        gnss::ReacquisitionGate invalid(policy, s.outage, s.rejection, s.core);
        advance(s.core, 1, kFirst);
        require(invalid.present(at(kFirst), fix("first", 1, kFirst),
                                measurement("first", 1, kFirst), kHealthy).reason
                    == gnss::ReacquisitionReason::InvalidPolicy
                    && s.outage.snapshot().mode == contracts::NavigationModeV1::BLACKOUT_DR,
                "single-fix policy was accepted");
    });

    run("duplicate_return_resets_without_core_update", [] {
        Scenario s;
        advance(s.core, 1, kFirst);
        require(s.gate.present(at(kFirst), fix("first", 1, kFirst),
                               measurement("first", 1, kFirst), kHealthy).reason
                    == gnss::ReacquisitionReason::Dwell, "first dwell failed");
        advance(s.core, 2, kSecond);
        const auto count = s.core.consumedEvidenceCount();
        const auto duplicate = s.gate.present(at(kSecond), fix("first", 2, kSecond),
                                              measurement("first", 2, kSecond), kHealthy);
        require(duplicate.reason == gnss::ReacquisitionReason::UpstreamRejected
                    && s.outage.snapshot().mode == contracts::NavigationModeV1::BLACKOUT_DR
                    && s.core.consumedEvidenceCount() == count,
                "duplicate returning source influenced recovery");
    });

    run("degraded_quality_never_enters_dwell", [] {
        Scenario s;
        advance(s.core, 1, kFirst);
        const auto result = s.gate.present(
            at(kFirst), fix("degraded", 1, kFirst),
            measurement("degraded", 1, kFirst),
            contracts::HealthIntegrityStateV1::DEGRADED);
        require(result.reason == gnss::ReacquisitionReason::QualityRejected
                    && s.rejection.consumedCount() == 1
                    && s.core.consumedEvidenceCount() == 2
                    && s.outage.snapshot().mode == contracts::NavigationModeV1::BLACKOUT_DR,
                "degraded candidate bypassed independent C-09 quality screening");
    });

    run("canonical_measurement_identity_cannot_be_reused", [] {
        Scenario s;
        advance(s.core, 1, kFirst);
        require(s.gate.present(at(kFirst), fix("first", 1, kFirst),
                               measurement("first", 1, kFirst), kHealthy).reason
                    == gnss::ReacquisitionReason::Dwell,
                "first dwell failed");
        advance(s.core, 2, kSecond);
        auto repeated_id = measurement("second", 2, kSecond);
        repeated_id.measurement_id.value = "measurement-first";
        const auto result = s.gate.present(
            at(kSecond), fix("second", 2, kSecond), repeated_id, kHealthy);
        require(result.reason == gnss::ReacquisitionReason::DuplicateMeasurementId
                    && s.outage.snapshot().mode == contracts::NavigationModeV1::BLACKOUT_DR,
                "repeated canonical evidence identity bypassed C-07 ledger");
    });

    run("reconstructed_gate_cannot_reuse_screened_core_evidence", [] {
        Scenario s;
        advance(s.core, 1, kFirst);
        require(s.gate.present(at(kFirst), fix("first", 1, kFirst),
                               measurement("first", 1, kFirst), kHealthy).reason
                    == gnss::ReacquisitionReason::Dwell,
                "first measurement was not withheld");
        require(s.outage.candidateRejected(at(kFirst), "first").applied(),
                "could not end the first recovery attempt");
        gnss::FixRejectionScreen replacement_rejection(rejectionPolicy());
        gnss::ReacquisitionGate replacement_gate(
            recoveryPolicy(), s.outage, replacement_rejection, s.core);
        advance(s.core, 2, kSecond);
        auto repeated = measurement("new-source", 2, kSecond);
        repeated.measurement_id.value = "measurement-first";
        const auto before = s.core.consumedEvidenceCount();
        const auto result = replacement_gate.present(
            at(kSecond), fix("new-source", 2, kSecond), repeated, kHealthy);
        require(result.reason == gnss::ReacquisitionReason::DuplicateMeasurementId
                    && result.screen_status
                        == nav::MeasurementStatus::RejectedDuplicateEvidenceIdentifier
                    && s.core.consumedEvidenceCount() == before
                    && s.outage.snapshot().mode == contracts::NavigationModeV1::BLACKOUT_DR,
                "reconstructed C-09 gate bypassed C-07 evidence ownership");
    });

    run("malformed_measurement_lineage_consumes_source_and_rejects", [] {
        Scenario s;
        advance(s.core, 1, kFirst);
        auto wrong = measurement("first", 1, kFirst);
        wrong.provider_evidence_ids = {nav::EvidenceIdentifier{"other-fix"}};
        require(s.gate.present(at(kFirst), fix("first", 1, kFirst), wrong, kHealthy).reason
                    == gnss::ReacquisitionReason::InvalidMeasurementLineage,
                "wrong source lineage reached the core");
        require(s.rejection.consumedCount() == 1
                    && s.core.consumedEvidenceCount() == 2
                    && s.outage.snapshot().mode == contracts::NavigationModeV1::BLACKOUT_DR,
                "malformed first presentation was not consumed or contained");
        require(s.gate.present(at(kFirst), fix("first", 1, kFirst),
                               measurement("first", 1, kFirst), kHealthy).reason
                    == gnss::ReacquisitionReason::UpstreamRejected,
                "malformed fix was upgraded and retried");
    });

    run("three_fix_policy_cannot_recover_after_two", [] {
        gnss::OutageStateTracker outage(outagePolicy());
        gnss::FixRejectionScreen rejection(rejectionPolicy());
        nav::NavigationCore core(initial());
        auto policy = recoveryPolicy();
        policy.required_consistent_fixes = 3;
        gnss::ReacquisitionGate gate(policy, outage, rejection, core);
        require(outage.acceptedAid(at(kAnchor), "anchor", true,
                                  contracts::HealthIntegrityStateV1::HEALTHY).applied(),
                "initial aid failed");
        require(outage.advance(at(kAnchor + 20'000'000)).applied(),
                "blackout failed");
        advance(core, 1, kFirst);
        require(gate.present(at(kFirst), fix("first", 1, kFirst),
                             measurement("first", 1, kFirst), kHealthy).reason
                    == gnss::ReacquisitionReason::Dwell, "first dwell failed");
        advance(core, 2, kSecond);
        const auto before = core.consumedEvidenceCount();
        const auto second = gate.present(at(kSecond), fix("second", 2, kSecond),
                                         measurement("second", 2, kSecond), kHealthy);
        require(second.reason == gnss::ReacquisitionReason::Dwell
                    && second.dwell_count == 2 && !second.scientific_update_accepted
                    && core.consumedEvidenceCount() == before + 1
                    && outage.snapshot().mode == contracts::NavigationModeV1::REACQUIRING,
                "two fixes bypassed the configured three-fix dwell");
    });

    return failures == 0 ? 0 : 1;
}
