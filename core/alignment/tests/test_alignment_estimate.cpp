#include "sih26168/alignment/alignment_estimate.hpp"

#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

namespace alignment = sih26168::alignment;
namespace contracts = sih26168::contracts;

namespace {

int failures = 0;
int total = 0;

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

void run(const std::string& name, const std::function<void()>& test) {
    ++total;
    try {
        test();
        std::cout << "PASS " << name << '\n';
    } catch (const std::exception& exception) {
        ++failures;
        std::cerr << "FAIL " << name << ": " << exception.what() << '\n';
    }
}

contracts::AlignmentEstimate estimate(
    contracts::AlignmentStatusV1 status = contracts::AlignmentStatusV1::VALID) {
    contracts::AlignmentEstimate value;
    value.sequence = 7;
    value.epoch_ns = 12'000'000'000;
    value.q_v_b_wxyz = {1.0, 0.0, 0.0, 0.0};
    value.covariance_3x3 = {
        0.01, 0.001, 0.0,
        0.001, 0.02, 0.0,
        0.0, 0.0, 0.03,
    };
    value.status = status;
    value.observability = 0.75;
    value.slip_probability = 0.05;
    value.method_id = "S3-M1";
    value.evidence_ids = {"imu-window-7", "gnss-window-7", "quality-7"};
    value.config_id = "s3-config-v1";
    return value;
}

void requireError(const contracts::AlignmentEstimate& value,
                  alignment::AlignmentEstimateError expected,
                  const std::string& message) {
    require(alignment::validateAlignmentEstimate(value).error == expected, message);
}

}  // namespace

