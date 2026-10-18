package org.sih26168.app.acquisition

import org.junit.Assert.*
import org.junit.Test
import org.sih26168.app.ingress.*
import org.sih26168.contracts.enums.DisplayModeV1

class LocationContractAdapterTest {
    private val retained = mutableListOf<NavigationIngressEvent<Map<String, Any?>>>()
    private val delivered = mutableListOf<NavigationIngressEvent<*>>()
    private fun adapter(recorder: LocationEvidenceRecorder = LocationEvidenceRecorder { retained.add(it) }) =
        LocationContractAdapter("session", recorder,
            SourceBoundNavigationIngress(DisplayModeV1.LIVE_DEVICE) { delivered.add(it) })
    private fun sample(time: Long = 100L, provider: String? = "gps") =
        LocationCallbackSnapshot(provider, time, time + 20L, 0.0, 0.0, 1.0, false)

    @Test fun absenceRemainsNullAndMockProviderAndSourceClockArePreserved() {
        assertTrue(adapter().accept(sample().copy(isMock = true, wallClockMsAuxiliary = 9000L))
            is NavigationIngressResult.Accepted)
        val event = retained.single()
        assertSame(event, delivered.single())
        assertEquals("gps", event.envelope.payload["provider"])
        assertEquals(true, event.envelope.payload["is_mock"])
        assertEquals(100L, event.envelope.timestamp.epochNs)
        assertEquals(120L, event.envelope.timestamp.arrivalElapsedRealtimeNs)
        assertNull(event.envelope.payload["speed_mps"])
        assertEquals(emptyList<String>(), event.envelope.payload["field_mask"])
        assertEquals(event.envelope.provenance.evidenceId, event.envelope.payload["evidence_id"])
    }

    @Test fun optionalZeroValuesArePresentAndSnapshotCollectionsAreImmutable() {
        adapter().accept(sample().copy(altitudeMeters = 0.0, verticalAccuracyMeters = 0.0,
            speedMetersPerSecond = 0.0, speedAccuracyMetersPerSecond = 0.0,
            bearingDegrees = 0.0, bearingAccuracyDegrees = 0.0))
        val payload = retained.single().envelope.payload
        assertEquals(6, (payload["field_mask"] as List<*>).size)
        assertThrows(UnsupportedOperationException::class.java) {
            (payload as MutableMap<String, Any?>).clear()
        }
    }

    @Test fun duplicateAndReorderedSourceTimesAreRetainedWithoutRuntimeDelivery() {
        val adapter = adapter()
        adapter.accept(sample())
        assertNull(adapter.accept(sample()))
        assertNull(adapter.accept(sample(time = 99L)))
        adapter.accept(sample(time = 101L))
        assertEquals(listOf(0L, 3L), delivered.map { it.sequence })
        assertEquals(4, retained.size)
        assertEquals("NON_INCREASING_LOCATION_TIME", retained[1].envelope.validityGate.rejectionCode)
        assertEquals(4, retained.map { it.envelope.provenance.evidenceId }.toSet().size)
    }

    @Test fun providerStreamsRemainSeparateWithoutClaimingGpsProvenance() {
        val adapter = adapter()
        adapter.accept(sample(time = 500L))
        adapter.accept(sample(provider = "network"))
        assertEquals(listOf(0L, 0L), delivered.map { it.sequence })
        assertEquals("network", retained[1].envelope.payload["provider"])
    }

    @Test fun schemaInvalidMeasurementsAndMissingAccuracyAreDiagnosticOnly() {
        val cases = listOf(sample(provider = null), sample(provider = ""),
            sample().copy(latitudeDegrees = 91.0), sample().copy(longitudeDegrees = Double.NaN),
            sample().copy(horizontalAccuracyMeters = null), sample().copy(horizontalAccuracyMeters = 0.0),
            sample().copy(speedMetersPerSecond = 101.0), sample().copy(speedAccuracyMetersPerSecond = -1.0),
            sample().copy(bearingDegrees = 360.0), sample().copy(bearingAccuracyDegrees = 181.0),
            sample().copy(verticalAccuracyMeters = -1.0), sample().copy(altitudeMeters = Double.POSITIVE_INFINITY),
            sample().copy(arrivalTimestampNs = 99L), sample(time = -1L))
        for (source in cases) {
            retained.clear()
            assertNull(adapter().accept(source))
            assertFalse(retained.single().envelope.validityGate.isValid)
            assertNotNull(retained.single().envelope.validityGate.rejectionCode)
        }
        assertTrue(delivered.isEmpty())
    }

    @Test fun retentionFailureStopsPublicationBeforeRuntime() {
        assertThrows(IllegalStateException::class.java) {
            adapter(LocationEvidenceRecorder { error("storage failed") }).accept(sample())
        }
        assertTrue(delivered.isEmpty())
    }
}
