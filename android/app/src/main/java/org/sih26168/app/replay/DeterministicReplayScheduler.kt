package org.sih26168.app.replay

/**
 * Immutable replay input as delivered by the validated session reader.
 *
 * [monotonicTimeNs], [streamSequence], [evidenceId], and [streamId] are source evidence and
 * must not be rewritten by the scheduler. [payload] remains opaque so the scheduler cannot
 * acquire authority over scientific state or evidence acceptance.
 */
data class ScheduledReplayRecord<T>(
    val monotonicTimeNs: Long,
    val streamId: String,
    val streamSequence: Long,
    val evidenceId: String,
    val payload: T,
)

enum class ReplaySpeed(
    internal val numerator: Long,
    internal val denominator: Long,
) {
    HALF(1L, 2L),
    NORMAL(1L, 1L),
    DOUBLE(2L, 1L),
}

enum class ReplaySchedulerStatus {
    PAUSED,
    PLAYING,
    COMPLETED,
}

data class ReplaySchedulerSnapshot(
    val status: ReplaySchedulerStatus,
    val cursor: Int,
    val recordCount: Int,
    val virtualTimeNs: Long,
    val speed: ReplaySpeed,
)

enum class ReplayScheduleRejectionReason {
    NEGATIVE_TIMESTAMP,
    REGRESSIVE_TIMESTAMP,
    BLANK_STREAM_ID,
    NEGATIVE_STREAM_SEQUENCE,
    NON_INCREASING_STREAM_SEQUENCE,
    BLANK_EVIDENCE_ID,
    DUPLICATE_EVIDENCE_ID,
}

data class ReplayScheduleRejection(
    val reason: ReplayScheduleRejectionReason,
    val recordIndex: Int,
)

sealed interface ReplayScheduleBuildResult<out T> {
    data class Ready<T>(
        val scheduler: DeterministicReplayScheduler<T>,
    ) : ReplayScheduleBuildResult<T>

    data class Rejected(
        val rejection: ReplayScheduleRejection,
    ) : ReplayScheduleBuildResult<Nothing>
}

enum class ReplayControlRejectionReason {
    INVALID_STATE,
    NEGATIVE_ELAPSED_TIME,
    TIME_OVERFLOW,
}

sealed interface ReplayControlResult<out T> {
    data class Accepted<T>(
        val emitted: List<ScheduledReplayRecord<T>>,
        val snapshot: ReplaySchedulerSnapshot,
    ) : ReplayControlResult<T>

    data class Rejected(
        val reason: ReplayControlRejectionReason,
        val snapshot: ReplaySchedulerSnapshot,
    ) : ReplayControlResult<Nothing>
}

/**
 * Deterministic virtual-time scheduler for C-12 replay records.
 *
 * The scheduler is intentionally single-threaded. It preserves reader order, rejects invalid
 * source ordering instead of sorting or repairing it, and uses exact rational speed scaling so
 * playback speed changes pacing only. A paused step emits one complete source-time epoch, which
 * prevents a pause from splitting records that share a monotonic timestamp.
 */
