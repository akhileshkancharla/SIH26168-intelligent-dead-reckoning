package org.sih26168.navigation

import java.nio.ByteBuffer
import java.nio.ByteOrder

internal interface NativeCalls {
    fun create(input: ByteBuffer, result: ByteBuffer): Long
    fun destroy(handle: Long): Int
    fun propagate(handle: Long, input: ByteBuffer, output: ByteBuffer): Int
    fun update(handle: Long, input: ByteBuffer, output: ByteBuffer): Int
    fun snapshot(handle: Long, output: ByteBuffer): Int
}

internal object NativeNavigationJni {
    init { System.loadLibrary("sih26168_navigation_jni") }

    @JvmStatic external fun create(input: ByteBuffer, result: ByteBuffer): Long
    @JvmStatic external fun destroy(handle: Long): Int
    @JvmStatic external fun propagate(handle: Long, input: ByteBuffer, output: ByteBuffer): Int
    @JvmStatic external fun update(handle: Long, input: ByteBuffer, output: ByteBuffer): Int
    @JvmStatic external fun snapshot(handle: Long, output: ByteBuffer): Int
}

private object ProductionNativeCalls : NativeCalls {
    override fun create(input: ByteBuffer, result: ByteBuffer) = NativeNavigationJni.create(input, result)
    override fun destroy(handle: Long) = NativeNavigationJni.destroy(handle)
    override fun propagate(handle: Long, input: ByteBuffer, output: ByteBuffer) =
        NativeNavigationJni.propagate(handle, input, output)
    override fun update(handle: Long, input: ByteBuffer, output: ByteBuffer) =
        NativeNavigationJni.update(handle, input, output)
    override fun snapshot(handle: Long, output: ByteBuffer) = NativeNavigationJni.snapshot(handle, output)
}

data class CreateResult(val status: BoundaryStatus, val handle: Long = 0)
data class NativeResult<T>(val status: BoundaryStatus, val value: T? = null)

class NativeNavigationBridge internal constructor(
    private val calls: NativeCalls = ProductionNativeCalls,
    private val allocator: (Int) -> ByteBuffer = { ByteBuffer.allocateDirect(it) },
) {
    fun create(initialState: InitialStateWire): CreateResult = boundaryGuard({ CreateResult(it) }) {
        val input = direct(NavigationWireCodec.encode(initialState))
        val result = allocator(12).order(ByteOrder.LITTLE_ENDIAN)
        val returnedHandle = calls.create(input, result)
        if (returnedHandle < 0) {
            return@boundaryGuard CreateResult(BoundaryStatus.fromCode((-returnedHandle).toInt()))
        }
        result.position(0)
        val encodedStatus = BoundaryStatus.fromCode(result.int)
        val encodedHandle = result.long
        val status = encodedStatus
        if (status == BoundaryStatus.OK && returnedHandle == encodedHandle && returnedHandle > 0) {
            CreateResult(status, returnedHandle)
        } else {
            CreateResult(if (status == BoundaryStatus.OK) BoundaryStatus.NATIVE_EXCEPTION else status)
        }
    }

    fun destroy(handle: Long): BoundaryStatus = boundaryGuard({ it }) {
        BoundaryStatus.fromCode(calls.destroy(handle))
    }

    fun propagate(handle: Long, batch: ImuBatchWire): NativeResult<PropagationWire> =
        boundaryGuard({ NativeResult(it) }) {
        val input = direct(NavigationWireCodec.encode(batch))
        val output = allocator(MAX_MESSAGE_BYTES).order(ByteOrder.LITTLE_ENDIAN)
        val status = BoundaryStatus.fromCode(calls.propagate(handle, input, output))
        if (status != BoundaryStatus.OK) NativeResult(status)
        else NavigationWireCodec.decodePropagation(output).let { NativeResult(it.first, it.second) }
    }

    fun update(handle: Long, measurement: MeasurementWire): NativeResult<MeasurementResultWire> =
        boundaryGuard({ NativeResult(it) }) {
            val input = direct(NavigationWireCodec.encode(measurement))
            val output = allocator(MAX_MESSAGE_BYTES).order(ByteOrder.LITTLE_ENDIAN)
            val status = BoundaryStatus.fromCode(calls.update(handle, input, output))
            if (status != BoundaryStatus.OK) NativeResult(status)
            else NavigationWireCodec.decodeMeasurement(output).let { NativeResult(it.first, it.second) }
        }

    fun snapshot(handle: Long): NativeResult<SnapshotWire> = boundaryGuard({ NativeResult(it) }) {
        val output = allocator(MAX_MESSAGE_BYTES).order(ByteOrder.LITTLE_ENDIAN)
        val status = BoundaryStatus.fromCode(calls.snapshot(handle, output))
        if (status != BoundaryStatus.OK) NativeResult(status)
        else NavigationWireCodec.decodeSnapshot(output).let { NativeResult(it.first, it.second) }
    }

    private fun direct(bytes: ByteArray): ByteBuffer = allocator(bytes.size)
        .order(ByteOrder.LITTLE_ENDIAN).apply { put(bytes); position(0) }

    private inline fun <T> boundaryGuard(
        failure: (BoundaryStatus) -> T,
        operation: () -> T,
    ): T = try {
        operation()
    } catch (_: OutOfMemoryError) {
        failure(BoundaryStatus.ALLOCATION_FAILURE)
    } catch (_: IllegalArgumentException) {
        failure(BoundaryStatus.INVALID_ARGUMENT)
    } catch (_: Exception) {
        failure(BoundaryStatus.PENDING_JNI_EXCEPTION)
    }
}
