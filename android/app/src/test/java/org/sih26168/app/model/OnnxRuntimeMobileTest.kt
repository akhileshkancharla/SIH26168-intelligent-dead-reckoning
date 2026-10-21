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
    fun incompleteI19IdentityFailsClosed() {
        val violation = OnnxRuntimeMobile.validateContract(
            validContract().copy(metrics = emptyMap()),
            modelSizeBytes = MODEL_BYTES.size,
        )

        assertEquals("I-19 metrics must be a non-empty finite map", violation)
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
    fun opsetOutsideApprovedRangeFailsClosed() {
        val tooOld = OnnxRuntimeMobile.validateContract(
            validContract().copy(opset = 12),
            modelSizeBytes = MODEL_BYTES.size,
        )
        val tooNew = OnnxRuntimeMobile.validateContract(
            validContract().copy(opset = 22),
            modelSizeBytes = MODEL_BYTES.size,
        )

        assertEquals("ONNX opset must be between 13 and 21", tooOld)
        assertEquals("ONNX opset must be between 13 and 21", tooNew)
    }

    @Test
    fun goldenVectorIdentityMustMatchI19() {
        val violation = OnnxRuntimeMobile.validateGoldenVector(
            validContract(),
            validGoldenVector().copy(modelId = "different-model"),
        )

        assertEquals("golden-vector identity does not match I-19", violation)
    }

    @Test
    fun goldenParityUsesRequiredAbsoluteTolerance() {
        val contract = validContract()
        val expected = validGoldenVector().outputs
        val withinTolerance = mapOf(
            "displacement" to FloatTensorData(
                listOf(1, 2),
                floatArrayOf(2.000009f, 4.0f),
            ),
        )
        val outsideTolerance = mapOf(
            "displacement" to FloatTensorData(
                listOf(1, 2),
                floatArrayOf(2.00002f, 4.0f),
            ),
        )

        assertNull(
            OnnxRuntimeMobile.validateGoldenOutputs(
                contract,
                expected,
                withinTolerance,
            ),
        )
        assertTrue(
            OnnxRuntimeMobile.validateGoldenOutputs(
                contract,
                expected,
                outsideTolerance,
            )!!.contains("exceeds 1e-5 tolerance"),
        )
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
        opset = 17,
        runtimeMinimum = PINNED_ONNX_RUNTIME_MOBILE_VERSION,
        inputContract = "fixed float32 IMU window",
        window = "one immutable window",
        normalization = "approved-normalization-id",
        bounds = "bounded displacement",
        trainingRun = "immutable-training-run",
        datasetManifest = "immutable-dataset-manifest",
        metrics = mapOf("held_out_rmse" to 1.0),
        redistributionStatus = "private-device-approved",
        exporterVersion = "wp12.1-v1",
        candidateDescriptorSha256 = "1".repeat(64),
        promotionEvidenceSha256 = "2".repeat(64),
        inputs = listOf(MobileTensorContract("imu_window", listOf(1, 2))),
        outputs = listOf(MobileTensorContract("displacement", listOf(1, 2))),
    )

    private fun validGoldenVector(): MobileGoldenVector = MobileGoldenVector(
        schemaVersion = 1,
        generatorVersion = "wp12.2-v1",
        modelId = "approved-model",
        modelSha256 = sha256(MODEL_BYTES),
        candidateDescriptorSha256 = "1".repeat(64),
        promotionEvidenceSha256 = "2".repeat(64),
        manifestSha256 = "3".repeat(64),
        inputs = mapOf(
            "imu_window" to FloatTensorData(
                listOf(1, 2),
                floatArrayOf(1.0f, 2.0f),
            ),
        ),
        outputs = mapOf(
            "displacement" to FloatTensorData(
                listOf(1, 2),
                floatArrayOf(2.0f, 4.0f),
            ),
        ),
    )

    private fun sha256(bytes: ByteArray): String = MessageDigest
        .getInstance("SHA-256")
        .digest(bytes)
        .joinToString("") { "%02x".format(it) }

    private companion object {
        val MODEL_BYTES = "not-a-real-model".encodeToByteArray()
    }
}
