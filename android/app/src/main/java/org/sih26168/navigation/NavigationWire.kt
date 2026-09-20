package org.sih26168.navigation

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.charset.StandardCharsets

internal const val WIRE_MAGIC: Int = 0x494E4A53
internal const val WIRE_VERSION: Short = 1
internal const val MAX_MESSAGE_BYTES: Int = 1024 * 1024

enum class BoundaryStatus(val code: Int) {
    OK(0), NULL_HANDLE(1), STALE_HANDLE(2), CONCURRENT_CALL(3), NULL_BUFFER(4),
    NON_DIRECT_BUFFER(5), BUFFER_TOO_SMALL(6), INVALID_MAGIC(7), UNSUPPORTED_VERSION(8),
    UNEXPECTED_MESSAGE_KIND(9), MALFORMED_LENGTH(10), INVALID_ENUM(11), NON_FINITE_VALUE(12),
    DUPLICATE_EVIDENCE_IDENTIFIER(13), PENDING_JNI_EXCEPTION(14), ALLOCATION_FAILURE(15),
    INVALID_ARGUMENT(16), NATIVE_EXCEPTION(17);

    companion object {
        fun fromCode(code: Int): BoundaryStatus = entries.firstOrNull { it.code == code }
            ?: NATIVE_EXCEPTION
    }
}

enum class NavigationMode { INITIALIZING, GNSS_AIDED, DEGRADED, BLACKOUT_DR, REACQUIRING, FAULT }
enum class StateValidity { VALID, INVALID }
enum class MeasurementKind { POSITION, VELOCITY, POSITION_VELOCITY }
enum class PrecheckStatus { PASSED, REJECTED }
enum class NavigationFrame { LOCAL_NORTH_EAST_DOWN }
enum class BodyFrame { PHYSICAL_IMU_BODY }

data class InitialStateWire(
    val sequence: Long,
    val epochNs: Long,
    val clockId: String,
    val originId: String,
    val mode: NavigationMode,
    val positionN: DoubleArray,
    val velocityN: DoubleArray,
    val quaternionNB: DoubleArray,
    val accelBiasB: DoubleArray,
    val gyroBiasB: DoubleArray,
    val covariance: DoubleArray,
    val navigationFrame: NavigationFrame = NavigationFrame.LOCAL_NORTH_EAST_DOWN,
    val bodyFrame: BodyFrame = BodyFrame.PHYSICAL_IMU_BODY,
)

data class ImuSampleWire(
    val sequence: Long,
    val evidenceId: String,
    val sourceTimestampNs: Long,
    val arrivalTimestampNs: Long,
    val specificForceB: DoubleArray,
    val angularRateB: DoubleArray,
    val bodyFrame: BodyFrame = BodyFrame.PHYSICAL_IMU_BODY,
)

data class ImuBatchWire(
    val batchId: String,
    val samples: List<ImuSampleWire>,
    val firstSequence: Long,
    val lastSequence: Long,
    val gapFlags: Int,
    val clockId: String,
)

data class MeasurementWire(
    val sequence: Long,
    val measurementId: String,
    val stateEpochNs: Long,
    val arrivalTimestampNs: Long,
    val kind: MeasurementKind,
    val originId: String,
    val providerEvidenceIds: List<String>,
    val precheckStatus: PrecheckStatus,
    val precheckReason: String,
    val values: DoubleArray,
    val covariance: DoubleArray,
    val navigationFrame: NavigationFrame = NavigationFrame.LOCAL_NORTH_EAST_DOWN,
)

data class StateWire(
    val sequence: Long,
    val epochNs: Long,
    val navigationFrame: NavigationFrame,
    val bodyFrame: BodyFrame,
    val positionN: DoubleArray,
    val velocityN: DoubleArray,
    val quaternionNB: DoubleArray,
    val accelBiasB: DoubleArray,
    val gyroBiasB: DoubleArray,
    val originId: String,
    val mode: NavigationMode,
    val validity: StateValidity,
)

