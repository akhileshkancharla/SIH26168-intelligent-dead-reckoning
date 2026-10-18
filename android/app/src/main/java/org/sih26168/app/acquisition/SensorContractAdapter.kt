package org.sih26168.app.acquisition

import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
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

/** A copied Android callback, before any axis, bias, unit, or timing transformation. */
data class SensorCallbackSnapshot(
    val sensorId: Int,
    val androidType: Int,
    val name: String,
    val vendor: String,
    val version: Int,
    val sourceTimestampNs: Long,
    val arrivalTimestampNs: Long,
    val values: FloatArray,
    val accuracy: Int,
)

/** Raw retention must finish successfully before a valid observation reaches runtime ingress. */
fun interface SensorEvidenceRecorder {
    fun record(event: NavigationIngressEvent<Map<String, Any?>>)
}

/**
 * I-01 adapter for an explicitly started session. The caller owns SensorManager registration,
 * permissions, service lifetime, and C-02 persistence. This class neither starts sensors nor
 * modifies C-07. A new instance is required for each boot-scoped session.
 */
class SensorContractAdapter(
    private val sessionId: String,
    private val recorder: SensorEvidenceRecorder,
    private val ingress: NavigationIngress,
) {
    private val sequences = mutableMapOf<Int, Long>()
    private val latestSourceNs = mutableMapOf<Int, Long>()
    private var publishing = false

    init {
        require(sessionId.isNotBlank())
        require(ingress.sourceMode == DisplayModeV1.LIVE_DEVICE)
    }

    /** Invalid observations are retained, with original values, but never sent to runtime. */
    @Synchronized
    fun accept(snapshot: SensorCallbackSnapshot): NavigationIngressResult? {
        check(!publishing) { "Reentrant acquisition publication" }
        val values = snapshot.values.map(Float::toDouble)
        val sequence = sequences[snapshot.sensorId] ?: 0L
        check(sequence < Long.MAX_VALUE) { "Sensor sequence exhausted; stop the session" }
        sequences[snapshot.sensorId] = sequence + 1L
        val stream = "sensor:${snapshot.sensorId}"
        val evidenceId = UUID.randomUUID().toString()
        val type = TYPES[snapshot.androidType]
        val previousNs = latestSourceNs[snapshot.sensorId]
        val reason = when {
            type == null -> "UNSUPPORTED_SENSOR_TYPE"
            snapshot.sourceTimestampNs < 0L || snapshot.arrivalTimestampNs < snapshot.sourceTimestampNs ->
                "INVALID_SENSOR_TIME"
            previousNs != null && snapshot.sourceTimestampNs <= previousNs ->
                "NON_INCREASING_SENSOR_TIME"
            snapshot.accuracy !in 0..3 -> "INVALID_SENSOR_ACCURACY"
            snapshot.name.isBlank() || snapshot.vendor.isBlank() || snapshot.version < 1 ->
                "INVALID_SENSOR_METADATA"
            values.size != (if (snapshot.androidType == 13) 1 else 3) -> "INVALID_SENSOR_ARITY"
            values.any { !it.isFinite() } -> "NON_FINITE_SENSOR_VALUE"
            else -> null
        }
        // Track the source high-water mark, including retained invalid callbacks, without repair.
        if (snapshot.sourceTimestampNs >= 0L &&
            (previousNs == null || snapshot.sourceTimestampNs > previousNs)) {
            latestSourceNs[snapshot.sensorId] = snapshot.sourceTimestampNs
        }
        val metadata = immutableMap(mapOf(
            "android_sensor_type" to snapshot.androidType,
            "android_sensor_id" to snapshot.sensorId,
            "sensor_name" to snapshot.name,
            "vendor" to snapshot.vendor,
            "version" to snapshot.version,
        ))
        val payload = immutableMap(mapOf(
            "schema_version" to 1,
            "evidence_id" to evidenceId,
            "session_id" to sessionId,
            "stream_id" to stream,
            "sequence" to sequence,
            "source_timestamp_ns" to snapshot.sourceTimestampNs,
            "arrival_elapsed_realtime_ns" to snapshot.arrivalTimestampNs,
            "sensor_type" to (type ?: "UNSUPPORTED"),
            "values" to Collections.unmodifiableList(values),
            "accuracy" to snapshot.accuracy,
            "source_metadata" to metadata,
        ))
        val event = NavigationIngressEvent(sequence, EvidenceEnvelopeV1(
            payloadType = "RawSensorSample",
            timestamp = TimestampV1(snapshot.sourceTimestampNs, snapshot.arrivalTimestampNs,
                "android.elapsed_realtime_ns", snapshot.sourceTimestampNs),
            provenance = ProvenanceV1(evidenceId, sessionId, stream, ProvenanceTypeV1.LIVE_DEVICE),
            payload = payload,
            validityGate = ValidityGateV1(values.all { it.isFinite() }, reason == null, reason),
        ))
        publishing = true
        try {
            recorder.record(event)
            return if (reason == null) ingress.submit(event) else null
        } finally {
            publishing = false
        }
    }

    companion object {
        private val TYPES = mapOf(1 to "ACCELEROMETER", 2 to "MAGNETIC_FIELD",
            4 to "GYROSCOPE", 13 to "AMBIENT_TEMPERATURE")
        private fun immutableMap(values: Map<String, Any?>): Map<String, Any?> =
            Collections.unmodifiableMap(LinkedHashMap(values))
    }
}

/** Copies callback-owned arrays immediately; registration remains with the session owner. */
class ContractSensorEventListener(
    private val adapter: SensorContractAdapter,
    private val onAccuracy: (Sensor?, Int) -> Unit,
) : SensorEventListener {
    override fun onSensorChanged(event: SensorEvent) {
        val arrival = SystemClock.elapsedRealtimeNanos()
        val sensor = event.sensor
        adapter.accept(SensorCallbackSnapshot(sensor.id, sensor.type, sensor.name, sensor.vendor,
            sensor.version, event.timestamp, arrival, event.values.copyOf(), event.accuracy))
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = onAccuracy(sensor, accuracy)
}
