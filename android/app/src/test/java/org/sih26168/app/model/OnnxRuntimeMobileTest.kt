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
        val golden = validGoldenVector()
        val violation = OnnxRuntimeMobile.validateGoldenVector(
            validContract(),
            golden.copy(modelId = "different-model"),
            validApproval(golden),
        )

        assertEquals(
            "golden-vector identity does not match the trusted approval",
            violation,
        )
    }

    @Test
    fun unpinnedGoldenManifestFailsBeforeRuntimeLoad() {
        val result = OnnxRuntimeMobile.load(
            MODEL_BYTES,
            validContract(),
            validGoldenVector(),
        )

        assertTrue(result is MobileModelLoadResult.ModelDisabled)
        assertEquals(
            ModelDisabledReason.GOLDEN_VECTOR_UNTRUSTED,
            (result as MobileModelLoadResult.ModelDisabled).reason,
        )
    }

    @Test
    fun tamperedGoldenArtifactOrPayloadFailsClosed() {
        val contract = validContract()
        val golden = validGoldenVector()
        val approval = validApproval(golden)
        val artifactViolation = OnnxRuntimeMobile.validateGoldenVector(
            contract,
            golden.copy(
                inputArtifactSha256 = mapOf("imu_window" to "9".repeat(64)),
            ),
            approval,
        )
        val payloadViolation = OnnxRuntimeMobile.validateGoldenVector(
            contract,
            golden.copy(
                inputs = mapOf(
                    "imu_window" to FloatTensorData(
                        listOf(1, 2),
                        floatArrayOf(1.0f, 99.0f),
                    ),
                ),
            ),
            approval,
        )
        val manifestViolation = OnnxRuntimeMobile.validateGoldenVector(
            contract,
            golden.copy(modelManifestSha256 = "8".repeat(64)),
            approval,
        )
        val missingArtifactViolation = OnnxRuntimeMobile.validateGoldenVector(
            contract,
            golden.copy(inputArtifactSha256 = emptyMap()),
            approval.copy(inputArtifactSha256 = emptyMap()),
        )

        assertTrue(artifactViolation!!.contains("artifact digests"))
        assertTrue(payloadViolation!!.contains("payload digest mismatch"))
        assertTrue(manifestViolation!!.contains("trusted approval"))
        assertTrue(missingArtifactViolation!!.contains("every golden tensor"))
    }

    @Test
    fun everySecurityRelevantI19MutationFailsTrustedDigest() {
        val contract = validContract()
        val golden = validGoldenVector()
        val approval = validApproval(golden, contract)
        val mutations = listOf(
            contract.copy(redistributionStatus = "redistribution-approved"),
            contract.copy(opset = 18),
            contract.copy(runtimeMinimum = "1.30.0"),
            contract.copy(normalization = "changed-normalization"),
            contract.copy(bounds = "changed-bounds"),
            contract.copy(inputContract = "changed-input-contract"),
            contract.copy(window = "changed-window"),
            contract.copy(trainingRun = "changed-training-run"),
            contract.copy(datasetManifest = "changed-dataset"),
            contract.copy(metrics = mapOf("held_out_rmse" to 2.0)),
            contract.copy(exporterVersion = "changed-exporter"),
            contract.copy(
                inputs = listOf(MobileTensorContract("imu_window", listOf(1, 3))),
            ),
            contract.copy(
                outputs = listOf(MobileTensorContract("displacement", listOf(1, 3))),
            ),
        )

        for (mutation in mutations) {
            assertEquals(
                "complete I-19 contract digest does not match the trusted approval",
                OnnxRuntimeMobile.validateGoldenVector(
                    mutation,
                    golden,
                    approval,
                ),
            )
        }
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
        modelManifestSha256 = "4".repeat(64),
        candidateDescriptorSha256 = "1".repeat(64),
        promotionEvidenceSha256 = "2".repeat(64),
        manifestSha256 = "3".repeat(64),
        inputArtifactSha256 = mapOf("imu_window" to "5".repeat(64)),
        outputArtifactSha256 = mapOf("displacement" to "6".repeat(64)),
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

    private fun validApproval(
        golden: MobileGoldenVector,
        contract: MobileModelContract = validContract(),
    ): MobileGoldenApproval = MobileGoldenApproval(
        goldenManifestSha256 = golden.manifestSha256,
        modelManifestSha256 = golden.modelManifestSha256,
        modelContractSha256 = OnnxRuntimeMobile.modelContractSha256(contract),
        modelId = golden.modelId,
        modelSha256 = golden.modelSha256,
        candidateDescriptorSha256 = golden.candidateDescriptorSha256,
        promotionEvidenceSha256 = golden.promotionEvidenceSha256,
        inputArtifactSha256 = golden.inputArtifactSha256,
        outputArtifactSha256 = golden.outputArtifactSha256,
        inputTensorSha256 = golden.inputs.mapValues { (_, tensor) ->
            OnnxRuntimeMobile.tensorPayloadSha256(tensor)
        },
        outputTensorSha256 = golden.outputs.mapValues { (_, tensor) ->
            OnnxRuntimeMobile.tensorPayloadSha256(tensor)
        },
    )

    private fun sha256(bytes: ByteArray): String = MessageDigest
        .getInstance("SHA-256")
        .digest(bytes)
        .joinToString("") { "%02x".format(it) }

    private companion object {
        val MODEL_BYTES = "not-a-real-model".encodeToByteArray()
    }
}
