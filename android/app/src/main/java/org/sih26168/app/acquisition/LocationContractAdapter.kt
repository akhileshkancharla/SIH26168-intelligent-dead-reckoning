package org.sih26168.app.acquisition

import android.location.Location
import android.location.LocationListener
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import java.util.Collections
import java.util.UUID
import org.sih26168.app.ingress.NavigationIngress
import org.sih26168.app.ingress.NavigationIngressEvent
import org.sih26168.app.ingress.NavigationIngressResult
import org.sih26168.contracts.enums.DisplayModeV1
import org.sih26168.contracts.enums.ProvenanceTypeV1
import org.sih26168.contracts.models.EvidenceEnvelopeV1
import org.sih26168.contracts.models.ProvenanceV1
import org.sih26168.contracts.models.TimestampV1
import org.sih26168.contracts.models.ValidityGateV1

/** Presence flags have already been applied; missing values remain null, never zero-filled. */
data class LocationCallbackSnapshot(
    val provider: String?,
    val sourceTimestampNs: Long,
    val arrivalTimestampNs: Long,
    val latitudeDegrees: Double,
    val longitudeDegrees: Double,
    val horizontalAccuracyMeters: Double?,
    val isMock: Boolean,
    val altitudeMeters: Double? = null,
    val verticalAccuracyMeters: Double? = null,
    val speedMetersPerSecond: Double? = null,
    val speedAccuracyMetersPerSecond: Double? = null,
    val bearingDegrees: Double? = null,
    val bearingAccuracyDegrees: Double? = null,
    val wallClockMsAuxiliary: Long? = null,
)

fun interface LocationEvidenceRecorder {
    fun record(event: NavigationIngressEvent<Map<String, Any?>>)
}

/** I-02 source adaptation only. C-09/C-07 retain all integrity/acceptance authority. */
class LocationContractAdapter(
    private val sessionId: String,
    private val recorder: LocationEvidenceRecorder,
    private val ingress: NavigationIngress,
) {
    private val sequences = mutableMapOf<String, Long>()
    private val latestSourceNs = mutableMapOf<String, Long>()
    private var publishing = false

    init {
        require(sessionId.isNotBlank())
        require(ingress.sourceMode == DisplayModeV1.LIVE_DEVICE)
    }

    @Synchronized
    fun accept(snapshot: LocationCallbackSnapshot): NavigationIngressResult? {
        check(!publishing) { "Reentrant acquisition publication" }
        // Missing provider has its own namespace; no literal provider can alias it.
        val stream = snapshot.provider?.let { "location:provider:${it.length}:$it" }
            ?: "location:null"
        val sequence = sequences[stream] ?: 0L
        check(sequence < Long.MAX_VALUE) { "Location sequence exhausted; stop the session" }
        sequences[stream] = sequence + 1L
        val evidenceId = UUID.randomUUID().toString()
        val measurements = linkedMapOf(
            "alt_m" to snapshot.altitudeMeters,
            "vacc_m" to snapshot.verticalAccuracyMeters,
            "speed_mps" to snapshot.speedMetersPerSecond,
            "speed_acc_mps" to snapshot.speedAccuracyMetersPerSecond,
            "bearing_deg" to snapshot.bearingDegrees,
            "bearing_acc_deg" to snapshot.bearingAccuracyDegrees,
        )
        val finite = (measurements.values + listOf(snapshot.latitudeDegrees,
            snapshot.longitudeDegrees, snapshot.horizontalAccuracyMeters)).all {
            it == null || it.isFinite()
        }
        val previousNs = latestSourceNs[stream]
        val reason = when {
            snapshot.provider.isNullOrBlank() -> "MISSING_LOCATION_PROVIDER"
            snapshot.sourceTimestampNs < 0L || snapshot.arrivalTimestampNs < snapshot.sourceTimestampNs ->
                "INVALID_LOCATION_TIME"
            previousNs != null && snapshot.sourceTimestampNs <= previousNs ->
                "NON_INCREASING_LOCATION_TIME"
            !finite -> "NON_FINITE_LOCATION_VALUE"
            snapshot.latitudeDegrees !in -90.0..90.0 || snapshot.longitudeDegrees !in -180.0..180.0 ->
                "INVALID_LOCATION_COORDINATE"
            snapshot.horizontalAccuracyMeters == null || snapshot.horizontalAccuracyMeters < 0.1 ->
                "INVALID_HORIZONTAL_ACCURACY"
            snapshot.verticalAccuracyMeters?.let { it < 0.0 } == true ||
                snapshot.speedAccuracyMetersPerSecond?.let { it < 0.0 } == true ||
                snapshot.speedMetersPerSecond?.let { it !in 0.0..100.0 } == true ||
                snapshot.bearingDegrees?.let { it < 0.0 || it >= 360.0 } == true ||
                snapshot.bearingAccuracyDegrees?.let { it !in 0.0..180.0 } == true ->
                "INVALID_LOCATION_MEASUREMENT"
            else -> null
        }
        if (snapshot.sourceTimestampNs >= 0L &&
            (previousNs == null || snapshot.sourceTimestampNs > previousNs)) {
            latestSourceNs[stream] = snapshot.sourceTimestampNs
        }
        val fields = linkedMapOf<String, Any?>(
            "schema_version" to 1,
            "evidence_id" to evidenceId,
            "provider" to snapshot.provider,
            "source_timestamp_ns" to snapshot.sourceTimestampNs,
            "arrival_elapsed_realtime_ns" to snapshot.arrivalTimestampNs,
            "lat_deg" to snapshot.latitudeDegrees,
            "lon_deg" to snapshot.longitudeDegrees,
            "hacc_m" to snapshot.horizontalAccuracyMeters,
            "is_mock" to snapshot.isMock,
            "field_mask" to Collections.unmodifiableList(measurements.filterValues { it != null }.keys.toList()),
            "source_wall_clock_ms_auxiliary" to snapshot.wallClockMsAuxiliary,
        )
        fields.putAll(measurements)
        val event: NavigationIngressEvent<Map<String, Any?>> = NavigationIngressEvent(sequence, EvidenceEnvelopeV1(
            payloadType = "LocationGnssFix",
            timestamp = TimestampV1(snapshot.sourceTimestampNs, snapshot.arrivalTimestampNs,
                "android.elapsed_realtime_ns", snapshot.sourceTimestampNs),
            provenance = ProvenanceV1(evidenceId, sessionId, stream, ProvenanceTypeV1.LIVE_DEVICE),
            payload = Collections.unmodifiableMap(fields),
            validityGate = ValidityGateV1(finite, reason == null, reason),
        ))
        publishing = true
        try {
            recorder.record(event)
            return if (reason == null) ingress.submit(event) else null
        } finally {
            publishing = false
        }
    }
}

