package org.sih26168.s1logger

object RecordingContract {
    const val SCHEMA_VERSION = "s1.android.acquisition.v1"
    const val CLOCK_ELAPSED_REALTIME_NS = "android.elapsed_realtime_ns"
    const val CLOCK_UNIX_EPOCH_MS = "unix_epoch_ms_auxiliary"
    const val SENSOR_PERIOD_US = 10_000
    const val SENSOR_MAX_REPORT_LATENCY_US = 2_000_000
    const val LOCATION_MIN_TIME_MS = 100L
    const val CHUNK_MAX_BYTES = 5L * 1024L * 1024L
    const val FLUSH_INTERVAL_MS = 10_000L
    const val MIN_FREE_BYTES = 100L * 1024L * 1024L
    const val MAX_SESSION_BYTES = 2L * 1024L * 1024L * 1024L
}

data class TimingFinding(
    val duplicates: Int,
    val nonMonotonic: Int,
    val gaps: Int,
)

object TimingChecks {
    fun inspect(timestampsNs: List<Long>, gapThresholdNs: Long): TimingFinding {
        var duplicates = 0
        var nonMonotonic = 0
        var gaps = 0
        timestampsNs.zipWithNext().forEach { (a, b) ->
            if (b == a) duplicates++
            if (b < a) nonMonotonic++
            if (b - a > gapThresholdNs) gaps++
        }
        return TimingFinding(duplicates, nonMonotonic, gaps)
    }
}

class StreamSequencer {
    private val sequences = mutableMapOf<String, Long>()
    @Synchronized fun next(stream: String): Long {
        val value = (sequences[stream] ?: 0L) + 1L
        sequences[stream] = value
        return value
    }
}
