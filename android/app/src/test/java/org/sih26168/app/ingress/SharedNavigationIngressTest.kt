package org.sih26168.app.ingress

import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test
import org.sih26168.contracts.enums.DisplayModeV1
import org.sih26168.contracts.enums.ProvenanceTypeV1
import org.sih26168.contracts.models.EvidenceEnvelopeV1
import org.sih26168.contracts.models.ProvenanceV1
import org.sih26168.contracts.models.TimestampV1
import org.sih26168.contracts.models.ValidityGateV1

class SharedNavigationIngressTest {
    @Test
    fun liveAndReplay_forwardTheSameContractWithoutRewritingIt() {
        val liveEvent = event(
            evidenceId = "live-1",
            provenance = ProvenanceTypeV1.LIVE_DEVICE,
            payload = TestPayload(1.0),
        )
        val replayEvent = event(
            evidenceId = "replay-1",
            provenance = ProvenanceTypeV1.DETERMINISTIC_REPLAY,
            payload = TestPayload(1.0),
        )
        val forwarded = mutableListOf<NavigationIngressEvent<*>>()

        val live = SourceBoundNavigationIngress(DisplayModeV1.LIVE_DEVICE) { forwarded += it }
        val replay = SourceBoundNavigationIngress(DisplayModeV1.DETERMINISTIC_REPLAY) {
            forwarded += it
        }

        assertAccepted(live.submit(liveEvent), "live-1")
        assertAccepted(replay.submit(replayEvent), "replay-1")
        assertSame(liveEvent, forwarded[0])
        assertSame(replayEvent, forwarded[1])
        assertEquals(liveEvent.envelope.payloadType, replayEvent.envelope.payloadType)
        assertEquals(liveEvent.envelope.payload, replayEvent.envelope.payload)
    }

    @Test
    fun sourceMismatch_isRejectedWithoutReachingTheConsumer() {
        val forwarded = mutableListOf<NavigationIngressEvent<*>>()
        val ingress = SourceBoundNavigationIngress(DisplayModeV1.LIVE_DEVICE) { forwarded += it }

        val result = ingress.submit(
            event(evidenceId = "replay-1", provenance = ProvenanceTypeV1.REPLAY),
        )

        assertRejected(result, NavigationIngressRejectionReason.SOURCE_MODE_MISMATCH)
        assertTrue(forwarded.isEmpty())
    }

    @Test
    fun onlyLiveCompatibleI01AndI02Payloads_areAccepted() {
        val forwarded = mutableListOf<NavigationIngressEvent<*>>()
        val ingress = SourceBoundNavigationIngress(DisplayModeV1.LIVE_DEVICE) { forwarded += it }

        assertAccepted(ingress.submit(event(evidenceId = "imu-1")), "imu-1")
        assertAccepted(
            ingress.submit(event(evidenceId = "gnss-1", payloadType = "LocationGnssFix", sequence = 2L)),
            "gnss-1",
        )
        assertRejected(
            ingress.submit(event(evidenceId = "ui-1", payloadType = "UiNavigationSnapshot", sequence = 3L)),
            NavigationIngressRejectionReason.UNSUPPORTED_PAYLOAD_TYPE,
        )
        assertEquals(2, forwarded.size)
    }

    @Test
    fun duplicateEvidence_isRejectedAcrossStreams() {
        val ingress = SourceBoundNavigationIngress(DisplayModeV1.LIVE_DEVICE) {}

        assertAccepted(ingress.submit(event(evidenceId = "same")), "same")
        assertRejected(
            ingress.submit(event(evidenceId = "same", streamId = "gnss", sequence = 1L)),
            NavigationIngressRejectionReason.DUPLICATE_EVIDENCE_ID,
        )
    }

    @Test
    fun sequenceMustIncreaseWithinEachStream_butStreamsRemainIndependent() {
        val ingress = SourceBoundNavigationIngress(DisplayModeV1.LIVE_DEVICE) {}

        assertAccepted(ingress.submit(event(evidenceId = "imu-5", sequence = 5L)), "imu-5")
        assertAccepted(
            ingress.submit(event(evidenceId = "gnss-5", streamId = "gnss", sequence = 5L)),
            "gnss-5",
        )
        assertRejected(
            ingress.submit(event(evidenceId = "imu-4", sequence = 4L)),
            NavigationIngressRejectionReason.NON_INCREASING_STREAM_SEQUENCE,
        )
    }

    @Test
    fun consumerFailure_doesNotConsumeEvidenceOrAdvanceSequence() {
        var fail = true
        val ingress = SourceBoundNavigationIngress(DisplayModeV1.LIVE_DEVICE) {
            if (fail) error("downstream unavailable")
        }
        val event = event(evidenceId = "imu-1")

        try {
            ingress.submit(event)
            throw AssertionError("consumer failure should propagate")
        } catch (expected: IllegalStateException) {
            assertEquals("downstream unavailable", expected.message)
        }

        fail = false
        assertAccepted(ingress.submit(event), "imu-1")
    }

    private fun event(
        evidenceId: String,
        provenance: ProvenanceTypeV1 = ProvenanceTypeV1.LIVE_DEVICE,
        payloadType: String = "RawSensorSample",
        streamId: String = "imu",
        sequence: Long = 1L,
        payload: TestPayload = TestPayload(0.0),
    ): NavigationIngressEvent<TestPayload> = NavigationIngressEvent(
        sequence = sequence,
        envelope = EvidenceEnvelopeV1(
            payloadType = payloadType,
            timestamp = TimestampV1(
                epochNs = 100L,
                arrivalElapsedRealtimeNs = 101L,
                clockId = "clock-1",
                sourceTimestampNs = 99L,
            ),
            provenance = ProvenanceV1(
                evidenceId = evidenceId,
                sessionId = "session-1",
                streamId = streamId,
                provenanceType = provenance,
            ),
            payload = payload,
            validityGate = ValidityGateV1(isFinite = true, isValid = true),
        ),
    )

    private fun assertAccepted(result: NavigationIngressResult, evidenceId: String) {
        val accepted = result as? NavigationIngressResult.Accepted
            ?: throw AssertionError("expected accepted result, got $result")
        assertEquals(evidenceId, accepted.evidenceId)
    }

    private fun assertRejected(
        result: NavigationIngressResult,
        reason: NavigationIngressRejectionReason,
    ) {
        val rejected = result as? NavigationIngressResult.Rejected
            ?: throw AssertionError("expected rejected result, got $result")
        assertEquals(reason, rejected.reason)
    }

    private data class TestPayload(val value: Double)
}
