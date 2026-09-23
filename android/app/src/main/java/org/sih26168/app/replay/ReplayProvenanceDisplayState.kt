package org.sih26168.app.replay

import org.sih26168.app.ingress.NavigationIngressEvent
import org.sih26168.contracts.enums.DisplayModeV1
import org.sih26168.contracts.enums.ProvenanceTypeV1

/**
 * Mandatory replay-mode disclosure plus the immutable origin of the latest accepted evidence.
 *
 * [displayMode] and [replayLabel] describe how the application is currently operating. They are
 * deliberately independent from [evidenceOrigin], which continues to identify where recorded
 * evidence originally came from and must never be relabelled merely because it is replayed.
 */
data class ReplayProvenanceDisplayState(
    val evidenceId: String? = null,
    val sessionId: String? = null,
    val streamId: String? = null,
    val streamSequence: Long? = null,
    val evidenceEpochNs: Long? = null,
    val evidenceOrigin: ProvenanceTypeV1? = null,
) {
    val displayMode: DisplayModeV1
        get() = DisplayModeV1.DETERMINISTIC_REPLAY

    val replayLabel: String
        get() = "REPLAY"

    val sourceLabel: String
        get() = "SOURCE: ${displayMode.name}"

    val evidenceOriginLabel: String
        get() = "EVIDENCE ORIGIN: ${evidenceOrigin?.name ?: "UNAVAILABLE"}"

    companion object {
        fun fromAcceptedIngress(
            event: NavigationIngressEvent<*>,
        ): ReplayProvenanceDisplayState? {
            val envelope = event.envelope
            val provenance = envelope.provenance
            if (
                event.sequence < 0L ||
                envelope.timestamp.epochNs < 0L ||
                provenance.evidenceId.isBlank() ||
                provenance.sessionId.isBlank() ||
                provenance.streamId.isBlank()
            ) {
                return null
            }
            return ReplayProvenanceDisplayState(
                evidenceId = provenance.evidenceId,
                sessionId = provenance.sessionId,
                streamId = provenance.streamId,
                streamSequence = event.sequence,
                evidenceEpochNs = envelope.timestamp.epochNs,
                evidenceOrigin = provenance.provenanceType,
            )
        }
    }
}