/** The session owner registers this listener and owns permission/provider/service lifetime. */
class ContractLocationListener(
    private val adapter: LocationContractAdapter,
    private val onProviderState: (String, Boolean) -> Unit,
    private val onLegacyStatus: (String?, Int, Bundle?) -> Unit,
) : LocationListener {
    override fun onLocationChanged(location: Location) {
        val arrival = SystemClock.elapsedRealtimeNanos()
        adapter.accept(LocationCallbackSnapshot(
            provider = location.provider,
            sourceTimestampNs = location.elapsedRealtimeNanos,
            arrivalTimestampNs = arrival,
            latitudeDegrees = location.latitude,
            longitudeDegrees = location.longitude,
            horizontalAccuracyMeters = if (location.hasAccuracy()) location.accuracy.toDouble() else null,
            isMock = if (Build.VERSION.SDK_INT >= 31) location.isMock else
                @Suppress("DEPRECATION") location.isFromMockProvider,
            altitudeMeters = if (location.hasAltitude()) location.altitude else null,
            verticalAccuracyMeters = if (location.hasVerticalAccuracy()) location.verticalAccuracyMeters.toDouble() else null,
            speedMetersPerSecond = if (location.hasSpeed()) location.speed.toDouble() else null,
            speedAccuracyMetersPerSecond = if (location.hasSpeedAccuracy()) location.speedAccuracyMetersPerSecond.toDouble() else null,
            bearingDegrees = if (location.hasBearing()) location.bearing.toDouble() else null,
            bearingAccuracyDegrees = if (location.hasBearingAccuracy()) location.bearingAccuracyDegrees.toDouble() else null,
            wallClockMsAuxiliary = location.time,
        ))
    }
    @Suppress("OVERRIDE_DEPRECATION")
    override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) =
        onLegacyStatus(provider, status, extras?.let { Bundle(it) })

    override fun onProviderEnabled(provider: String) = onProviderState(provider, true)
    override fun onProviderDisabled(provider: String) = onProviderState(provider, false)
}
