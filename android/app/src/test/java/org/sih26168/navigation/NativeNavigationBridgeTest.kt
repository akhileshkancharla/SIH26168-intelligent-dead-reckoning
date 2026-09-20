package org.sih26168.navigation

import java.nio.ByteBuffer
import java.nio.ByteOrder
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeNavigationBridgeTest {
    private fun initialState() = InitialStateWire(
        sequence = 7,
        epochNs = 1_000_000_000,
        clockId = "boot-clock-1",
        originId = "origin-1",
        mode = NavigationMode.GNSS_AIDED,
        positionN = doubleArrayOf(1.0, 2.0, 3.0),
        velocityN = doubleArrayOf(0.1, 0.2, 0.3),
        quaternionNB = doubleArrayOf(1.0, 0.0, 0.0, 0.0),
        accelBiasB = doubleArrayOf(0.01, -0.02, 0.03),
        gyroBiasB = doubleArrayOf(0.001, -0.002, 0.003),
        covariance = DoubleArray(225).also { values ->
            repeat(15) { index -> values[index * 15 + index] = 0.5 }
        },
    )

    @Test
    fun batchCodecPreservesIdentityClockGapAndEvidence() {
        val batch = ImuBatchWire(
            batchId = "batch-1",
            samples = listOf(
                ImuSampleWire(
                    10, "imu-10", 1_010_000_000, 1_010_001_000,
                    doubleArrayOf(0.0, 0.0, -9.80665), doubleArrayOf(0.01, -0.02, 0.03),
                ),
            ),
            firstSequence = 10,
            lastSequence = 10,
            gapFlags = 2,
            clockId = "boot-clock-1",
        )
        val buffer = ByteBuffer.wrap(NavigationWireCodec.encode(batch)).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals(WIRE_MAGIC, buffer.int)
        assertEquals(WIRE_VERSION, buffer.short)
        assertEquals(2, buffer.short.toInt())
        assertEquals("batch-1", buffer.string())
        assertEquals(10, buffer.long)
        assertEquals(10, buffer.long)
        assertEquals(2, buffer.int)
        assertEquals("boot-clock-1", buffer.string())
        assertEquals(1, buffer.int)
        assertEquals(10, buffer.long)
        assertEquals("imu-10", buffer.string())
        assertEquals(1_010_000_000, buffer.long)
        assertEquals(1_010_001_000, buffer.long)
    }

    @Test
    fun createUsesDirectBuffersAndReturnsOpaqueHandle() {
        val calls = object : NativeCalls {
            override fun create(input: ByteBuffer, result: ByteBuffer): Long {
                assertTrue(input.isDirect)
                assertTrue(result.isDirect)
                result.order(ByteOrder.LITTLE_ENDIAN).putInt(BoundaryStatus.OK.code).putLong(42)
                return 42
            }
            override fun destroy(handle: Long) = BoundaryStatus.OK.code
            override fun propagate(handle: Long, input: ByteBuffer, output: ByteBuffer) = 0
            override fun update(handle: Long, input: ByteBuffer, output: ByteBuffer) = 0
            override fun snapshot(handle: Long, output: ByteBuffer) = 0
        }
        val result = NativeNavigationBridge(calls).create(initialState())
        assertEquals(BoundaryStatus.OK, result.status)
        assertEquals(42, result.handle)
    }

    @Test
    fun javaAllocationFailureIsExplicit() {
        val calls = object : NativeCalls {
            override fun create(input: ByteBuffer, result: ByteBuffer) = 1L
            override fun destroy(handle: Long) = 0
            override fun propagate(handle: Long, input: ByteBuffer, output: ByteBuffer) = 0
            override fun update(handle: Long, input: ByteBuffer, output: ByteBuffer) = 0
            override fun snapshot(handle: Long, output: ByteBuffer) = 0
        }
        val bridge = NativeNavigationBridge(calls) { throw OutOfMemoryError("synthetic") }
        assertEquals(BoundaryStatus.ALLOCATION_FAILURE, bridge.create(initialState()).status)
    }

    @Test
    fun malformedArrayLengthIsExplicit() {
        val calls = noOpCalls()
        val malformed = initialState().copy(positionN = doubleArrayOf(1.0, 2.0))
        assertEquals(
            BoundaryStatus.INVALID_ARGUMENT,
            NativeNavigationBridge(calls).create(malformed).status,
        )
    }

    @Test
    fun javaExceptionFromNativeCallIsExplicit() {
        val calls = object : NativeCalls by noOpCalls() {
            override fun destroy(handle: Long): Int = throw IllegalStateException("synthetic")
        }
        assertEquals(
            BoundaryStatus.PENDING_JNI_EXCEPTION,
            NativeNavigationBridge(calls).destroy(1),
        )
    }

    @Test
    fun nativeLifecycleStatusIsNotCoerced() {
        val calls = object : NativeCalls {
            override fun create(input: ByteBuffer, result: ByteBuffer) = 0L
            override fun destroy(handle: Long) = BoundaryStatus.STALE_HANDLE.code
            override fun propagate(handle: Long, input: ByteBuffer, output: ByteBuffer) = 0
            override fun update(handle: Long, input: ByteBuffer, output: ByteBuffer) = 0
            override fun snapshot(handle: Long, output: ByteBuffer) = 0
        }
        assertEquals(
            BoundaryStatus.STALE_HANDLE,
            NativeNavigationBridge(calls).destroy(99),
        )
    }

    private fun noOpCalls() = object : NativeCalls {
        override fun create(input: ByteBuffer, result: ByteBuffer) = 1L
        override fun destroy(handle: Long) = BoundaryStatus.OK.code
        override fun propagate(handle: Long, input: ByteBuffer, output: ByteBuffer) = 0
        override fun update(handle: Long, input: ByteBuffer, output: ByteBuffer) = 0
        override fun snapshot(handle: Long, output: ByteBuffer) = 0
    }

    private fun ByteBuffer.string(): String {
        val bytes = ByteArray(int)
        get(bytes)
        return bytes.toString(Charsets.UTF_8)
    }
}