data class CovarianceWire(
    val stateSequence: Long,
    val epochNs: Long,
    val orderingId: String,
    val values: DoubleArray,
    val qualityFlags: Int,
)

data class SnapshotWire(val state: StateWire, val covariance: CovarianceWire)

data class PropagationWire(
    val coreStatus: Int,
    val deltaTimeSeconds: Double,
    val gapDetected: Boolean,
    val stateSequence: Long,
    val snapshots: SnapshotWire,
)

data class MeasurementResultWire(
    val coreStatus: Int,
    val dimension: Int,
    val normalizedInnovationSquared: Double,
    val stateSequence: Long,
    val snapshots: SnapshotWire,
)

internal object NavigationWireCodec {
    private enum class Kind(val code: Short) {
        INITIAL(1), BATCH(2), MEASUREMENT(3), PROPAGATION_RESPONSE(4),
        MEASUREMENT_RESPONSE(5), SNAPSHOT_RESPONSE(6),
    }

    fun encode(value: InitialStateWire): ByteArray = writer(Kind.INITIAL).apply {
        long(value.sequence); long(value.epochNs); string(value.clockId); string(value.originId)
        int(value.mode.ordinal); int(value.navigationFrame.ordinal); int(value.bodyFrame.ordinal)
        doubles(value.positionN, 3); doubles(value.velocityN, 3); doubles(value.quaternionNB, 4)
        doubles(value.accelBiasB, 3); doubles(value.gyroBiasB, 3); doubles(value.covariance, 225)
    }.bytes()

    fun encode(value: ImuBatchWire): ByteArray = writer(Kind.BATCH).apply {
        string(value.batchId); long(value.firstSequence); long(value.lastSequence)
        int(value.gapFlags); string(value.clockId); int(value.samples.size)
        value.samples.forEach { sample ->
            long(sample.sequence); string(sample.evidenceId); long(sample.sourceTimestampNs)
            long(sample.arrivalTimestampNs); int(sample.bodyFrame.ordinal)
            doubles(sample.specificForceB, 3); doubles(sample.angularRateB, 3)
        }
    }.bytes()

    fun encode(value: MeasurementWire): ByteArray = writer(Kind.MEASUREMENT).apply {
        long(value.sequence); string(value.measurementId); long(value.stateEpochNs)
        long(value.arrivalTimestampNs); int(value.kind.ordinal); int(value.navigationFrame.ordinal)
        string(value.originId)
        int(value.providerEvidenceIds.size); value.providerEvidenceIds.forEach(::string)
        int(value.precheckStatus.ordinal); string(value.precheckReason)
        doubles(value.values, 6); doubles(value.covariance, 36)
    }.bytes()

    fun decodePropagation(buffer: ByteBuffer): Pair<BoundaryStatus, PropagationWire?> {
        val reader = Reader(buffer, Kind.PROPAGATION_RESPONSE)
        val boundary = BoundaryStatus.fromCode(reader.int())
        val coreStatus = reader.int()
        val dt = reader.double()
        val gap = reader.byte().toInt() != 0
        val sequence = reader.long()
        val snapshots = reader.snapshots()
        return reader.result(boundary, PropagationWire(coreStatus, dt, gap, sequence, snapshots))
    }

    fun decodeMeasurement(buffer: ByteBuffer): Pair<BoundaryStatus, MeasurementResultWire?> {
        val reader = Reader(buffer, Kind.MEASUREMENT_RESPONSE)
        val boundary = BoundaryStatus.fromCode(reader.int())
        val coreStatus = reader.int()
        val dimension = reader.int()
        val nis = reader.double()
        val sequence = reader.long()
        val snapshots = reader.snapshots()
        return reader.result(
            boundary,
            MeasurementResultWire(coreStatus, dimension, nis, sequence, snapshots),
        )
    }

    fun decodeSnapshot(buffer: ByteBuffer): Pair<BoundaryStatus, SnapshotWire?> {
        val reader = Reader(buffer, Kind.SNAPSHOT_RESPONSE)
        val boundary = BoundaryStatus.fromCode(reader.int())
        return reader.result(boundary, reader.snapshots())
    }

