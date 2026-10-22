package org.sih26168.app.acquisition

import org.junit.Assert.*
import org.junit.Test
import org.sih26168.app.ingress.*
import org.sih26168.contracts.enums.DisplayModeV1
import org.sih26168.contracts.enums.ProvenanceTypeV1

class SensorContractAdapterTest {
    private val retained = mutableListOf<NavigationIngressEvent<Map<String, Any?>>>()
    private val delivered = mutableListOf<NavigationIngressEvent<*>>()
    private fun adapter(recorder: SensorEvidenceRecorder = SensorEvidenceRecorder { retained.add(it) }) =
        SensorContractAdapter("session", recorder,
            SourceBoundNavigationIngress(DisplayModeV1.LIVE_DEVICE) { delivered.add(it) })
    private fun sample(id: Int = 1, time: Long = 100L, type: Int = 1,
        values: FloatArray = floatArrayOf(1f, -2f, 9.8f)) =
        SensorCallbackSnapshot(id, type, "sensor", "vendor", 1, time, time + 20L, values, 3)

    @Test fun preservesCallbackValuesTimingAndImmutableIdentity() {
        val source = sample()
        assertTrue(adapter().accept(source) is NavigationIngressResult.Accepted)
        val event = retained.single()
        assertSame(event, delivered.single())
        assertEquals(ProvenanceTypeV1.LIVE_DEVICE, event.envelope.provenance.provenanceType)
        assertEquals(100L, event.envelope.timestamp.epochNs)
        assertEquals(120L, event.envelope.timestamp.arrivalElapsedRealtimeNs)
        assertEquals(event.envelope.provenance.evidenceId, event.envelope.payload["evidence_id"])
        source.values[0] = 999f
        val values = event.envelope.payload["values"] as List<*>
        assertEquals(1.0, values[0])
        assertThrows(UnsupportedOperationException::class.java) {
            @Suppress("UNCHECKED_CAST")
            (values as MutableList<Any?>).clear()
        }
    }

    @Test fun duplicateAndReorderedTimesAreRetainedButNotDelivered() {
        val adapter = adapter()
        adapter.accept(sample(time = 100L))
        assertNull(adapter.accept(sample(time = 100L)))
        assertNull(adapter.accept(sample(time = 99L)))
        adapter.accept(sample(time = 101L))
        assertEquals(listOf(0L, 1L, 2L, 3L), retained.map { it.sequence })
        assertEquals(listOf(0L, 3L), delivered.map { it.sequence })
        assertEquals("NON_INCREASING_SENSOR_TIME", retained[1].envelope.validityGate.rejectionCode)
        assertEquals(4, retained.map { it.envelope.provenance.evidenceId }.toSet().size)
    }

    @Test fun streamsHaveIndependentSequencesAndSourceClocks() {
        val adapter = adapter()
        adapter.accept(sample(id = 1, time = 500L))
        adapter.accept(sample(id = 2, time = 100L, type = 4))
        assertEquals(listOf(0L, 0L), delivered.map { it.sequence })
        assertEquals(2, delivered.map { it.envelope.provenance.streamId }.toSet().size)
    }

    @Test fun unavailableHardwareIdsDoNotMergeAccelerometerAndGyroscopeStreams() {
        val adapter = adapter()
        adapter.accept(sample(id = 0, time = 500L, type = 1))
        adapter.accept(sample(id = 0, time = 100L, type = 4))
        assertEquals(listOf(0L, 0L), delivered.map { it.sequence })
        assertEquals(2, delivered.map { it.envelope.provenance.streamId }.toSet().size)
    }

    @Test fun fallbackIdsSeparateSameTypeSensorsByNameWithoutDelimiterCollisions() {
        val adapter = adapter()
        adapter.accept(sample(id = -1, time = 500L).copy(name = "a:b", vendor = "c"))
        adapter.accept(sample(id = -1, time = 100L).copy(name = "a", vendor = "b:c"))
        assertEquals(listOf(0L, 0L), delivered.map { it.sequence })
        assertEquals(2, delivered.map { it.envelope.provenance.streamId }.toSet().size)
    }

    @Test fun invalidShapesMetadataAndTimeNeverReachRuntime() {
        val cases = listOf(sample(type = 16), sample(values = floatArrayOf(1f)),
            sample(values = floatArrayOf(Float.NaN, 0f, 0f)), sample().copy(accuracy = -1),
            sample().copy(name = ""), sample().copy(version = 0),
            sample().copy(arrivalTimestampNs = 99L), sample(time = -1L))
        for (source in cases) {
            retained.clear()
            assertNull(adapter().accept(source))
            assertFalse(retained.single().envelope.validityGate.isValid)
            assertNotNull(retained.single().envelope.validityGate.rejectionCode)
        }
        assertTrue(delivered.isEmpty())
    }

    @Test fun temperatureIsOneValueAndRecorderFailureStopsRuntimeDelivery() {
        adapter().accept(sample(type = 13, values = floatArrayOf(24f)))
        assertEquals("AMBIENT_TEMPERATURE", retained.single().envelope.payload["sensor_type"])
        delivered.clear()
        assertThrows(IllegalStateException::class.java) {
            adapter(SensorEvidenceRecorder { error("storage failed") }).accept(sample())
        }
        assertTrue(delivered.isEmpty())
    }
}