int main() {
    run("valid_i06_posterior_is_eligible", [] {
        const auto value = estimate();
        require(alignment::validateAlignmentEstimate(value).valid(),
                "valid I-06 posterior was rejected");
        require(alignment::dependentAidsEligible(value),
                "valid I-06 posterior did not enable its safety gate");
    });

    run("all_nonvalid_states_disable_dependent_aids", [] {
        for (const auto status : {
                 contracts::AlignmentStatusV1::UNINITIALIZED,
                 contracts::AlignmentStatusV1::UNCERTAIN,
                 contracts::AlignmentStatusV1::SLIP_SUSPECTED,
             }) {
            auto value = estimate(status);
            require(alignment::validateAlignmentEstimate(value).valid(),
                    "explicit failure state was not representable");
            require(!alignment::dependentAidsEligible(value),
                    "non-VALID state enabled dependent aids");
        }
    });

    run("quaternion_must_be_finite_unit_and_canonical", [] {
        auto value = estimate();
        value.q_v_b_wxyz[1] = std::numeric_limits<double>::quiet_NaN();
        requireError(value, alignment::AlignmentEstimateError::NonFiniteQuaternion,
                     "non-finite quaternion was accepted");
        value = estimate();
        value.q_v_b_wxyz = {2.0, 0.0, 0.0, 0.0};
        requireError(value, alignment::AlignmentEstimateError::NonUnitQuaternion,
                     "non-unit quaternion was accepted");
        value.q_v_b_wxyz = {-1.0, 0.0, 0.0, 0.0};
        requireError(value, alignment::AlignmentEstimateError::NonCanonicalQuaternion,
                     "negative-w quaternion was accepted");
    });

    run("covariance_must_be_finite_symmetric_and_positive_semidefinite", [] {
        auto value = estimate();
        value.covariance_3x3[0] = std::numeric_limits<double>::infinity();
        requireError(value, alignment::AlignmentEstimateError::NonFiniteCovariance,
                     "non-finite covariance was accepted");
        value = estimate();
        value.covariance_3x3[1] = 0.2;
        requireError(value, alignment::AlignmentEstimateError::NonSymmetricCovariance,
                     "asymmetric covariance was accepted");
        value = estimate();
        value.covariance_3x3 = {
            1.0, 0.0, 0.0,
            0.0, 0.0, 0.0,
            0.0, 0.0, 1.0,
        };
        require(alignment::validateAlignmentEstimate(value).valid(),
                "singular positive-semidefinite covariance was rejected");
        value.covariance_3x3 = {
            1.0, 0.0, 0.0,
            0.0, -0.01, 0.0,
            0.0, 0.0, 1.0,
        };
        requireError(value,
                     alignment::AlignmentEstimateError::NonPositiveSemidefiniteCovariance,
                     "negative-eigenvalue covariance was accepted");
    });

    run("bounded_values_are_enforced_without_acceptance_thresholds", [] {
        auto value = estimate();
        value.observability = 1.01;
        requireError(value, alignment::AlignmentEstimateError::InvalidObservability,
                     "out-of-range observability was accepted");
        value = estimate();
        value.slip_probability = -0.01;
        requireError(value, alignment::AlignmentEstimateError::InvalidSlipProbability,
                     "out-of-range slip probability was accepted");
        value = estimate();
        value.observability = 0.0;
        value.slip_probability = std::nullopt;
        require(alignment::validateAlignmentEstimate(value).valid(),
                "structural validation invented a scientific threshold");
    });

    run("status_and_epoch_are_validated", [] {
        auto value = estimate();
        value.epoch_ns = -1;
        requireError(value, alignment::AlignmentEstimateError::NegativeEpoch,
                     "negative epoch was accepted");
        value = estimate();
        value.status = static_cast<contracts::AlignmentStatusV1>(255);
        requireError(value, alignment::AlignmentEstimateError::UnknownStatus,
                     "unknown alignment state was accepted");
    });

    run("provenance_must_be_complete_and_unique", [] {
        auto value = estimate();
        value.method_id.clear();
        requireError(value, alignment::AlignmentEstimateError::MissingMethodId,
                     "missing method identity was accepted");
        value = estimate();
        value.evidence_ids.clear();
        requireError(value, alignment::AlignmentEstimateError::MissingEvidenceId,
                     "missing evidence identity was accepted");
        value.evidence_ids = {"same", "same"};
        requireError(value, alignment::AlignmentEstimateError::DuplicateEvidenceId,
                     "duplicate evidence identity was accepted");
        value = estimate();
        value.config_id.clear();
        requireError(value, alignment::AlignmentEstimateError::MissingConfigId,
                     "missing configuration identity was accepted");
    });

    run("publisher_rejects_sequence_regression_without_overwrite", [] {
        alignment::AlignmentEstimatePublisher publisher;
        const auto accepted = estimate();
        require(publisher.publish(accepted).accepted, "initial posterior was rejected");
        require(publisher.dependentAidsEligible(), "accepted VALID state was not eligible");

        auto stale = accepted;
        stale.epoch_ns += 1;
        stale.evidence_ids = {"newer-evidence"};
        const auto result = publisher.publish(stale);
        require(!result.accepted
                    && result.error == alignment::AlignmentEstimateError::SequenceNotIncreasing,
                "duplicate sequence was accepted");
        require(publisher.latest()->evidence_ids == accepted.evidence_ids,
                "rejected sequence overwrote the accepted posterior");
        require(!publisher.dependentAidsEligible(),
                "rejected publication did not fail the aid gate closed");
    });

    run("publisher_rejects_epoch_regression_without_overwrite", [] {
        alignment::AlignmentEstimatePublisher publisher;
        const auto accepted = estimate();
        require(publisher.publish(accepted).accepted, "initial posterior was rejected");
        auto regressed = accepted;
        ++regressed.sequence;
        --regressed.epoch_ns;
        regressed.evidence_ids = {"later-sequence-older-epoch"};
        const auto result = publisher.publish(regressed);
        require(!result.accepted
                    && result.error == alignment::AlignmentEstimateError::EpochRegressed,
                "regressed epoch was accepted");
        require(publisher.latest()->epoch_ns == accepted.epoch_ns,
                "regressed epoch overwrote the accepted posterior");
    });

    run("publisher_accepts_same_epoch_state_transition", [] {
        alignment::AlignmentEstimatePublisher publisher;
        auto first = estimate(contracts::AlignmentStatusV1::UNINITIALIZED);
        require(publisher.publish(first).accepted, "initial state was rejected");
        auto uncertain = first;
        ++uncertain.sequence;
        uncertain.status = contracts::AlignmentStatusV1::UNCERTAIN;
        uncertain.evidence_ids = {"quality-reassessment"};
        require(publisher.publish(uncertain).accepted,
                "same-epoch state transition was rejected");
        require(!publisher.dependentAidsEligible(),
                "UNCERTAIN transition enabled dependent aids");
    });

    run("slip_publication_disables_dependent_aids_atomically", [] {
        alignment::AlignmentEstimatePublisher publisher;
        auto valid = estimate();
        require(publisher.publish(valid).accepted, "VALID state was rejected");
        require(publisher.dependentAidsEligible(), "VALID state was not eligible");

        auto slip = valid;
        ++slip.sequence;
        ++slip.epoch_ns;
        slip.status = contracts::AlignmentStatusV1::SLIP_SUSPECTED;
        slip.evidence_ids = {"mount-slip-decision"};
        require(publisher.publish(slip).accepted, "slip state was rejected");
        require(!publisher.dependentAidsEligible(),
                "accepted slip state did not atomically disable dependent aids");
        require(publisher.latest()->status
                    == contracts::AlignmentStatusV1::SLIP_SUSPECTED,
                "slip state was not the latest accepted posterior");
    });

    run("post_slip_recovery_requires_new_evidence_identity", [] {
        alignment::AlignmentEstimatePublisher publisher;
        auto slip = estimate(contracts::AlignmentStatusV1::SLIP_SUSPECTED);
        require(publisher.publish(slip).accepted, "slip state was rejected");

        auto replayed = slip;
        ++replayed.sequence;
        ++replayed.epoch_ns;
        replayed.status = contracts::AlignmentStatusV1::VALID;
        const auto rejected = publisher.publish(replayed);
        require(!rejected.accepted
                    && rejected.error
                        == alignment::AlignmentEstimateError::MissingRecoveryEvidence,
                "pre-slip evidence was reused for recovery");
        require(publisher.latest()->status
                    == contracts::AlignmentStatusV1::SLIP_SUSPECTED,
                "rejected recovery overwrote the slip state");

        replayed.evidence_ids.push_back("post-slip-realignment");
        require(publisher.publish(replayed).accepted,
                "recovery with new evidence identity was rejected");
        require(publisher.dependentAidsEligible(),
                "valid post-slip recovery did not restore eligibility");
    });

    run("post_slip_recovery_latch_survives_intermediate_state", [] {
        alignment::AlignmentEstimatePublisher publisher;
        auto slip = estimate(contracts::AlignmentStatusV1::SLIP_SUSPECTED);
        require(publisher.publish(slip).accepted, "slip state was rejected");

        auto uncertain = slip;
        ++uncertain.sequence;
        ++uncertain.epoch_ns;
        uncertain.status = contracts::AlignmentStatusV1::UNCERTAIN;
        uncertain.evidence_ids = {"uncertain-assessment"};
        require(publisher.publish(uncertain).accepted,
                "intermediate UNCERTAIN state was rejected");

        auto replayed = uncertain;
        ++replayed.sequence;
        ++replayed.epoch_ns;
        replayed.status = contracts::AlignmentStatusV1::VALID;
        const auto rejected = publisher.publish(replayed);
        require(!rejected.accepted
                    && rejected.error
                        == alignment::AlignmentEstimateError::MissingRecoveryEvidence,
                "intermediate state cleared the slip-recovery evidence latch");
        require(publisher.latest()->status
                    == contracts::AlignmentStatusV1::UNCERTAIN,
                "rejected recovery overwrote the intermediate state");
        require(!publisher.dependentAidsEligible(),
                "rejected indirect recovery enabled dependent aids");

        replayed.evidence_ids.push_back("post-slip-realignment");
        require(publisher.publish(replayed).accepted,
                "indirect recovery with new evidence identity was rejected");
        require(publisher.dependentAidsEligible(),
                "indirect valid recovery did not restore eligibility");
    });

    run("repeated_slip_extends_recovery_evidence_barrier", [] {
        alignment::AlignmentEstimatePublisher publisher;
        auto first_slip = estimate(contracts::AlignmentStatusV1::SLIP_SUSPECTED);
        first_slip.evidence_ids = {"mount-slip-a"};
        require(publisher.publish(first_slip).accepted,
                "first slip state was rejected");

        auto second_slip = first_slip;
        ++second_slip.sequence;
        ++second_slip.epoch_ns;
        second_slip.evidence_ids = {"mount-slip-b"};
        require(publisher.publish(second_slip).accepted,
                "second slip state was rejected");

        auto replayed = second_slip;
        ++replayed.sequence;
        ++replayed.epoch_ns;
        replayed.status = contracts::AlignmentStatusV1::VALID;
        const auto rejected = publisher.publish(replayed);
        require(!rejected.accepted
                    && rejected.error
                        == alignment::AlignmentEstimateError::MissingRecoveryEvidence,
                "latest slip evidence was reused for recovery");
        require(publisher.latest()->status
                    == contracts::AlignmentStatusV1::SLIP_SUSPECTED
                    && publisher.latest()->evidence_ids
                        == second_slip.evidence_ids,
                "rejected recovery overwrote the latest slip state");
        require(!publisher.dependentAidsEligible(),
                "repeated-slip recovery bypass enabled dependent aids");

        replayed.evidence_ids.push_back("post-slip-realignment");
        require(publisher.publish(replayed).accepted,
                "repeated-slip recovery with unseen evidence was rejected");
        require(publisher.dependentAidsEligible(),
                "repeated-slip recovery did not restore eligibility");
    });

    run("malformed_publication_fails_closed_and_can_recover", [] {
        alignment::AlignmentEstimatePublisher publisher;
        auto first = estimate();
        require(publisher.publish(first).accepted, "initial posterior was rejected");
        auto malformed = first;
        ++malformed.sequence;
        malformed.epoch_ns += 1;
        malformed.covariance_3x3[8] = -1.0;
        require(!publisher.publish(malformed).accepted,
                "malformed posterior was accepted");
        require(!publisher.dependentAidsEligible(),
                "malformed input left dependent aids eligible");

        auto recovered = first;
        recovered.sequence += 2;
        recovered.epoch_ns += 2;
        recovered.evidence_ids = {"recovered-estimate"};
        require(publisher.publish(recovered).accepted,
                "new valid posterior did not recover publisher health");
        require(publisher.dependentAidsEligible(),
                "publisher health recovered without restoring eligibility");
    });

    run("failure_codes_have_stable_strings", [] {
        require(std::string(alignment::toString(
                    alignment::AlignmentEstimateError::MissingRecoveryEvidence))
                    == "missing_recovery_evidence",
                "recovery failure string changed");
        require(std::string(alignment::toString(
                    alignment::AlignmentEstimateError::NonPositiveSemidefiniteCovariance))
                    == "non_positive_semidefinite_covariance",
                "covariance failure string changed");
    });

    std::cout << "RESULT " << (total - failures) << '/' << total << " tests passed\n";
    return failures == 0 ? 0 : 1;
}
