#include "sih26168/gnss/fix_precheck.hpp"

#include <cstdlib>
#include <iostream>
#include <limits>
#include <string>

using sih26168::gnss::Decision;
using sih26168::gnss::FixPrecheck;
using sih26168::gnss::LocationFix;
using sih26168::gnss::Policy;
using sih26168::gnss::Reason;
using sih26168::gnss::SourceKind;

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

Policy policy() {
    return Policy{"session-1", "boot-1", "elapsed-realtime-1", SourceKind::Live,
                  "gps", 200'000'000};
}

LocationFix fix(std::string id = "fix-1", std::uint64_t seq = 1,
                std::int64_t source_ns = 1'000'000'000) {
    LocationFix value;
    value.evidence_id = std::move(id);
    value.session_id = "session-1";
    value.boot_id = "boot-1";
    value.clock_id = "elapsed-realtime-1";
    value.provider = "gps";
    value.sequence = seq;
    value.source_timestamp_ns = source_ns;
    value.arrival_elapsed_realtime_ns = source_ns + 10'000'000;
    value.lat_deg = 12.5;
    value.lon_deg = 77.5;
    value.hacc_m = 3.0;
    return value;
}

void expect(const Decision& decision, Reason reason) {
    require(decision.reason == reason, "unexpected GNSS precheck reason");
    require(decision.eligible == (reason == Reason::Eligible), "wrong GNSS eligibility");
}

}  // namespace

