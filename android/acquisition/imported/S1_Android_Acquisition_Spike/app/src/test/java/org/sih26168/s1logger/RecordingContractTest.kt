package org.sih26168.s1logger

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RecordingContractTest {
    @Test fun timestampUnitIsNanoseconds() {
        assertTrue(RecordingContract.CLOCK_ELAPSED_REALTIME_NS.endsWith("_ns"))
        assertEquals(10_000, RecordingContract.SENSOR_PERIOD_US)
    }

    @Test fun sequenceNumbersAreIndependentAndIncreasing() {
        val sequence = StreamSequencer()
        assertEquals(1L, sequence.next("a"))
        assertEquals(2L, sequence.next("a"))
        assertEquals(1L, sequence.next("b"))
    }

    @Test fun duplicateDetectionIsDeterministic() {
        assertEquals(1, TimingChecks.inspect(listOf(1L, 2L, 2L, 3L), 10L).duplicates)
    }

    @Test fun reorderDetectionIsDeterministic() {
        assertEquals(1, TimingChecks.inspect(listOf(1L, 3L, 2L), 10L).nonMonotonic)
    }

    @Test fun gapDetectionIsDeterministic() {
        assertEquals(1, TimingChecks.inspect(listOf(0L, 10L, 100L), 50L).gaps)
    }
}
