package org.sih26168.app.model

import java.security.MessageDigest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OnnxRuntimeMobileTest {
    @Test
    fun validContractPassesStaticGate() {
        assertNull(
            OnnxRuntimeMobile.validateContract(
                validContract(),
                modelSizeBytes = MODEL_BYTES.size,
            ),
        )
    }

    @Test
    fun malformedHashFailsBeforeRuntimeLoad() {
        val violation = OnnxRuntimeMobile.validateContract(
            validContract().copy(modelSha256 = "not-a-hash"),
            modelSizeBytes = MODEL_BYTES.size,
        )

        assertEquals("model SHA-256 must be lowercase hexadecimal", violation)
    }

    @Test
    fun dynamicOrEmptyTensorShapesFailClosed() {
        val dynamic = OnnxRuntimeMobile.validateContract(
            validContract().copy(
                inputs = listOf(MobileTensorContract("imu_window", listOf(1, -1))),
            ),
            modelSizeBytes = MODEL_BYTES.size,
        )
        val empty = OnnxRuntimeMobile.validateContract(
            validContract().copy(outputs = emptyList()),
            modelSizeBytes = MODEL_BYTES.size,
        )

        assertTrue(dynamic!!.contains("fixed positive shape"))
        assertEquals("output contract must not be empty", empty)
    }

    @Test
    fun duplicateNamesFailClosed() {
        val duplicate = MobileTensorContract("imu_window", listOf(1, 2))
        val violation = OnnxRuntimeMobile.validateContract(
            validContract().copy(inputs = listOf(duplicate, duplicate)),
            modelSizeBytes = MODEL_BYTES.size,
        )

        assertEquals("input names must be unique", violation)
    }

    @Test
    fun semanticRuntimeComparisonIsNumeric() {
        assertTrue(OnnxRuntimeMobile.runtimeAtLeast("1.31.0", "1.9.0"))
        assertTrue(OnnxRuntimeMobile.runtimeAtLeast("1.31.0-mobile", "1.31.0"))
        assertFalse(OnnxRuntimeMobile.runtimeAtLeast("1.30.9", "1.31.0"))
        assertFalse(OnnxRuntimeMobile.runtimeAtLeast("unknown", "1.31.0"))
    }

    private fun validContract(): MobileModelContract = MobileModelContract(
        schemaVersion = 1,
        modelId = "approved-model",
        modelSha256 = sha256(MODEL_BYTES),
        format = "onnx",
        runtimeMinimum = PINNED_ONNX_RUNTIME_MOBILE_VERSION,
        redistributionStatus = "private-device-approved",
        inputs = listOf(MobileTensorContract("imu_window", listOf(1, 2))),
        outputs = listOf(MobileTensorContract("displacement", listOf(1, 2))),
    )

    private fun sha256(bytes: ByteArray): String = MessageDigest
        .getInstance("SHA-256")
        .digest(bytes)
        .joinToString("") { "%02x".format(it) }

    private companion object {
        val MODEL_BYTES = "not-a-real-model".encodeToByteArray()
    }
}