int main() {
    {
        FixPrecheck check(policy());
        auto first = fix();
        expect(check.present(first, 1'020'000'000), Reason::Eligible);
        expect(check.present(first, 1'020'000'000), Reason::DuplicateEvidenceId);
        require(check.consumedCount() == 1, "duplicate was consumed twice");
        expect(check.present(fix("fix-2", 2, 1'100'000'000), 1'120'000'000), Reason::Eligible);
    }
    {
        FixPrecheck check(policy());
        auto invalid = fix("bad");
        invalid.lat_deg = std::numeric_limits<double>::quiet_NaN();
        expect(check.present(invalid, 1'020'000'000), Reason::InvalidMeasurement);
        invalid.lat_deg = 12.5;
        expect(check.present(invalid, 1'020'000'000), Reason::DuplicateEvidenceId);
        expect(check.present(fix("good"), 1'020'000'000), Reason::Eligible);
    }
    {
        FixPrecheck check(policy());
        auto wrong = fix("wrong-boot");
        wrong.boot_id = "boot-2";
        expect(check.present(wrong, 1'020'000'000), Reason::ProvenanceMismatch);
        wrong = fix("wrong-clock");
        wrong.clock_id = "wall-time";
        expect(check.present(wrong, 1'020'000'000), Reason::ProvenanceMismatch);
        wrong = fix("wrong-session");
        wrong.session_id = "session-2";
        expect(check.present(wrong, 1'020'000'000), Reason::ProvenanceMismatch);
        wrong = fix("wrong-provider");
        wrong.provider = "network";
        expect(check.present(wrong, 1'020'000'000), Reason::ProvenanceMismatch);
        wrong = fix("wrong-source");
        wrong.source_kind = SourceKind::Replay;
        expect(check.present(wrong, 1'020'000'000), Reason::ProvenanceMismatch);
        require(check.consumedCount() == 5, "rejected provenance ID not consumed");
    }
    {
        FixPrecheck check(policy());
        auto missing = fix("");
        expect(check.present(missing, 1'020'000'000), Reason::EmptyEvidenceId);
        require(check.consumedCount() == 0, "empty evidence ID consumed");
        auto unsupported = fix("unsupported");
        unsupported.schema_version = 2;
        expect(check.present(unsupported, 1'020'000'000), Reason::UnsupportedSchema);
        auto mock = fix("mock");
        mock.is_mock = true;
        expect(check.present(mock, 1'020'000'000), Reason::MockFix);
    }
    {
        FixPrecheck check(policy());
        expect(check.present(fix("boundary"), 1'200'000'000), Reason::Eligible);
        auto stale = fix("stale", 2, 1'100'000'000);
        expect(check.present(stale, 1'300'000'001), Reason::StaleFix);
        auto future = fix("future", 3, 1'300'000'000);
        expect(check.present(future, 1'300'000'000), Reason::FutureFix);
        auto negative = fix("negative", 4);
        negative.source_timestamp_ns = -1;
        expect(check.present(negative, 1'020'000'000), Reason::InvalidTimestamp);
    }
    {
        FixPrecheck check(policy());
        expect(check.present(fix("first", 5), 1'020'000'000), Reason::Eligible);
        expect(check.present(fix("old-seq", 4, 1'100'000'000), 1'120'000'000),
               Reason::OutOfOrderFix);
        expect(check.present(fix("old-time", 6, 1'000'000'000), 1'120'000'000),
               Reason::OutOfOrderFix);
        expect(check.present(fix("next", 6, 1'100'000'000), 1'120'000'000),
               Reason::Eligible);
        auto regressed_now = fix("regressed-now", 7, 1'110'000'000);
        regressed_now.arrival_elapsed_realtime_ns = 1'115'000'000;
        expect(check.present(regressed_now, 1'119'000'000), Reason::InvalidTimestamp);
    }
    {
        FixPrecheck check(policy());
        auto invalid = fix("mask-1");
        invalid.field_mask = {"alt_m"};
        expect(check.present(invalid, 1'020'000'000), Reason::InvalidFieldMask);
        invalid = fix("mask-2");
        invalid.alt_m = 100.0;
        expect(check.present(invalid, 1'020'000'000), Reason::InvalidFieldMask);
        invalid = fix("mask-3");
        invalid.field_mask = {"speed_mps", "speed_mps"};
        invalid.speed_mps = 4.0;
        expect(check.present(invalid, 1'020'000'000), Reason::InvalidFieldMask);
        auto valid = fix("mask-good");
        valid.field_mask = {"alt_m", "speed_mps", "bearing_deg"};
        valid.alt_m = -5.0;
        valid.speed_mps = 4.0;
        valid.bearing_deg = 359.9999999999;
        expect(check.present(valid, 1'020'000'000), Reason::Eligible);
    }
    {
        FixPrecheck check(policy());
        auto invalid = fix("bad-hacc");
        invalid.hacc_m = 0.09;
        expect(check.present(invalid, 1'020'000'000), Reason::InvalidMeasurement);
        invalid = fix("bad-longitude");
        invalid.lon_deg = 181.0;
        expect(check.present(invalid, 1'020'000'000), Reason::InvalidMeasurement);
    }
    {
        auto replay_policy = policy();
        replay_policy.source_kind = SourceKind::Replay;
        FixPrecheck replay(replay_policy);
        auto replay_fix = fix();
        replay_fix.source_kind = SourceKind::Replay;
        expect(replay.present(replay_fix, 1'020'000'000), Reason::Eligible);
        replay_fix.evidence_id = "live-disguised";
        replay_fix.source_kind = SourceKind::Live;
        expect(replay.present(replay_fix, 1'020'000'000), Reason::ProvenanceMismatch);
    }
    {
        auto invalid_policy = policy();
        invalid_policy.max_age_ns = -1;
        FixPrecheck check(invalid_policy);
        expect(check.present(fix(), 1'020'000'000), Reason::InvalidPolicy);
        require(check.consumedCount() == 1, "invalid policy erased evidence identity");
    }
    {
        const auto invalid_kind = static_cast<SourceKind>(2);
        auto invalid_policy = policy();
        invalid_policy.source_kind = invalid_kind;
        FixPrecheck check(invalid_policy);
        auto malformed = fix("invalid-policy-kind");
        malformed.source_kind = invalid_kind;
        expect(check.present(malformed, 1'020'000'000), Reason::InvalidPolicy);
        expect(check.present(malformed, 1'020'000'000), Reason::DuplicateEvidenceId);
        require(check.consumedCount() == 1, "invalid policy kind erased evidence identity");
    }
    {
        FixPrecheck check(policy());
        auto malformed = fix("invalid-fix-kind");
        malformed.source_kind = static_cast<SourceKind>(2);
        expect(check.present(malformed, 1'020'000'000), Reason::InvalidSourceKind);
        expect(check.present(malformed, 1'020'000'000), Reason::DuplicateEvidenceId);
        require(check.consumedCount() == 1, "invalid fix kind erased evidence identity");
        expect(check.present(fix("valid-after-invalid-kind"), 1'020'000'000),
               Reason::Eligible);
    }
    std::cout << "gnss-precheck-native: PASS\n";
}
