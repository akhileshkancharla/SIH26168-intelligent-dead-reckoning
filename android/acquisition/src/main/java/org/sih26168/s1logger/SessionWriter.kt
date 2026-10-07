package org.sih26168.s1logger

import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/**
 * C-02 writer adapted from the immutable WP-02.1 S1 SessionWriter.
 * All I/O is serialized on one worker. Callers supply real I-18 metadata and
 * already validated stream records; this class does not calibrate or repair them.
 * Recovery is an explicit manual-launch operation, never an automatic restart.
 */
class SessionWriter(
    sessionsRoot: File,
    initialManifest: JSONObject,
    private val limits: Limits = Limits(),
    private val availableBytes: (File) -> Long = { it.usableSpace },
) : AutoCloseable {
    data class Limits(
        val chunkBytes: Long = 5L * 1024 * 1024,
        val sessionBytes: Long = 2L * 1024 * 1024 * 1024,
        val reserveBytes: Long = 100L * 1024 * 1024,
        val flushMillis: Long = 10_000,
    ) {
        init {
            require(chunkBytes in 1..Int.MAX_VALUE.toLong())
            require(sessionBytes >= chunkBytes && reserveBytes >= 0 && flushMillis > 0)
        }
    }

    private val manifest = JSONObject(initialManifest.toString())
    val sessionId: String = manifest.getString("session_id")
    val sessionDir: File = File(sessionsRoot, sessionId)
    private val worker = Executors.newSingleThreadScheduledExecutor { task ->
        Thread(task, "session-writer").apply { isDaemon = true }
    }
    private var output: FileOutputStream? = null
    private var partial: File? = null
    private var chunkSize = 0L
    private var totalSize = 0L
    private var closed = false
    private var failure: Exception? = null
    private val chunks = manifest.getJSONArray("chunks")

    init {
        try {
            validateManifest(manifest)
            require(manifest.getString("status") == "INCOMPLETE" && chunks.length() == 0)
            streamObjects(manifest).forEach {
                require(it.getLong("sample_count") == 0L && it.isNull("first_sequence") && it.isNull("last_sequence"))
            }
            require(manifest.getJSONObject("loss_counts").let { counts ->
                counts.keys().asSequence().all { counts.getLong(it) == 0L }
            })
            require(sessionsRoot.isDirectory || sessionsRoot.mkdirs())
            require(!Files.isSymbolicLink(sessionsRoot.toPath()))
            require(Files.isSameFile(sessionsRoot.toPath(), sessionsRoot.canonicalFile.toPath()))
            check(sessionDir.mkdir()) { "Session already exists or cannot be created" }
            io {
                // Written before any data: recovery never invents boot/build/device metadata.
                atomicWrite(File(sessionDir, CONTEXT), manifest.toString())
                atomicWrite(File(sessionDir, MARKER), "unfinished\n")
            }
            worker.scheduleWithFixedDelay({
                try { sync() } catch (error: Exception) { failure = error }
            }, limits.flushMillis, limits.flushMillis, TimeUnit.MILLISECONDS)
        } catch (error: Exception) {
            worker.shutdownNow()
            throw error
        }
    }

    /** Blocks producers instead of silently dropping records into an unbounded queue. */
    @Synchronized fun append(record: JSONObject) {
        check(!closed) { "Session is closed" }
        val snapshot = JSONObject(record.toString())
        io {
            check(failure == null) { "Writer failed; only diagnostic finalization is allowed" }
            try {
                val stream = recordStream(manifest, snapshot)
                val bytes = (snapshot.toString() + "\n").toByteArray(Charsets.UTF_8)
                require(bytes.size.toLong() <= limits.chunkBytes) { "Record exceeds chunk bound" }
                check(bytes.size.toLong() <= limits.sessionBytes - totalSize) { "Session size limit reached" }
                check(availableBytes(sessionDir) - bytes.size >= limits.reserveBytes) { "Storage reserve reached" }
                if (chunkSize + bytes.size > limits.chunkBytes) finalizeChunk()
                if (output == null) {
                    partial = File(sessionDir, chunkName(chunks.length() + 1) + ".partial")
                    check(partial!!.createNewFile())
                    output = FileOutputStream(partial!!)
                }
                output!!.write(bytes)
                chunkSize += bytes.size
                totalSize += bytes.size
                countRecord(manifest, stream, snapshot.getLong("sequence"))
            } catch (error: Exception) {
                failure = error
                throw error
            }
        }
    }

    @Synchronized fun flush() {
        check(!closed)
        io { try { sync() } catch (error: Exception) { failure = error; throw error } }
    }

    /** Explicit end of acquisition; supplied loss counts are observed values, not estimates. */
    @Synchronized fun finish(lossCounts: Map<String, Long> = emptyMap()): File {
        check(!closed) { "Session is closed" }
        return try {
            io {
                val losses = manifest.getJSONObject("loss_counts")
                lossCounts.forEach { (id, count) ->
                    require(losses.has(id) && count >= losses.getLong(id))
                    losses.put(id, count)
                }
                finalizeChunk()
                val degraded = failure != null || losses.keys().asSequence().any { losses.getLong(it) > 0 }
                manifest.put("status", when {
                    degraded -> "EVIDENCE_DEGRADED"
                    chunks.length() == 0 -> "INCOMPLETE"
                    else -> "COMPLETE"
                })
                validateManifest(manifest)
                verifyChunks(sessionDir, manifest)
                val target = File(sessionDir, MANIFEST)
                atomicWrite(target, manifest.toString(2) + "\n")
                check(File(sessionDir, MARKER).delete())
                target
            }
        } finally {
            closed = true
            // On failure, leave context, marker and partial bytes for manual recovery.
            try { io { output?.close(); output = null } } finally { worker.shutdownNow() }
        }
    }

    /** Abandon without claiming a complete session (e.g. caller cancellation). */
    @Synchronized override fun close() {
        if (closed) return
        try { io { try { sync() } finally { output?.close(); output = null } } }
        finally { closed = true; worker.shutdownNow() }
    }

    private fun sync() { output?.fd?.sync() }

    private fun finalizeChunk() {
        val file = partial ?: return
        sync()
        output?.close()
        output = null
        val target = File(sessionDir, file.name.removeSuffix(".partial"))
        check(!target.exists())
        Files.move(file.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE)
        chunks.put(chunkEntry(target))
        partial = null
        chunkSize = 0
    }

    private fun <T> io(block: () -> T): T {
        val task = worker.submit<T> { block() }
        var interrupted = false
        try {
            while (true) {
                try { return task.get() }
                catch (_: InterruptedException) { interrupted = true }
                catch (error: java.util.concurrent.ExecutionException) { throw (error.cause ?: error) }
            }
        } finally {
            // Do not release producer serialization while an interrupted call still writes.
            if (interrupted) Thread.currentThread().interrupt()
        }
    }

    companion object {
        private const val CONTEXT = "session_context.json"
        private const val MANIFEST = "session_manifest.json"
        private const val MARKER = "INCOMPLETE"
        private val identifier = Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,255}")
        private val hash = Regex("[0-9a-f]{64}")
        private val chunkPattern = Regex("chunk_[0-9]{5,}\\.jsonl(?:\\.partial)?")
        private fun chunkName(index: Int) = String.format(Locale.ROOT, "chunk_%05d.jsonl", index)
        private fun streamObjects(m: JSONObject) = (0 until m.getJSONArray("streams").length())
            .map { m.getJSONArray("streams").getJSONObject(it) }
        private fun keys(o: JSONObject) = o.keys().asSequence().toSet()
        private fun exact(o: JSONObject, vararg names: String) { require(keys(o) == names.toSet()) }
        private fun id(value: String) { require(identifier.matches(value)) }
        private fun integer(o: JSONObject, key: String): Long {
            val value = o.get(key)
            require(value is Int || value is Long) { "$key must be an integer" }
            return (value as Number).toLong().also { require(it >= 0) }
        }
        private fun text(o: JSONObject, key: String): String = (o.get(key) as? String)
            ?.also { require(it.isNotEmpty()) } ?: error("$key must be a string")

        /** Schema v1 plus identity, sequence, uniqueness and declared-stream invariants. */
        internal fun validateManifest(m: JSONObject) {
            exact(m, "schema_version", "session_id", "status", "clock_id", "boot_id", "app_build",
                "device_profile", "streams", "chunks", "loss_counts", "config_hash", "privacy_class")
            require(integer(m, "schema_version") == 1L)
            listOf("session_id", "clock_id", "boot_id").forEach { id(text(m, it)) }
            require(text(m, "status") in setOf("COMPLETE", "INCOMPLETE", "EVIDENCE_DEGRADED"))
            require(hash.matches(text(m, "config_hash")))
            require(text(m, "privacy_class") in setOf("PRIVATE_OFFLINE_ONLY", "SYNTHETIC_NON_PRIVATE"))
            m.getJSONObject("app_build").let {
                exact(it, "version_name", "version_code", "git_commit", "build_type")
                text(it, "version_name"); require(integer(it, "version_code") > 0)
                require(Regex("[0-9a-f]{40}").matches(text(it, "git_commit")))
                require(text(it, "build_type") in setOf("DEBUG", "RELEASE"))
            }
            m.getJSONObject("device_profile").let {
                exact(it, "profile_id", "manufacturer", "model", "sdk_int", "hardware")
                id(text(it, "profile_id"))
                listOf("manufacturer", "model", "hardware").forEach { k -> if (!it.isNull(k)) text(it, k) }
                if (!it.isNull("sdk_int")) require(integer(it, "sdk_int") > 0)
            }
            val streams = streamObjects(m)
            require(streams.isNotEmpty())
            val ids = streams.map { text(it, "stream_id") }
            require(ids.toSet().size == ids.size)
            streams.forEach {
                exact(it, "stream_id", "interface_id", "clock_id", "coordinate_frame", "units",
                    "sample_count", "first_sequence", "last_sequence")
                id(text(it, "stream_id")); id(text(it, "clock_id"))
                require(it.getString("clock_id") == m.getString("clock_id"))
                require(text(it, "interface_id") in setOf("I-01", "I-02", "I-04", "I-07", "I-13", "I-14", "I-15", "I-16"))
                require(text(it, "coordinate_frame").length <= 128)
                it.getJSONObject("units").let { units -> keys(units).forEach { k -> id(k); text(units, k) } }
                val count = integer(it, "sample_count")
                if (count == 0L) require(it.isNull("first_sequence") && it.isNull("last_sequence"))
                else {
                    val first = integer(it, "first_sequence"); val last = integer(it, "last_sequence")
                    require(last >= first && count - 1 <= last - first)
                }
            }
            m.getJSONObject("loss_counts").let { losses ->
                require(keys(losses) == ids.toSet())
                keys(losses).forEach {
                    val count = integer(losses, it)
                    if (m.getString("status") == "COMPLETE") require(count == 0L)
                }
            }
            val paths = mutableSetOf<String>()
            val chunks = m.getJSONArray("chunks")
            if (m.getString("status") == "COMPLETE") require(chunks.length() > 0)
            for (i in 0 until chunks.length()) {
                val c = chunks.getJSONObject(i)
                exact(c, "path", "size_bytes", "sha256")
                val path = text(c, "path")
                // This writer deliberately emits only flat, numbered chunk paths.
                require(chunkPattern.matches(path) && !path.endsWith(".partial") && paths.add(path))
                require(path == chunkName(i + 1))
                integer(c, "size_bytes"); require(hash.matches(text(c, "sha256")))
            }
        }

        private fun recordStream(m: JSONObject, record: JSONObject): JSONObject {
            require(text(record, "session_id") == m.getString("session_id"))
            val stream = streamObjects(m).single { it.getString("stream_id") == text(record, "stream_id") }
            val sequence = integer(record, "sequence")
            if (!stream.isNull("last_sequence")) require(sequence > stream.getLong("last_sequence"))
            return stream
        }
        private fun countRecord(m: JSONObject, stream: JSONObject, sequence: Long) {
            if (!stream.isNull("last_sequence")) {
                val gap = sequence - stream.getLong("last_sequence") - 1
                val losses = m.getJSONObject("loss_counts")
                val id = stream.getString("stream_id")
                losses.put(id, Math.addExact(losses.getLong(id), gap))
            }
            if (stream.isNull("first_sequence")) stream.put("first_sequence", sequence)
            stream.put("last_sequence", sequence)
            stream.put("sample_count", Math.addExact(stream.getLong("sample_count"), 1))
        }

        fun findIncomplete(root: File): List<File> = root.listFiles()?.filter {
            it.isDirectory && !Files.isSymbolicLink(it.toPath()) && File(it, MARKER).isFile
        }?.sortedBy { it.name } ?: emptyList()

        /** Call only for abandoned sessions after acquisition has stopped, on manual launch.
         * Torn/malformed lines are retained byte-for-byte and make evidence degraded.
         * Legacy sessions without this writer's context are rejected, never upgraded.
         */
        fun recover(sessionDir: File, limits: Limits = Limits()): JSONObject {
            require(!Files.isSymbolicLink(sessionDir.toPath()) && File(sessionDir, MARKER).isFile)
            // A crash after publishing the manifest but before deleting the marker must
            // not downgrade a verified completed session or reorder its declared chunks.
            val published = File(sessionDir, MANIFEST)
            if (published.exists()) {
                val m = readJson(published)
                validateManifest(m)
                require(m.getString("session_id") == sessionDir.name)
                verifyChunks(sessionDir, m)
                check(File(sessionDir, MARKER).delete())
                return m
            }
            val m = readJson(File(sessionDir, CONTEXT))
            validateManifest(m)
            require(m.getString("session_id") == sessionDir.name && m.getString("status") == "INCOMPLETE")
            require(m.getJSONArray("chunks").length() == 0)
            streamObjects(m).forEach {
                require(it.getLong("sample_count") == 0L && it.isNull("first_sequence") && it.isNull("last_sequence"))
            }
            val files = sessionDir.listFiles()!!.filter { chunkPattern.matches(it.name) }.sortedBy { it.name }
            var degraded = false
            var total = 0L
            files.forEachIndexed { index, file ->
                val name = chunkName(index + 1)
                require(file.name == name || file.name == "$name.partial") { "Ambiguous or missing chunk order" }
                require(file.isFile && !Files.isSymbolicLink(file.toPath()))
                require(file.length() <= limits.chunkBytes && file.length() <= limits.sessionBytes - total)
                total += file.length()
                // Bounded scan: at most the configured chunk size is held at a time.
                val bytes = file.readBytes()
                var start = 0
                bytes.forEachIndexed { offset, byte ->
                    if (byte == 10.toByte()) {
                        try {
                            val decoder = Charsets.UTF_8.newDecoder()
                            val line = decoder.decode(java.nio.ByteBuffer.wrap(bytes, start, offset - start)).toString()
                            val record = parseJson(line)
                            countRecord(m, recordStream(m, record), integer(record, "sequence"))
                        } catch (_: Exception) { degraded = true }
                        start = offset + 1
                    }
                }
                if (start != bytes.size) degraded = true
                val target = File(sessionDir, name)
                if (file != target) {
                    check(!target.exists())
                    FileOutputStream(file, true).use { it.fd.sync() }
                    Files.move(file.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE)
                }
                m.getJSONArray("chunks").put(chunkEntry(target))
            }
            m.put("status", if (degraded) "EVIDENCE_DEGRADED" else "INCOMPLETE")
            validateManifest(m)
            atomicWrite(published, m.toString(2) + "\n")
            check(File(sessionDir, MARKER).delete())
            return m
        }

        /** Explicit caller-selected session and destination. Caller owns/ closes destination.
         * Only a COMPLETE session is eligible. Any exception means discard the output ZIP.
         */
        fun exportSession(sessionDir: File, destination: OutputStream) {
            require(!File(sessionDir, MARKER).exists())
            val manifestFile = File(sessionDir, MANIFEST)
            require(safeFile(manifestFile).length() <= 16L * 1024 * 1024)
            val bytes = manifestFile.readBytes()
            val m = parseJson(Charsets.UTF_8.newDecoder().decode(java.nio.ByteBuffer.wrap(bytes)).toString())
            validateManifest(m)
            require(m.getString("status") == "COMPLETE" && m.getString("session_id") == sessionDir.name)
            verifyChunks(sessionDir, m)
            val zip = ZipOutputStream(object : java.io.FilterOutputStream(destination) {
                override fun close() { flush() }
            })
            zip.use {
                val chunks = m.getJSONArray("chunks")
                for (i in 0 until chunks.length()) {
                    val c = chunks.getJSONObject(i)
                    zip.putNextEntry(ZipEntry(c.getString("path")))
                    val digest = MessageDigest.getInstance("SHA-256")
                    var size = 0L
                    safeFile(File(sessionDir, c.getString("path"))).inputStream().use { input ->
                        val buffer = ByteArray(64 * 1024)
                        while (true) {
                            val n = input.read(buffer)
                            if (n < 0) break
                            size += n
                            check(size <= c.getLong("size_bytes"))
                            digest.update(buffer, 0, n); zip.write(buffer, 0, n)
                        }
                    }
                    check(size == c.getLong("size_bytes") && hex(digest.digest()) == c.getString("sha256"))
                    zip.closeEntry()
                }
                zip.putNextEntry(ZipEntry(MANIFEST)); zip.write(bytes); zip.closeEntry()
            }
        }

        private fun parseJson(text: String): JSONObject {
            val tokens = org.json.JSONTokener(text)
            val value = JSONObject(tokens)
            require(tokens.nextClean() == '\u0000') { "Trailing JSON data" }
            return value
        }

        private fun readJson(file: File): JSONObject {
            require(safeFile(file).length() <= 16L * 1024 * 1024) { "Metadata exceeds read bound" }
            return parseJson(Charsets.UTF_8.newDecoder().decode(java.nio.ByteBuffer.wrap(file.readBytes())).toString())
        }
        private fun safeFile(file: File): File {
            require(file.isFile && !Files.isSymbolicLink(file.toPath()))
            require(Files.isSameFile(file.toPath(), file.canonicalFile.toPath())) { "Symlink path is not evidence" }
            return file
        }
        private fun chunkEntry(file: File) = JSONObject().put("path", file.name)
            .put("size_bytes", file.length()).put("sha256", sha256(file))
        private fun verifyChunks(dir: File, m: JSONObject) {
            val chunks = m.getJSONArray("chunks")
            for (i in 0 until chunks.length()) {
                val c = chunks.getJSONObject(i)
                val file = safeFile(File(dir, c.getString("path")))
                check(file.length() == c.getLong("size_bytes") && sha256(file) == c.getString("sha256"))
            }
        }
        fun sha256(file: File): String {
            val digest = MessageDigest.getInstance("SHA-256")
            safeFile(file).inputStream().use { input ->
                val buffer = ByteArray(64 * 1024)
                while (true) { val n = input.read(buffer); if (n < 0) break; digest.update(buffer, 0, n) }
            }
            return hex(digest.digest())
        }
        private fun hex(bytes: ByteArray) = bytes.joinToString("") { "%02x".format(it) }
        private fun atomicWrite(target: File, content: String) {
            val temp = File(target.parentFile, target.name + ".tmp")
            require(!Files.isSymbolicLink(temp.toPath()))
            FileOutputStream(temp).use { it.write(content.toByteArray(Charsets.UTF_8)); it.fd.sync() }
            Files.move(temp.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
        }
    }
}
