package org.sih26168.app.model

import ai.onnxruntime.OnnxJavaType
import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import ai.onnxruntime.TensorInfo
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import java.util.LinkedHashMap
import java.util.LinkedHashSet
import kotlin.math.abs

const val PINNED_ONNX_RUNTIME_MOBILE_VERSION = "1.31.0"

data class MobileTensorContract(
    val name: String,
    val shape: List<Long>,
)

data class MobileModelContract(
    val schemaVersion: Int,
    val modelId: String,
    val modelSha256: String,
    val format: String,
    val opset: Int,
    val runtimeMinimum: String,
    val inputContract: String,
    val window: String,
    val normalization: String,
    val bounds: String,
    val trainingRun: String,
    val datasetManifest: String,
    val metrics: Map<String, Double>,
    val redistributionStatus: String,
    val exporterVersion: String,
    val candidateDescriptorSha256: String,
    val promotionEvidenceSha256: String,
    val inputs: List<MobileTensorContract>,
    val outputs: List<MobileTensorContract>,
)

data class FloatTensorData(
    val shape: List<Long>,
    val values: FloatArray,
)

data class MobileGoldenVector(
    val schemaVersion: Int,
    val generatorVersion: String,
    val modelId: String,
    val modelSha256: String,
    val modelManifestSha256: String,
    val candidateDescriptorSha256: String,
    val promotionEvidenceSha256: String,
    val manifestSha256: String,
    val inputArtifactSha256: Map<String, String>,
    val outputArtifactSha256: Map<String, String>,
    val inputs: Map<String, FloatTensorData>,
    val outputs: Map<String, FloatTensorData>,
)

internal data class MobileGoldenApproval(
    val goldenManifestSha256: String,
    val modelManifestSha256: String,
    val modelContractSha256: String,
    val modelId: String,
    val modelSha256: String,
    val candidateDescriptorSha256: String,
    val promotionEvidenceSha256: String,
    val inputArtifactSha256: Map<String, String>,
    val outputArtifactSha256: Map<String, String>,
    val inputTensorSha256: Map<String, String>,
    val outputTensorSha256: Map<String, String>,
)

enum class ModelDisabledReason {
    INVALID_CONTRACT,
    GOLDEN_VECTOR_INVALID,
    GOLDEN_VECTOR_MISMATCH,
    GOLDEN_VECTOR_UNTRUSTED,
    MODEL_HASH_MISMATCH,
    REDISTRIBUTION_NOT_APPROVED,
    RUNTIME_UNAVAILABLE,
    RUNTIME_TOO_OLD,
    SESSION_CONTRACT_MISMATCH,
}

sealed interface MobileModelLoadResult {
    data class Ready(
        val runtime: OnnxRuntimeMobile,
    ) : MobileModelLoadResult

    data class ModelDisabled(
        val reason: ModelDisabledReason,
        val detail: String,
    ) : MobileModelLoadResult
}

sealed interface MobileInferenceResult {
    data class Success(
        val outputs: Map<String, FloatTensorData>,
    ) : MobileInferenceResult

    data class ModelDisabled(
        val detail: String,
    ) : MobileInferenceResult
}

/**
 * Fail-closed ONNX Runtime Mobile boundary for C-17/I-19.
 *
 * Callers may supply only a separately approved model bundle. This class never discovers,
 * downloads, promotes, or silently substitutes model bytes.
 */