class DeterministicReplayScheduler<T> private constructor(
    records: List<ScheduledReplayRecord<T>>,
) {
    private val records: List<ScheduledReplayRecord<T>> = records.toList()
    private val originTimeNs: Long = records.firstOrNull()?.monotonicTimeNs ?: 0L

    private var cursor: Int = 0
    private var status: ReplaySchedulerStatus = if (records.isEmpty()) {
        ReplaySchedulerStatus.COMPLETED
    } else {
        ReplaySchedulerStatus.PAUSED
    }
    private var virtualTimeNs: Long = originTimeNs
    private var speed: ReplaySpeed = ReplaySpeed.NORMAL
    // All supported speeds are exactly representable in half-nanosecond units. Keeping the carry
    // in this speed-independent unit means a control-only speed change cannot discard virtual time.
    private var fractionalTimeUnits: Long = 0L

    fun snapshot(): ReplaySchedulerSnapshot = ReplaySchedulerSnapshot(
        status = status,
        cursor = cursor,
        recordCount = records.size,
        virtualTimeNs = virtualTimeNs,
        speed = speed,
    )

    fun play(): ReplayControlResult<T> {
        if (status == ReplaySchedulerStatus.COMPLETED) {
            return rejected(ReplayControlRejectionReason.INVALID_STATE)
        }
        status = ReplaySchedulerStatus.PLAYING
        return accepted(emptyList())
    }

    fun pause(): ReplayControlResult<T> {
        if (status != ReplaySchedulerStatus.PLAYING) {
            return rejected(ReplayControlRejectionReason.INVALID_STATE)
        }
        status = ReplaySchedulerStatus.PAUSED
        return accepted(emptyList())
    }

    fun setSpeed(newSpeed: ReplaySpeed): ReplayControlResult<T> {
        if (status == ReplaySchedulerStatus.COMPLETED) {
            return rejected(ReplayControlRejectionReason.INVALID_STATE)
        }
        speed = newSpeed
        return accepted(emptyList())
    }

    fun step(): ReplayControlResult<T> {
        if (status != ReplaySchedulerStatus.PAUSED || cursor >= records.size) {
            return rejected(ReplayControlRejectionReason.INVALID_STATE)
        }

        val epochNs = records[cursor].monotonicTimeNs
        virtualTimeNs = epochNs
        val emitted = emitThrough(epochNs)
        completeIfExhausted()
        return accepted(emitted)
    }

    fun advanceByElapsedTime(elapsedTimeNs: Long): ReplayControlResult<T> {
        if (elapsedTimeNs < 0L) {
            return rejected(ReplayControlRejectionReason.NEGATIVE_ELAPSED_TIME)
        }
        if (status != ReplaySchedulerStatus.PLAYING) {
            return rejected(ReplayControlRejectionReason.INVALID_STATE)
        }

        val scaled = scaleElapsedTime(elapsedTimeNs)
            ?: return rejected(ReplayControlRejectionReason.TIME_OVERFLOW)
        val nextVirtualTime = addWithoutOverflow(virtualTimeNs, scaled.deltaNs)
            ?: return rejected(ReplayControlRejectionReason.TIME_OVERFLOW)

        virtualTimeNs = nextVirtualTime
        fractionalTimeUnits = scaled.remainder
        val emitted = emitThrough(virtualTimeNs)
        completeIfExhausted()
        return accepted(emitted)
    }

    fun reset(): ReplayControlResult<T> {
        cursor = 0
        virtualTimeNs = originTimeNs
        speed = ReplaySpeed.NORMAL
        fractionalTimeUnits = 0L
        status = if (records.isEmpty()) {
            ReplaySchedulerStatus.COMPLETED
        } else {
            ReplaySchedulerStatus.PAUSED
        }
        return accepted(emptyList())
    }

    private fun scaleElapsedTime(elapsedTimeNs: Long): ScaledElapsedTime? {
        val speedUnitsPerElapsedNanosecond = try {
            Math.multiplyExact(
                speed.numerator,
                TIME_FRACTION_DENOMINATOR / speed.denominator,
            )
        } catch (_: ArithmeticException) {
            return null
        }
        val scaledUnits = try {
            Math.addExact(
                Math.multiplyExact(elapsedTimeNs, speedUnitsPerElapsedNanosecond),
                fractionalTimeUnits,
            )
        } catch (_: ArithmeticException) {
            return null
        }
        return ScaledElapsedTime(
            deltaNs = scaledUnits / TIME_FRACTION_DENOMINATOR,
            remainder = scaledUnits % TIME_FRACTION_DENOMINATOR,
        )
    }

    private fun addWithoutOverflow(left: Long, right: Long): Long? = try {
        Math.addExact(left, right)
    } catch (_: ArithmeticException) {
        null
    }

    private fun emitThrough(inclusiveTimeNs: Long): List<ScheduledReplayRecord<T>> {
        val start = cursor
        while (cursor < records.size && records[cursor].monotonicTimeNs <= inclusiveTimeNs) {
            cursor += 1
        }
        return records.subList(start, cursor).toList()
    }

    private fun completeIfExhausted() {
        if (cursor == records.size) {
            status = ReplaySchedulerStatus.COMPLETED
            fractionalTimeUnits = 0L
        }
    }

    private fun accepted(
        emitted: List<ScheduledReplayRecord<T>>,
    ): ReplayControlResult.Accepted<T> = ReplayControlResult.Accepted(
        emitted = emitted,
        snapshot = snapshot(),
    )

    private fun rejected(reason: ReplayControlRejectionReason): ReplayControlResult.Rejected =
        ReplayControlResult.Rejected(reason = reason, snapshot = snapshot())

    private data class ScaledElapsedTime(
        val deltaNs: Long,
        val remainder: Long,
    )

    companion object {
        private const val TIME_FRACTION_DENOMINATOR = 2L

        fun <T> create(
            records: List<ScheduledReplayRecord<T>>,
        ): ReplayScheduleBuildResult<T> {
            val seenEvidenceIds = mutableSetOf<String>()
            val lastSequenceByStream = mutableMapOf<String, Long>()
            var previousTimestampNs: Long? = null

            records.forEachIndexed { index, record ->
                val reason = when {
                    record.monotonicTimeNs < 0L ->
                        ReplayScheduleRejectionReason.NEGATIVE_TIMESTAMP
                    previousTimestampNs?.let { record.monotonicTimeNs < it } == true ->
                        ReplayScheduleRejectionReason.REGRESSIVE_TIMESTAMP
                    record.streamId.isBlank() ->
                        ReplayScheduleRejectionReason.BLANK_STREAM_ID
                    record.streamSequence < 0L ->
                        ReplayScheduleRejectionReason.NEGATIVE_STREAM_SEQUENCE
                    lastSequenceByStream[record.streamId]
                        ?.let { record.streamSequence <= it } == true ->
                        ReplayScheduleRejectionReason.NON_INCREASING_STREAM_SEQUENCE
                    record.evidenceId.isBlank() ->
                        ReplayScheduleRejectionReason.BLANK_EVIDENCE_ID
                    !seenEvidenceIds.add(record.evidenceId) ->
                        ReplayScheduleRejectionReason.DUPLICATE_EVIDENCE_ID
                    else -> null
                }
                if (reason != null) {
                    return ReplayScheduleBuildResult.Rejected(
                        ReplayScheduleRejection(reason = reason, recordIndex = index),
                    )
                }
                previousTimestampNs = record.monotonicTimeNs
                lastSequenceByStream[record.streamId] = record.streamSequence
            }

            return ReplayScheduleBuildResult.Ready(DeterministicReplayScheduler(records))
        }
    }
}
