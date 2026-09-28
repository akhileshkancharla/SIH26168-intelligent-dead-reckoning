package org.sih26168.app.replay

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DeterministicReplaySchedulerTest {
    @Test
    fun create_rejectsRegressiveSourceTimeWithoutSorting() {
        val result = DeterministicReplayScheduler.create(
            listOf(record(timeNs = 10L, sequence = 1L), record(timeNs = 9L, sequence = 2L)),
        )

        assertRejected(result, ReplayScheduleRejectionReason.REGRESSIVE_TIMESTAMP, 1)
    }

    @Test
    fun create_rejectsDuplicateEvidenceAndNonIncreasingPerStreamSequence() {
        val duplicateEvidence = DeterministicReplayScheduler.create(
            listOf(
                record(timeNs = 10L, sequence = 1L, evidenceId = "same"),
                record(timeNs = 11L, sequence = 2L, evidenceId = "same"),
            ),
        )
        assertRejected(duplicateEvidence, ReplayScheduleRejectionReason.DUPLICATE_EVIDENCE_ID, 1)

        val repeatedSequence = DeterministicReplayScheduler.create(
            listOf(record(timeNs = 10L, sequence = 1L), record(timeNs = 11L, sequence = 1L)),
        )
        assertRejected(
            repeatedSequence,
            ReplayScheduleRejectionReason.NON_INCREASING_STREAM_SEQUENCE,
            1,
        )
    }

    @Test
    fun step_emitsOneCompleteTimestampEpochInReaderOrder() {
        val scheduler = scheduler(
            listOf(
                record(timeNs = 100L, sequence = 1L, evidenceId = "imu-1"),
                record(
                    timeNs = 100L,
                    sequence = 1L,
                    evidenceId = "gnss-1",
                    streamId = "gnss",
                ),
                record(timeNs = 110L, sequence = 2L, evidenceId = "imu-2"),
            ),
        )

        val first = scheduler.step().accepted()
        assertEquals(listOf("imu-1", "gnss-1"), first.emitted.map { it.evidenceId })
        assertEquals(100L, first.snapshot.virtualTimeNs)
        assertEquals(ReplaySchedulerStatus.PAUSED, first.snapshot.status)

        val second = scheduler.step().accepted()
        assertEquals(listOf("imu-2"), second.emitted.map { it.evidenceId })
        assertEquals(ReplaySchedulerStatus.COMPLETED, second.snapshot.status)
    }

    @Test
    fun pauseAndResume_preserveCursorWithoutSkippingOrDuplicatingRecords() {
        val scheduler = scheduler(standardRecords())

        scheduler.play().accepted()
        assertEquals(listOf("event-0"), scheduler.advanceByElapsedTime(0L).accepted().ids())
        scheduler.pause().accepted()

        val pausedAdvance = scheduler.advanceByElapsedTime(10L)
        assertRejected(pausedAdvance, ReplayControlRejectionReason.INVALID_STATE)
        assertEquals(1, scheduler.snapshot().cursor)

        scheduler.play().accepted()
        assertEquals(listOf("event-1"), scheduler.advanceByElapsedTime(10L).accepted().ids())
        assertEquals(2, scheduler.snapshot().cursor)
    }

    @Test
    fun everySupportedSpeed_emitsExactlyTheSameEvidenceOrder() {
        val expected = listOf("event-0", "event-1", "event-2", "event-3")

        assertEquals(expected, replayAllAt(ReplaySpeed.HALF, elapsedNs = 80L))
        assertEquals(expected, replayAllAt(ReplaySpeed.NORMAL, elapsedNs = 40L))
        assertEquals(expected, replayAllAt(ReplaySpeed.DOUBLE, elapsedNs = 20L))
    }

    @Test
    fun halfSpeed_carriesFractionalNanosecondsExactly() {
        val scheduler = scheduler(
            listOf(
                record(timeNs = 0L, sequence = 1L, evidenceId = "origin"),
                record(timeNs = 1L, sequence = 2L, evidenceId = "next"),
            ),
        )
        scheduler.setSpeed(ReplaySpeed.HALF).accepted()
        scheduler.play().accepted()

        assertEquals(listOf("origin"), scheduler.advanceByElapsedTime(1L).accepted().ids())
        assertEquals(listOf("next"), scheduler.advanceByElapsedTime(1L).accepted().ids())
    }

    @Test
    fun speedChanges_preserveFractionalVirtualTime() {
        val scheduler = scheduler(
            listOf(
                record(timeNs = 0L, sequence = 1L, evidenceId = "origin"),
                record(timeNs = 1L, sequence = 2L, evidenceId = "next"),
            ),
        )
        scheduler.setSpeed(ReplaySpeed.HALF).accepted()
        scheduler.play().accepted()

        assertEquals(listOf("origin"), scheduler.advanceByElapsedTime(1L).accepted().ids())
        scheduler.setSpeed(ReplaySpeed.NORMAL).accepted()
        scheduler.setSpeed(ReplaySpeed.HALF).accepted()

        assertEquals(listOf("next"), scheduler.advanceByElapsedTime(1L).accepted().ids())
    }

    @Test
    fun step_discardsFractionalCarryFromThePreStepClockPosition() {
        val scheduler = scheduler(
            listOf(
                record(timeNs = 0L, sequence = 1L, evidenceId = "origin"),
                record(timeNs = 10L, sequence = 2L, evidenceId = "stepped"),
                record(timeNs = 11L, sequence = 3L, evidenceId = "after-step"),
            ),
        )
        scheduler.setSpeed(ReplaySpeed.HALF).accepted()
        scheduler.play().accepted()

        assertEquals(listOf("origin"), scheduler.advanceByElapsedTime(1L).accepted().ids())
        scheduler.pause().accepted()
        assertEquals(listOf("stepped"), scheduler.step().accepted().ids())
        scheduler.play().accepted()

        assertTrue(scheduler.advanceByElapsedTime(1L).accepted().emitted.isEmpty())
        assertEquals(
            listOf("after-step"),
            scheduler.advanceByElapsedTime(1L).accepted().ids(),
        )
    }

    @Test
    fun reset_restoresOriginCursorPauseAndNormalSpeed() {
        val scheduler = scheduler(standardRecords())
        scheduler.setSpeed(ReplaySpeed.DOUBLE).accepted()
        scheduler.play().accepted()
        scheduler.advanceByElapsedTime(20L).accepted()

        val reset = scheduler.reset().accepted().snapshot

        assertEquals(ReplaySchedulerStatus.PAUSED, reset.status)
        assertEquals(0, reset.cursor)
        assertEquals(100L, reset.virtualTimeNs)
        assertEquals(ReplaySpeed.NORMAL, reset.speed)
        assertEquals(listOf("event-0"), scheduler.step().accepted().ids())
    }

    @Test
    fun advance_rejectsNegativeElapsedTimeAndOverflowWithoutChangingState() {
        val scheduler = scheduler(
            listOf(record(timeNs = Long.MAX_VALUE - 1L, sequence = 1L)),
        )
        scheduler.play().accepted()
        val initial = scheduler.snapshot()

        assertRejected(
            scheduler.advanceByElapsedTime(-1L),
            ReplayControlRejectionReason.NEGATIVE_ELAPSED_TIME,
        )
        assertEquals(initial, scheduler.snapshot())

        scheduler.setSpeed(ReplaySpeed.DOUBLE).accepted()
        val beforeOverflow = scheduler.snapshot()
        assertRejected(
            scheduler.advanceByElapsedTime(Long.MAX_VALUE),
            ReplayControlRejectionReason.TIME_OVERFLOW,
        )
        assertEquals(beforeOverflow, scheduler.snapshot())
    }

    @Test
    fun emptySchedule_isExplicitlyCompletedAndCanBeResetDeterministically() {
        val scheduler = scheduler(emptyList())

        assertEquals(ReplaySchedulerStatus.COMPLETED, scheduler.snapshot().status)
        assertRejected(scheduler.play(), ReplayControlRejectionReason.INVALID_STATE)
        assertEquals(ReplaySchedulerStatus.COMPLETED, scheduler.reset().accepted().snapshot.status)
    }

    private fun replayAllAt(speed: ReplaySpeed, elapsedNs: Long): List<String> {
        val scheduler = scheduler(standardRecords())
        scheduler.setSpeed(speed).accepted()
        scheduler.play().accepted()
        return scheduler.advanceByElapsedTime(elapsedNs).accepted().ids()
    }

    private fun standardRecords(): List<ScheduledReplayRecord<String>> = listOf(
        record(timeNs = 100L, sequence = 1L, evidenceId = "event-0"),
        record(timeNs = 110L, sequence = 2L, evidenceId = "event-1"),
        record(timeNs = 120L, sequence = 3L, evidenceId = "event-2"),
        record(timeNs = 140L, sequence = 4L, evidenceId = "event-3"),
    )

    private fun record(
        timeNs: Long,
        sequence: Long,
        evidenceId: String = "event-$sequence",
        streamId: String = "imu",
    ) = ScheduledReplayRecord(
        monotonicTimeNs = timeNs,
        streamId = streamId,
        streamSequence = sequence,
        evidenceId = evidenceId,
        payload = evidenceId,
    )

    private fun scheduler(
        records: List<ScheduledReplayRecord<String>>,
    ): DeterministicReplayScheduler<String> = when (
        val result = DeterministicReplayScheduler.create(records)
    ) {
        is ReplayScheduleBuildResult.Ready -> result.scheduler
        is ReplayScheduleBuildResult.Rejected ->
            throw AssertionError("unexpected rejection: ${result.rejection}")
    }

    private fun ReplayControlResult<String>.accepted(): ReplayControlResult.Accepted<String> =
        this as? ReplayControlResult.Accepted<String>
            ?: throw AssertionError("expected accepted result, got $this")

    private fun ReplayControlResult.Accepted<String>.ids(): List<String> =
        emitted.map { it.evidenceId }

    private fun assertRejected(
        result: ReplayScheduleBuildResult<String>,
        expectedReason: ReplayScheduleRejectionReason,
        expectedIndex: Int,
    ) {
        val rejected = result as? ReplayScheduleBuildResult.Rejected
            ?: throw AssertionError("expected rejected result, got $result")
        assertEquals(expectedReason, rejected.rejection.reason)
        assertEquals(expectedIndex, rejected.rejection.recordIndex)
    }

    private fun assertRejected(
        result: ReplayControlResult<String>,
        expectedReason: ReplayControlRejectionReason,
    ) {
        val rejected = result as? ReplayControlResult.Rejected
            ?: throw AssertionError("expected rejected result, got $result")
        assertEquals(expectedReason, rejected.reason)
    }
}