class OnnxRuntimeMobile private constructor(
    private val environment: OrtEnvironment,
    private val options: OrtSession.SessionOptions,
    private val session: OrtSession,
    val contract: MobileModelContract,
    val runtimeVersion: String,
) : AutoCloseable {
    @Synchronized
    fun run(inputs: Map<String, FloatTensorData>): MobileInferenceResult {
        val expectedNames = contract.inputs.map { it.name }
        if (inputs.keys != expectedNames.toSet()) {
            return MobileInferenceResult.ModelDisabled(
                "input names must exactly match the approved model contract",
            )
        }

        val tensors = LinkedHashMap<String, OnnxTensor>()
        return try {
            for (specification in contract.inputs) {
                val input = inputs.getValue(specification.name)
                val violation = validateTensorData(specification, input)
                if (violation != null) {
                    return MobileInferenceResult.ModelDisabled(violation)
                }
                val buffer = ByteBuffer
                    .allocateDirect(input.values.size * Float.SIZE_BYTES)
                    .order(ByteOrder.nativeOrder())
                    .asFloatBuffer()
                buffer.put(input.values)
                buffer.flip()
                tensors[specification.name] = OnnxTensor.createTensor(
                    environment,
                    buffer,
                    input.shape.toLongArray(),
                )
            }

            val requestedOutputs = contract.outputs
                .mapTo(LinkedHashSet()) { it.name }
            session.run(tensors, requestedOutputs).use { result ->
                val outputs = LinkedHashMap<String, FloatTensorData>()
                for (specification in contract.outputs) {
                    val value = result.get(specification.name).orElse(null)
                    if (value !is OnnxTensor) {
                        return MobileInferenceResult.ModelDisabled(
                            "runtime did not return tensor output ${specification.name}",
                        )
                    }
                    val info = value.info
                    if (info.type != OnnxJavaType.FLOAT ||
                        info.shape.toList() != specification.shape
                    ) {
                        return MobileInferenceResult.ModelDisabled(
                            "runtime output contract mismatch for ${specification.name}",
                        )
                    }
                    val values = value.floatBuffer?.let { outputBuffer ->
                        FloatArray(outputBuffer.remaining()).also(outputBuffer::get)
                    } ?: return MobileInferenceResult.ModelDisabled(
                        "runtime output ${specification.name} is not float32",
                    )
                    if (values.any { !it.isFinite() }) {
                        return MobileInferenceResult.ModelDisabled(
                            "runtime output ${specification.name} contains non-finite values",
                        )
                    }
                    outputs[specification.name] = FloatTensorData(
                        shape = specification.shape,
                        values = values,
                    )
                }
                MobileInferenceResult.Success(outputs)
            }
        } catch (exception: Exception) {
            MobileInferenceResult.ModelDisabled(
                "ONNX inference failed closed: ${exception.javaClass.simpleName}",
            )
        } finally {
            tensors.values.forEach { tensor ->
                runCatching { tensor.close() }
            }
        }
    }

    override fun close() {
        try {
            session.close()
        } finally {
            options.close()
        }
    }

    companion object {
        private const val MAX_MODEL_BYTES = 32 * 1024 * 1024
        internal const val GOLDEN_ABSOLUTE_TOLERANCE = 1e-5f
        private val SUPPORTED_ONNX_OPSETS = 13..21

        // Deliberately empty until a reviewed private WP-12.2 bundle digest is approved.
        // Adding an entry is a security-sensitive code change, never runtime configuration.
        private val TRUSTED_GOLDEN_APPROVALS: Map<String, MobileGoldenApproval> =
            emptyMap()

        private val APPROVED_REDISTRIBUTION = setOf(
            "redistribution-approved",
            "private-device-approved",
        )

        fun load(
            modelBytes: ByteArray,
            contract: MobileModelContract,
            goldenVector: MobileGoldenVector,
        ): MobileModelLoadResult {
            validateContract(contract, modelBytes.size)?.let { detail ->
                return MobileModelLoadResult.ModelDisabled(
                    ModelDisabledReason.INVALID_CONTRACT,
                    detail,
                )
            }
            val approval = TRUSTED_GOLDEN_APPROVALS[goldenVector.manifestSha256]
                ?: return MobileModelLoadResult.ModelDisabled(
                    ModelDisabledReason.GOLDEN_VECTOR_UNTRUSTED,
                    "golden manifest digest is not pinned by this app build",
                )
            validateGoldenVector(contract, goldenVector, approval)?.let { detail ->
                return MobileModelLoadResult.ModelDisabled(
                    ModelDisabledReason.GOLDEN_VECTOR_INVALID,
                    detail,
                )
            }
            if (contract.redistributionStatus !in APPROVED_REDISTRIBUTION) {
                return MobileModelLoadResult.ModelDisabled(
                    ModelDisabledReason.REDISTRIBUTION_NOT_APPROVED,
                    "model redistribution is not approved for device inclusion",
                )
            }
            if (sha256(modelBytes) != contract.modelSha256) {
                return MobileModelLoadResult.ModelDisabled(
                    ModelDisabledReason.MODEL_HASH_MISMATCH,
                    "model bytes do not match the approved I-19 digest",
                )
            }

            val environment = try {
                OrtEnvironment.getEnvironment()
            } catch (error: LinkageError) {
                return MobileModelLoadResult.ModelDisabled(
                    ModelDisabledReason.RUNTIME_UNAVAILABLE,
                    "ONNX Runtime native library is unavailable",
                )
            }
            val runtimeVersion = environment.version
            if (!runtimeAtLeast(runtimeVersion, contract.runtimeMinimum)) {
                return MobileModelLoadResult.ModelDisabled(
                    ModelDisabledReason.RUNTIME_TOO_OLD,
                    "runtime $runtimeVersion is older than ${contract.runtimeMinimum}",
                )
            }

            var openedOptions: OrtSession.SessionOptions? = null
            var openedSession: OrtSession? = null
            return try {
                val options = OrtSession.SessionOptions()
                openedOptions = options
                val session = environment.createSession(modelBytes, options)
                openedSession = session
                validateSessionContract(session, contract)?.let { detail ->
                    runCatching { session.close() }
                    runCatching { options.close() }
                    return MobileModelLoadResult.ModelDisabled(
                        ModelDisabledReason.SESSION_CONTRACT_MISMATCH,
                        detail,
                    )
                }
                val runtime = OnnxRuntimeMobile(
                    environment = environment,
                    options = options,
                    session = session,
                    contract = contract,
                    runtimeVersion = runtimeVersion,
                )
                when (val goldenResult = runtime.run(goldenVector.inputs)) {
                    is MobileInferenceResult.ModelDisabled -> {
                        runCatching { runtime.close() }
                        return MobileModelLoadResult.ModelDisabled(
                            ModelDisabledReason.GOLDEN_VECTOR_MISMATCH,
                            "golden inference failed closed: ${goldenResult.detail}",
                        )
                    }
                    is MobileInferenceResult.Success -> {
                        validateGoldenOutputs(
                            contract,
                            goldenVector.outputs,
                            goldenResult.outputs,
                        )?.let { detail ->
                            runCatching { runtime.close() }
                            return MobileModelLoadResult.ModelDisabled(
                                ModelDisabledReason.GOLDEN_VECTOR_MISMATCH,
                                detail,
                            )
                        }
                    }
                }
                MobileModelLoadResult.Ready(runtime)
            } catch (exception: Exception) {
                runCatching { openedSession?.close() }
                runCatching { openedOptions?.close() }
                MobileModelLoadResult.ModelDisabled(
                    ModelDisabledReason.RUNTIME_UNAVAILABLE,
                    "ONNX session creation failed closed: ${exception.javaClass.simpleName}",
                )
            } catch (error: LinkageError) {
                runCatching { openedSession?.close() }
                runCatching { openedOptions?.close() }
                MobileModelLoadResult.ModelDisabled(
                    ModelDisabledReason.RUNTIME_UNAVAILABLE,
                    "ONNX Runtime native library is unavailable",
                )
            }
        }

        internal fun validateContract(
            contract: MobileModelContract,
            modelSizeBytes: Int,
        ): String? {
            if (contract.schemaVersion != 1) return "unsupported I-19 schema version"
            if (contract.modelId.isBlank()) return "model ID must not be blank"
            if (!isSha256(contract.modelSha256)) {
                return "model SHA-256 must be lowercase hexadecimal"
            }
            if (contract.format != "onnx") return "model format must be onnx"
            if (contract.opset !in SUPPORTED_ONNX_OPSETS) {
                return "ONNX opset must be between 13 and 21"
            }
            val requiredIdentity = listOf(
                contract.inputContract,
                contract.window,
                contract.normalization,
                contract.bounds,
                contract.trainingRun,
                contract.datasetManifest,
                contract.exporterVersion,
            )
            if (requiredIdentity.any(String::isBlank)) {
                return "I-19 identity fields must not be blank"
            }
            if (contract.metrics.isEmpty() ||
                contract.metrics.any { (name, value) -> name.isBlank() || !value.isFinite() }
            ) {
                return "I-19 metrics must be a non-empty finite map"
            }
            if (!isSha256(contract.candidateDescriptorSha256) ||
                !isSha256(contract.promotionEvidenceSha256)
            ) {
                return "I-19 evidence hashes must be lowercase SHA-256"
            }
            if (parseVersion(contract.runtimeMinimum) == null) {
                return "runtime minimum must be a semantic version"
            }
            if (modelSizeBytes !in 1..MAX_MODEL_BYTES) {
                return "model size must be between 1 byte and $MAX_MODEL_BYTES bytes"
            }
            validateTensorContracts("input", contract.inputs)?.let { return it }
            validateTensorContracts("output", contract.outputs)?.let { return it }
            return null
        }

        internal fun validateGoldenVector(
            contract: MobileModelContract,
            goldenVector: MobileGoldenVector,
            approval: MobileGoldenApproval,
        ): String? {
            if (goldenVector.schemaVersion != 1) {
                return "unsupported golden-vector schema version"
            }
            if (goldenVector.generatorVersion != "wp12.2-v1") {
                return "unsupported golden-vector generator version"
            }
            val approvalHashes = listOf(
                approval.goldenManifestSha256,
                approval.modelManifestSha256,
                approval.modelContractSha256,
                approval.modelSha256,
                approval.candidateDescriptorSha256,
                approval.promotionEvidenceSha256,
            ) + approval.inputArtifactSha256.values +
                approval.outputArtifactSha256.values +
                approval.inputTensorSha256.values +
                approval.outputTensorSha256.values
            if (approvalHashes.any { !isSha256(it) }) {
                return "trusted golden approval contains a malformed digest"
            }
            if (goldenVector.manifestSha256 != approval.goldenManifestSha256 ||
                goldenVector.modelManifestSha256 != approval.modelManifestSha256 ||
                goldenVector.modelId != approval.modelId ||
                goldenVector.modelSha256 != approval.modelSha256 ||
                goldenVector.candidateDescriptorSha256 !=
                    approval.candidateDescriptorSha256 ||
                goldenVector.promotionEvidenceSha256 !=
                    approval.promotionEvidenceSha256
            ) {
                return "golden-vector identity does not match the trusted approval"
            }
            if (modelContractSha256(contract) != approval.modelContractSha256) {
                return "complete I-19 contract digest does not match the trusted approval"
            }
            if (contract.modelId != approval.modelId ||
                contract.modelSha256 != approval.modelSha256 ||
                contract.candidateDescriptorSha256 !=
                    approval.candidateDescriptorSha256 ||
                contract.promotionEvidenceSha256 !=
                    approval.promotionEvidenceSha256
            ) {
                return "I-19 identity does not match the trusted golden approval"
            }
            if (goldenVector.inputArtifactSha256 != approval.inputArtifactSha256 ||
                goldenVector.outputArtifactSha256 != approval.outputArtifactSha256
            ) {
                return "golden tensor artifact digests do not match the trusted approval"
            }
            if (goldenVector.inputArtifactSha256.keys != goldenVector.inputs.keys ||
                goldenVector.outputArtifactSha256.keys != goldenVector.outputs.keys
            ) {
                return "every golden tensor must have an approved artifact digest"
            }
            if (goldenVector.inputs.keys != contract.inputs.map { it.name }.toSet() ||
                goldenVector.inputs.keys != approval.inputTensorSha256.keys
            ) {
                return "golden input names must exactly match I-19 and the approval"
            }
            if (goldenVector.outputs.keys != contract.outputs.map { it.name }.toSet() ||
                goldenVector.outputs.keys != approval.outputTensorSha256.keys
            ) {
                return "golden output names must exactly match I-19 and the approval"
            }
            for (specification in contract.inputs) {
                val tensor = goldenVector.inputs.getValue(specification.name)
                validateTensorData(
                    specification,
                    tensor,
                    "golden input",
                )?.let { return it }
                if (tensorPayloadSha256(tensor) !=
                    approval.inputTensorSha256.getValue(specification.name)
                ) {
                    return "golden input payload digest mismatch for ${specification.name}"
                }
            }
            for (specification in contract.outputs) {
                val tensor = goldenVector.outputs.getValue(specification.name)
                validateTensorData(
                    specification,
                    tensor,
                    "golden output",
                )?.let { return it }
                if (tensorPayloadSha256(tensor) !=
                    approval.outputTensorSha256.getValue(specification.name)
                ) {
                    return "golden output payload digest mismatch for ${specification.name}"
                }
            }
            return null
        }

        internal fun validateGoldenOutputs(
            contract: MobileModelContract,
            expected: Map<String, FloatTensorData>,
            actual: Map<String, FloatTensorData>,
        ): String? {
            if (actual.keys != expected.keys) {
                return "runtime golden output names do not match the approved vector"
            }
            for (specification in contract.outputs) {
                val expectedTensor = expected.getValue(specification.name)
                val actualTensor = actual[specification.name]
                    ?: return "runtime omitted golden output ${specification.name}"
                if (actualTensor.shape != expectedTensor.shape ||
                    actualTensor.values.size != expectedTensor.values.size
                ) {
                    return "runtime golden output shape mismatch for ${specification.name}"
                }
                for (index in expectedTensor.values.indices) {
                    if (abs(actualTensor.values[index] - expectedTensor.values[index]) >
                        GOLDEN_ABSOLUTE_TOLERANCE
                    ) {
                        return "runtime golden output exceeds 1e-5 tolerance for " +
                            specification.name
                    }
                }
            }
            return null
        }

        private fun validateTensorContracts(
            label: String,
            contracts: List<MobileTensorContract>,
        ): String? {
            if (contracts.isEmpty()) return "$label contract must not be empty"
            if (contracts.map { it.name }.toSet().size != contracts.size) {
                return "$label names must be unique"
            }
            for (contract in contracts) {
                if (contract.name.isBlank()) return "$label name must not be blank"
                if (contract.shape.isEmpty() || contract.shape.any { it <= 0L }) {
                    return "$label ${contract.name} must have a fixed positive shape"
                }
                val elements = contract.shape.fold(1L) { total, dimension ->
                    if (total > Int.MAX_VALUE / dimension) return "$label tensor is too large"
                    total * dimension
                }
                if (elements > Int.MAX_VALUE) return "$label tensor is too large"
            }
            return null
        }

        private fun validateSessionContract(
            session: OrtSession,
            contract: MobileModelContract,
        ): String? {
            val inputViolation = validateRuntimeNodes(
                "input",
                session.inputInfo,
                contract.inputs,
            )
            if (inputViolation != null) return inputViolation
            return validateRuntimeNodes(
                "output",
                session.outputInfo,
                contract.outputs,
            )
        }

        private fun validateRuntimeNodes(
            label: String,
            nodes: Map<String, ai.onnxruntime.NodeInfo>,
            expected: List<MobileTensorContract>,
        ): String? {
            if (nodes.keys.toList() != expected.map { it.name }) {
                return "runtime $label names/order do not match I-19"
            }
            for (specification in expected) {
                val info = nodes.getValue(specification.name).info as? TensorInfo
                    ?: return "runtime $label ${specification.name} is not a tensor"
                if (info.type != OnnxJavaType.FLOAT ||
                    info.shape.toList() != specification.shape
                ) {
                    return "runtime $label ${specification.name} must be fixed float32"
                }
            }
            return null
        }

        private fun validateTensorData(
            contract: MobileTensorContract,
            tensor: FloatTensorData,
            label: String = "input",
        ): String? {
            if (tensor.shape != contract.shape) {
                return "$label ${contract.name} shape does not match I-19"
            }
            val expectedElements = contract.shape.fold(1L, Long::times)
            if (expectedElements != tensor.values.size.toLong()) {
                return "$label ${contract.name} element count does not match its shape"
            }
            if (tensor.values.any { !it.isFinite() }) {
                return "$label ${contract.name} contains non-finite values"
            }
            return null
        }

        internal fun runtimeAtLeast(actual: String, minimum: String): Boolean {
            val actualParts = parseVersion(actual) ?: return false
            val minimumParts = parseVersion(minimum) ?: return false
            return actualParts >= minimumParts
        }

        private fun parseVersion(value: String): Version? {
            val match = Regex("""^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$""").matchEntire(value)
                ?: return null
            return Version(
                match.groupValues[1].toIntOrNull() ?: return null,
                match.groupValues[2].toIntOrNull() ?: return null,
                match.groupValues[3].toIntOrNull() ?: return null,
            )
        }

        internal fun modelContractSha256(contract: MobileModelContract): String {
            val digest = MessageDigest.getInstance("SHA-256")
            digest.update("sih26168-i19-mobile-v1\u0000".toByteArray(Charsets.UTF_8))

            fun putLong(value: Long) {
                val bytes = ByteBuffer.allocate(Long.SIZE_BYTES)
                    .order(ByteOrder.BIG_ENDIAN)
                    .putLong(value)
                    .array()
                digest.update(bytes)
            }

            fun putString(value: String) {
                val bytes = value.toByteArray(Charsets.UTF_8)
                putLong(bytes.size.toLong())
                digest.update(bytes)
            }

            fun putTensorContracts(contracts: List<MobileTensorContract>) {
                putLong(contracts.size.toLong())
                for (tensor in contracts) {
                    putString(tensor.name)
                    putLong(tensor.shape.size.toLong())
                    tensor.shape.forEach(::putLong)
                }
            }

            putLong(contract.schemaVersion.toLong())
            putString(contract.modelId)
            putString(contract.modelSha256)
            putString(contract.format)
            putLong(contract.opset.toLong())
            putString(contract.runtimeMinimum)
            putString(contract.inputContract)
            putString(contract.window)
            putString(contract.normalization)
            putString(contract.bounds)
            putString(contract.trainingRun)
            putString(contract.datasetManifest)
            putLong(contract.metrics.size.toLong())
            for ((name, value) in contract.metrics.toSortedMap()) {
                putString(name)
                putLong(java.lang.Double.doubleToRawLongBits(value))
            }
            putString(contract.redistributionStatus)
            putString(contract.exporterVersion)
            putString(contract.candidateDescriptorSha256)
            putString(contract.promotionEvidenceSha256)
            putTensorContracts(contract.inputs)
            putTensorContracts(contract.outputs)
            return digest.digest().toHex()
        }

        internal fun tensorPayloadSha256(tensor: FloatTensorData): String {
            val digest = MessageDigest.getInstance("SHA-256")
            digest.update("sih26168-float32-v1\u0000".toByteArray(Charsets.UTF_8))
            val scratch = ByteBuffer.allocate(Long.SIZE_BYTES).order(ByteOrder.BIG_ENDIAN)
            scratch.putLong(tensor.shape.size.toLong())
            digest.update(scratch.array())
            for (dimension in tensor.shape) {
                scratch.clear()
                scratch.putLong(dimension)
                digest.update(scratch.array())
            }
            scratch.clear()
            scratch.putLong(tensor.values.size.toLong())
            digest.update(scratch.array())
            val floatBytes = ByteBuffer.allocate(Int.SIZE_BYTES).order(ByteOrder.BIG_ENDIAN)
            for (value in tensor.values) {
                floatBytes.clear()
                floatBytes.putInt(java.lang.Float.floatToRawIntBits(value))
                digest.update(floatBytes.array())
            }
            return digest.digest().toHex()
        }

        private fun isSha256(value: String): Boolean =
            value.matches(Regex("[0-9a-f]{64}"))

        private fun sha256(bytes: ByteArray): String = MessageDigest
            .getInstance("SHA-256")
            .digest(bytes)
            .toHex()

        private fun ByteArray.toHex(): String =
            joinToString("") { "%02x".format(it) }
    }
}

private data class Version(
    val major: Int,
    val minor: Int,
    val patch: Int,
) : Comparable<Version> {
    override fun compareTo(other: Version): Int = compareValuesBy(
        this,
        other,
        Version::major,
        Version::minor,
        Version::patch,
    )
}
