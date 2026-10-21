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

enum class ModelDisabledReason {
    INVALID_CONTRACT,
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
            tensors.values.forEach(OnnxTensor::close)
        }
    }

    override fun close() {
        session.close()
        options.close()
    }

    companion object {
        private const val MAX_MODEL_BYTES = 32 * 1024 * 1024
        private val APPROVED_REDISTRIBUTION = setOf(
            "redistribution-approved",
            "private-device-approved",
        )

        fun load(
            modelBytes: ByteArray,
            contract: MobileModelContract,
        ): MobileModelLoadResult {
            validateContract(contract, modelBytes.size)?.let { detail ->
                return MobileModelLoadResult.ModelDisabled(
                    ModelDisabledReason.INVALID_CONTRACT,
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

            val options = OrtSession.SessionOptions()
            var openedSession: OrtSession? = null
            return try {
                val session = environment.createSession(modelBytes, options)
                openedSession = session
                validateSessionContract(session, contract)?.let { detail ->
                    session.close()
                    options.close()
                    return MobileModelLoadResult.ModelDisabled(
                        ModelDisabledReason.SESSION_CONTRACT_MISMATCH,
                        detail,
                    )
                }
                MobileModelLoadResult.Ready(
                    OnnxRuntimeMobile(
                        environment = environment,
                        options = options,
                        session = session,
                        contract = contract,
                        runtimeVersion = runtimeVersion,
                    ),
                )
            } catch (exception: Exception) {
                openedSession?.close()
                options.close()
                MobileModelLoadResult.ModelDisabled(
                    ModelDisabledReason.RUNTIME_UNAVAILABLE,
                    "ONNX session creation failed closed: ${exception.javaClass.simpleName}",
                )
            } catch (error: LinkageError) {
                openedSession?.close()
                options.close()
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
            if (contract.opset <= 0) return "ONNX opset must be positive"
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
        ): String? {
            if (tensor.shape != contract.shape) {
                return "input ${contract.name} shape does not match I-19"
            }
            val expectedElements = contract.shape.fold(1L, Long::times)
            if (expectedElements != tensor.values.size.toLong()) {
                return "input ${contract.name} element count does not match its shape"
            }
            if (tensor.values.any { !it.isFinite() }) {
                return "input ${contract.name} contains non-finite values"
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

        private fun isSha256(value: String): Boolean =
            value.matches(Regex("[0-9a-f]{64}"))

        private fun sha256(bytes: ByteArray): String = MessageDigest
            .getInstance("SHA-256")
            .digest(bytes)
            .joinToString("") { "%02x".format(it) }
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
