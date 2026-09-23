package org.sih26168.app.ingress

import org.sih26168.contracts.enums.DisplayModeV1
import org.sih26168.contracts.enums.ProvenanceTypeV1
import org.sih26168.contracts.models.EvidenceEnvelopeV1

/** An I-01 or I-02 observation presented to the common downstream pipeline. */
data class NavigationIngressEvent<T>(
    val sequence: Long,
    val envelope: EvidenceEnvelopeV1<T>,
)

/**
 * Consumer boundary shared by live acquisition and deterministic replay.
 *
 * The event is passed through unchanged. The consumer, rather than this adapter, owns contract
 * validation and all scientific state transitions.
 */
fun interface NavigationIngressSink {
    fun accept(event: NavigationIngressEvent<*>)
}

enum class NavigationIngressRejectionReason {
    UNSUPPORTED_PAYLOAD_TYPE,
    SOURCE_MODE_MISMATCH,
    NEGATIVE_SEQUENCE,
    DUPLICATE_EVIDENCE_ID,
    NON_INCREASING_STREAM_SEQUENCE,
}

sealed interface NavigationIngressResult {
    data class Accepted(
        val evidenceId: String,
    ) : NavigationIngressResult

    data class Rejected(
        val reason: NavigationIngressRejectionReason,
    ) : NavigationIngressResult
}

/** Source adapter contract used identically by C-01 live acquisition and C-12 replay. */
interface NavigationIngress {
    val sourceMode: DisplayModeV1

    fun <T> submit(event: NavigationIngressEvent<T>): NavigationIngressResult
}

/**
 * Fail-closed source boundary for the shared I-01/I-02 ingress path.
 *
 * This class does not translate, copy, reorder, or repair observations. It verifies only the
 * properties needed to keep live and replay sources honest at their common boundary, then passes
 * the original event instance to [sink]. Schema validation remains the responsibility of C-20.
 */
class SourceBoundNavigationIngress(
    override val sourceMode: DisplayModeV1,
    private val sink: NavigationIngressSink,
) : NavigationIngress {
    private val consumedEvidenceIds = mutableSetOf<String>()
    private val lastSequenceByStream = mutableMapOf<String, Long>()

    @Synchronized
    override fun <T> submit(event: NavigationIngressEvent<T>): NavigationIngressResult {
        val envelope = event.envelope
        val rejection = when {
            envelope.payloadType !in SUPPORTED_PAYLOAD_TYPES ->
                NavigationIngressRejectionReason.UNSUPPORTED_PAYLOAD_TYPE
            !sourceMode.accepts(envelope.provenance.provenanceType) ->
                NavigationIngressRejectionReason.SOURCE_MODE_MISMATCH
            event.sequence < 0L ->
                NavigationIngressRejectionReason.NEGATIVE_SEQUENCE
            envelope.provenance.evidenceId in consumedEvidenceIds ->
                NavigationIngressRejectionReason.DUPLICATE_EVIDENCE_ID
            lastSequenceByStream[envelope.provenance.streamId]
                ?.let { event.sequence <= it } == true ->
                NavigationIngressRejectionReason.NON_INCREASING_STREAM_SEQUENCE
            else -> null
        }

        if (rejection != null) {
            return NavigationIngressResult.Rejected(rejection)
        }

        sink.accept(event)
        consumedEvidenceIds += envelope.provenance.evidenceId
        lastSequenceByStream[envelope.provenance.streamId] = event.sequence
        return NavigationIngressResult.Accepted(envelope.provenance.evidenceId)
    }

    private fun DisplayModeV1.accepts(provenance: ProvenanceTypeV1): Boolean = when (this) {
        DisplayModeV1.LIVE_DEVICE ->
            provenance == ProvenanceTypeV1.LIVE_DEVICE || provenance == ProvenanceTypeV1.LIVE
        DisplayModeV1.DETERMINISTIC_REPLAY ->
            provenance == ProvenanceTypeV1.DETERMINISTIC_REPLAY || provenance == ProvenanceTypeV1.REPLAY
    }

    private companion object {
        val SUPPORTED_PAYLOAD_TYPES = setOf("RawSensorSample", "LocationGnssFix")
    }
}