    private fun writer(kind: Kind) = Writer(kind)

    private class Writer(kind: Kind) {
        private var buffer = ByteBuffer.allocate(1024).order(ByteOrder.LITTLE_ENDIAN)

        init { int(WIRE_MAGIC); short(WIRE_VERSION); short(kind.code) }

        fun byte(value: Byte) { ensure(1); buffer.put(value) }
        fun short(value: Short) { ensure(2); buffer.putShort(value) }
        fun int(value: Int) { ensure(4); buffer.putInt(value) }
        fun long(value: Long) { ensure(8); buffer.putLong(value) }
        fun double(value: Double) { ensure(8); buffer.putDouble(value) }
        fun string(value: String) {
            val encoded = value.toByteArray(StandardCharsets.UTF_8)
            require(encoded.size <= 4096) { "wire string exceeds 4096 bytes" }
            int(encoded.size); ensure(encoded.size); buffer.put(encoded)
        }
        fun doubles(values: DoubleArray, expected: Int) {
            require(values.size == expected) { "expected $expected values" }
            values.forEach(::double)
        }
        fun bytes(): ByteArray = ByteArray(buffer.position()).also {
            buffer.flip(); buffer.get(it)
        }
        private fun ensure(count: Int) {
            require(buffer.position() + count <= MAX_MESSAGE_BYTES) { "wire message too large" }
            if (buffer.remaining() >= count) return
            var capacity = buffer.capacity()
            while (capacity - buffer.position() < count) capacity = (capacity * 2).coerceAtMost(MAX_MESSAGE_BYTES)
            buffer = ByteBuffer.allocate(capacity).order(ByteOrder.LITTLE_ENDIAN).also { replacement ->
                buffer.flip(); replacement.put(buffer)
            }
        }
    }

    private class Reader(source: ByteBuffer, expected: Kind) {
        private val buffer = source.duplicate().order(ByteOrder.LITTLE_ENDIAN).apply { position(0) }
        private var valid = true

        init {
            valid = remaining(8) && int() == WIRE_MAGIC && short() == WIRE_VERSION && short() == expected.code
        }

        fun byte(): Byte = if (remaining(1)) buffer.get() else 0
        fun short(): Short = if (remaining(2)) buffer.short else 0
        fun int(): Int = if (remaining(4)) buffer.int else 0
        fun long(): Long = if (remaining(8)) buffer.long else 0
        fun double(): Double = if (remaining(8)) buffer.double else Double.NaN
        fun string(): String {
            val length = int()
            if (length < 0 || length > 4096 || !remaining(length)) return ""
            val bytes = ByteArray(length); buffer.get(bytes)
            return String(bytes, StandardCharsets.UTF_8)
        }
        fun doubles(count: Int): DoubleArray = DoubleArray(count) { double() }
        fun snapshots(): SnapshotWire {
            val state = StateWire(
                sequence = long(), epochNs = long(),
                navigationFrame = enumValue<NavigationFrame>(int()),
                bodyFrame = enumValue<BodyFrame>(int()), positionN = doubles(3),
                velocityN = doubles(3),
                quaternionNB = doubles(4), accelBiasB = doubles(3), gyroBiasB = doubles(3),
                originId = string(), mode = enumValue<NavigationMode>(int()),
                validity = enumValue<StateValidity>(int()),
            )
            val covariance = CovarianceWire(long(), long(), string(), doubles(225), int())
            return SnapshotWire(state, covariance)
        }
        fun <T> result(boundary: BoundaryStatus, value: T): Pair<BoundaryStatus, T?> =
            if (valid) boundary to value else BoundaryStatus.MALFORMED_LENGTH to null
        private fun remaining(count: Int): Boolean {
            if (!valid || count < 0 || buffer.remaining() < count) { valid = false; return false }
            return true
        }
        private inline fun <reified T : Enum<T>> enumValue(index: Int): T {
            val values = enumValues<T>()
            if (index !in values.indices) { valid = false; return values.last() }
            return values[index]
        }
    }
}
