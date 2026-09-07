package org.sih26168.contracts
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.sih26168.contracts.enums.ProvenanceTypeV1
import org.sih26168.contracts.models.EvidenceEnvelopeV1
import org.sih26168.contracts.models.ProvenanceV1
import org.sih26168.contracts.models.TimestampV1
import org.sih26168.contracts.models.ValidityGateV1

// WP-01.5 (Issue #29): exercises the placed Kotlin bindings
// (android/app/src/main/java/org/sih26168/contracts/) from real Android
// test code, proving they're usable from the consuming app module.
class ContractsModelsSmokeTest {
    @Test
    fun evidenceEnvelopeCarriesATypedPayload() {
        val timestamp = TimestampV1(
            epochNs = 3456789000000L,
            arrivalElapsedRealtimeNs = 3456789000000L,
            clockId = "CLOCK_BOOTTIME"
        )
        val provenance = ProvenanceV1(
            evidenceId = "ev-001",
            sessionId = "sess-001",
            streamId = "sensor_accel",
            // provenanceType has no schema default and is required.
            provenanceType = ProvenanceTypeV1.LIVE_DEVICE
        )
        val envelope = EvidenceEnvelopeV1(
            payloadType = "RawSensorSample",
            timestamp = timestamp,
            provenance = provenance,
            payload = doubleArrayOf(0.012, -0.034, 9.80665),
            // isFinite/isValid are required fields with no schema default,
            // so the generated data class requires them explicitly rather
            // than silently defaulting to true.
            validityGate = ValidityGateV1(isFinite = true, isValid = true)
        )

        assertEquals(1L, envelope.schemaVersion)
        assertEquals("RawSensorSample", envelope.payloadType)
        assertEquals(ProvenanceTypeV1.LIVE_DEVICE, envelope.provenance.provenanceType)
        assertTrue(envelope.validityGate.isFinite)
        assertEquals(9.80665, envelope.payload[2], 1e-9)
    }
}
