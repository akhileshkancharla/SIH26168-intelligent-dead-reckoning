package org.sih26168.s1logger

import android.os.StatFs
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedWriter
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStreamWriter
import java.security.MessageDigest
import java.util.UUID

class SessionWriter(private val sessionsRoot: File) {
    val sessionId: String = UUID.randomUUID().toString()
    val sessionDir = File(sessionsRoot, sessionId)
    private val chunkRecords = mutableListOf<JSONObject>()
    private var stream: FileOutputStream? = null
    private var writer: BufferedWriter? = null
    private var chunkIndex = 0
    private var chunkBytes = 0L
    private var sessionBytes = 0L
    private var closed = false

    init {
        check(sessionDir.mkdirs()) { "Cannot create session directory" }
        File(sessionDir, "INCOMPLETE").writeText("session not finalized\n")
        openChunk()
    }

    @Synchronized fun append(record: JSONObject) {
        check(!closed) { "Session is closed" }
        val line = record.toString() + "\n"
        val bytes = line.toByteArray(Charsets.UTF_8).size.toLong()
        ensureCapacity(bytes)
        writer!!.write(line)
        chunkBytes += bytes
        sessionBytes += bytes
        if (chunkBytes >= RecordingContract.CHUNK_MAX_BYTES) rotate()
    }

    @Synchronized fun flush() {
        writer?.flush()
        stream?.fd?.sync()
    }

    @Synchronized fun close(stopReason: String, extra: JSONObject): File {
        if (closed) return File(sessionDir, "session_manifest.json")
        finalizeChunk()
        closed = true
        val manifest = JsonUtil.objectOf(
            "schema_version" to RecordingContract.SCHEMA_VERSION,
            "session_id" to sessionId,
            "complete" to true,
            "stop_reason" to stopReason,
            "chunks" to JSONArray(chunkRecords),
            "total_log_bytes" to sessionBytes,
            "metadata" to extra,
        )
        val target = File(sessionDir, "session_manifest.json")
        atomicWrite(target, manifest.toString(2) + "\n")
        File(sessionDir, "INCOMPLETE").delete()
        return target
    }

    private fun ensureCapacity(nextBytes: Long) {
        val free = StatFs(sessionDir.absolutePath).availableBytes
        if (free - nextBytes < RecordingContract.MIN_FREE_BYTES) {
            throw IllegalStateException("storage_reserve_reached")
        }
        if (sessionBytes + nextBytes > RecordingContract.MAX_SESSION_BYTES) {
            throw IllegalStateException("session_size_limit_reached")
        }
    }

    private fun openChunk() {
        chunkIndex++
        val partial = File(sessionDir, "chunk_%05d.jsonl.partial".format(chunkIndex))
        stream = FileOutputStream(partial, true)
        writer = BufferedWriter(OutputStreamWriter(stream, Charsets.UTF_8), 64 * 1024)
        chunkBytes = partial.length()
    }

    private fun rotate() {
        finalizeChunk()
        openChunk()
    }

    private fun finalizeChunk() {
        writer?.flush()
        stream?.fd?.sync()
        writer?.close()
        writer = null
        stream = null
        val partial = File(sessionDir, "chunk_%05d.jsonl.partial".format(chunkIndex))
        if (!partial.exists()) return
        val final = File(sessionDir, "chunk_%05d.jsonl".format(chunkIndex))
        check(partial.renameTo(final)) { "Cannot finalize chunk" }
        chunkRecords += JsonUtil.objectOf(
            "path" to final.name,
            "size" to final.length(),
            "sha256" to sha256(final),
        )
    }

    companion object {
        fun findIncomplete(sessionsRoot: File): List<File> =
            sessionsRoot.listFiles()?.filter { File(it, "INCOMPLETE").exists() } ?: emptyList()

        fun recover(sessionDir: File): JSONObject {
            val chunks = JSONArray()
            sessionDir.listFiles()?.filter { it.name.startsWith("chunk_") }?.sortedBy { it.name }?.forEach { file ->
                if (file.name.endsWith(".partial")) {
                    val recovered = File(file.parentFile, file.name.removeSuffix(".partial"))
                    file.renameTo(recovered)
                }
            }
            sessionDir.listFiles()?.filter { it.name.endsWith(".jsonl") }?.sortedBy { it.name }?.forEach { file ->
                chunks.put(JsonUtil.objectOf("path" to file.name, "size" to file.length(), "sha256" to sha256(file)))
            }
            val manifest = JsonUtil.objectOf(
                "schema_version" to RecordingContract.SCHEMA_VERSION,
                "session_id" to sessionDir.name,
                "complete" to false,
                "stop_reason" to "recovered_after_incomplete_termination",
                "chunks" to chunks,
            )
            atomicWrite(File(sessionDir, "session_manifest.json"), manifest.toString(2) + "\n")
            File(sessionDir, "INCOMPLETE").delete()
            return manifest
        }

        fun sha256(file: File): String {
            val digest = MessageDigest.getInstance("SHA-256")
            file.inputStream().buffered().use { input ->
                val buffer = ByteArray(64 * 1024)
                while (true) {
                    val n = input.read(buffer)
                    if (n < 0) break
                    digest.update(buffer, 0, n)
                }
            }
            return digest.digest().joinToString("") { "%02x".format(it) }
        }

        private fun atomicWrite(target: File, content: String) {
            val temp = File(target.parentFile, target.name + ".tmp")
            FileOutputStream(temp).use { out ->
                out.write(content.toByteArray(Charsets.UTF_8))
                out.fd.sync()
            }
            check(temp.renameTo(target)) { "Cannot finalize ${target.name}" }
        }
    }
}
