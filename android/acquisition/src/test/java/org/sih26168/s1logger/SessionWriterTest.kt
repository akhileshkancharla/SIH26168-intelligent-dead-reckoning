package org.sih26168.s1logger

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.zip.ZipInputStream

class SessionWriterTest {
    @get:Rule val temp = TemporaryFolder()
    private fun initial(id: String = "synthetic-session") = JSONObject("""
        {"schema_version":1,"session_id":"$id","status":"INCOMPLETE",
         "clock_id":"CLOCK_BOOTTIME","boot_id":"synthetic-boot",
         "app_build":{"version_name":"test","version_code":1,
           "git_commit":"0123456789abcdef0123456789abcdef01234567","build_type":"DEBUG"},
         "device_profile":{"profile_id":"synthetic","manufacturer":null,
           "model":null,"sdk_int":null,"hardware":null},
         "streams":[{"stream_id":"imu","interface_id":"I-01","clock_id":"CLOCK_BOOTTIME",
           "coordinate_frame":"ANDROID_SENSOR_BODY","units":{"accelerometer":"m/s^2"},
           "sample_count":0,"first_sequence":null,"last_sequence":null}],
         "chunks":[],"loss_counts":{"imu":0},
         "config_hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
         "privacy_class":"SYNTHETIC_NON_PRIVATE"}
    """.trimIndent())
    private fun record(sequence: Long = 0) = JSONObject().put("schema_version", 1)
        .put("evidence_id", "synthetic-$sequence").put("session_id", "synthetic-session")
        .put("stream_id", "imu").put("sequence", sequence)
        .put("source_timestamp_ns", 1_000_000L + sequence).put("arrival_elapsed_realtime_ns", 1_000_100L + sequence)
        .put("sensor_type", "ACCELEROMETER").put("values", JSONArray(listOf(0.0, 0.0, 9.81)))
        .put("accuracy", 3).put("source_metadata", JSONObject().put("android_sensor_type", 1)
            .put("sensor_name", "Synthetic").put("vendor", "Fixture").put("version", 1))
    private fun limits(chunk: Long = 1024, session: Long = 8192, reserve: Long = 0) =
        SessionWriter.Limits(chunk, session, reserve, 20)
    private fun writer(limits: SessionWriter.Limits = limits()) = SessionWriter(temp.root, initial(), limits)
    private fun manifest(file: File) = JSONObject(file.readText())
    private fun fails(block: () -> Unit) {
        try { block(); fail("Expected rejection") } catch (expected: Exception) { /* expected */ }
    }
    private fun evidence(name: String, manifest: JSONObject) {
        System.getProperty("wp024.evidenceDir")?.let {
            val dir = File(it); check(dir.isDirectory || dir.mkdirs())
            File(dir, "$name.json").writeText(manifest.toString(2))
        }
    }

    @Test fun finalizationPreservesRecordsHashesOrderAndMetadata() {
        val w = writer(limits(chunk = 400))
        for (n in 0L..2L) w.append(record(n))
        val m = manifest(w.finish())
        assertEquals("COMPLETE", m.getString("status"))
        assertEquals(3, m.getJSONArray("chunks").length())
        for (i in 0..2) {
            val c = m.getJSONArray("chunks").getJSONObject(i)
            val f = File(w.sessionDir, c.getString("path"))
            assertTrue(f.length() <= 400)
            assertEquals(f.length(), c.getLong("size_bytes"))
            assertEquals(SessionWriter.sha256(f), c.getString("sha256"))
            assertEquals(i.toLong(), JSONObject(f.readText()).getLong("sequence"))
        }
        val s = m.getJSONArray("streams").getJSONObject(0)
        assertEquals(3, s.getInt("sample_count")); assertEquals(0, s.getInt("first_sequence"))
        assertEquals(2, s.getInt("last_sequence"))
        assertEquals("synthetic-boot", m.getString("boot_id"))
        assertFalse(File(w.sessionDir, "INCOMPLETE").exists())
        evidence("complete", m)
    }
    @Test fun exactChunkBoundaryDoesNotCreateEmptyTail() {
        val size = (record().toString() + "\n").toByteArray().size.toLong()
        val w = writer(limits(size)); w.append(record())
        val m = manifest(w.finish())
        assertEquals(1, m.getJSONArray("chunks").length())
        assertEquals(size, m.getJSONArray("chunks").getJSONObject(0).getLong("size_bytes"))
    }
    @Test fun oversizeRecordPreventsComplete() {
        val w = writer(limits(32)); fails { w.append(record()) }
        assertEquals("EVIDENCE_DEGRADED", manifest(w.finish()).getString("status"))
    }
    @Test fun sessionBoundPreventsCompleteAndRetainsAcceptedBytes() {
        val w = writer(limits(400, 400)); w.append(record())
        fails { w.append(record(1)) }
        val m = manifest(w.finish())
        assertEquals("EVIDENCE_DEGRADED", m.getString("status"))
        assertEquals(1, m.getJSONArray("streams").getJSONObject(0).getInt("sample_count"))
    }
    @Test fun reserveFailureIsDiagnostic() {
        val w = SessionWriter(temp.root, initial(), limits(reserve = 100), availableBytes = { 100 })
        fails { w.append(record()) }
        assertEquals("EVIDENCE_DEGRADED", manifest(w.finish()).getString("status"))
    }
    @Test fun emptySessionCannotBeComplete() {
        assertEquals("INCOMPLETE", manifest(writer().finish()).getString("status"))
    }
    @Test fun sequenceGapAndReportedLossCannotBeComplete() {
        val w = writer(); w.append(record()); w.append(record(2))
        val m = manifest(w.finish(mapOf("imu" to 1)))
        assertEquals("EVIDENCE_DEGRADED", m.getString("status"))
        assertEquals(1, m.getJSONObject("loss_counts").getInt("imu"))
    }
    @Test fun observedLossCannotBeErased() {
        val w = writer(); w.append(record()); w.append(record(2))
        fails { w.finish(mapOf("imu" to 0)) }
        assertTrue(File(w.sessionDir, "INCOMPLETE").exists())
    }
    @Test fun duplicateOrWrongIdentityRejectsComplete() {
        val w = writer(); w.append(record())
        fails { w.append(record()) }
        assertEquals("EVIDENCE_DEGRADED", manifest(w.finish()).getString("status"))
        val other = SessionWriter(temp.root, initial("other"), limits())
        fails { other.append(record()) }
        assertEquals("EVIDENCE_DEGRADED", manifest(other.finish()).getString("status"))
    }
    @Test fun metadataMustBeExplicitAndCopied() {
        val m = initial(); m.remove("boot_id")
        fails { SessionWriter(temp.root, m, limits()) }
        val valid = initial(); val w = SessionWriter(temp.root, valid, limits())
        valid.put("boot_id", "mutated"); w.append(record())
        assertEquals("synthetic-boot", manifest(w.finish()).getString("boot_id"))
    }
    @Test fun malformedMetadataCannotCreateSession() {
        for (bad in listOf(
            initial().put("session_id", "../escape"),
            initial().put("legacy_complete", true),
            initial().put("schema_version", 1.5),
            initial().put("config_hash", "missing"),
        )) fails { SessionWriter(temp.root, bad, limits()) }
        assertEquals(0, temp.root.listFiles()!!.size)
    }
    @Test fun manualRecoveryRetainsOldIdentityAndIsNeverComplete() {
        val w = writer(); w.append(record()); w.flush(); w.close()
        assertEquals(listOf(w.sessionDir), SessionWriter.findIncomplete(temp.root))
        val m = SessionWriter.recover(w.sessionDir, limits())
        assertEquals("INCOMPLETE", m.getString("status"))
        assertEquals("synthetic-boot", m.getString("boot_id"))
        assertEquals(1, m.getJSONArray("streams").getJSONObject(0).getInt("sample_count"))
        fails { SessionWriter.exportSession(w.sessionDir, ByteArrayOutputStream()) }
        evidence("incomplete", m)
    }
    @Test fun tornRecordIsRetainedWithoutInventingAnEvent() {
        val w = writer(); w.append(record()); w.close()
        val f = w.sessionDir.listFiles()!!.single { it.name.endsWith(".partial") }
        f.appendText("{\"torn\":")
        val original = f.readBytes()
        val m = SessionWriter.recover(w.sessionDir, limits())
        assertEquals("EVIDENCE_DEGRADED", m.getString("status"))
        assertEquals(1, m.getJSONArray("streams").getJSONObject(0).getInt("sample_count"))
        assertArrayEquals(original, File(w.sessionDir, m.getJSONArray("chunks").getJSONObject(0).getString("path")).readBytes())
        evidence("degraded", m)
    }
    @Test fun legacyWithoutContextCannotBeUpgraded() {
        val dir = temp.newFolder("legacy"); File(dir, "INCOMPLETE").writeText("legacy")
        fails { SessionWriter.recover(dir) }
        assertFalse(File(dir, "session_manifest.json").exists())
        assertTrue(File(dir, "INCOMPLETE").exists())
    }
    @Test fun recoveryRejectsAmbiguousChunkOrder() {
        val w = writer(); w.append(record()); w.close()
        File(w.sessionDir, "chunk_00001.jsonl").writeText("duplicate")
        fails { SessionWriter.recover(w.sessionDir, limits()) }
        assertFalse(File(w.sessionDir, "session_manifest.json").exists())
    }
    @Test fun crashAfterManifestPublicationPreservesVerifiedComplete() {
        val w = writer(); w.append(record()); val before = w.finish().readText()
        File(w.sessionDir, "INCOMPLETE").writeText("stale marker")
        val m = SessionWriter.recover(w.sessionDir, limits())
        assertEquals("COMPLETE", m.getString("status"))
        assertEquals(before, File(w.sessionDir, "session_manifest.json").readText())
    }
    @Test fun zipContainsExactlySelectedManifestAndDeclaredChunks() {
        val w = writer(); w.append(record()); w.finish()
        File(w.sessionDir, "unrelated-private-file").writeText("must not export")
        val destination = ByteArrayOutputStream(); SessionWriter.exportSession(w.sessionDir, destination)
        val names = mutableListOf<String>()
        ZipInputStream(destination.toByteArray().inputStream()).use { zip ->
            while (true) { val entry = zip.nextEntry ?: break; names.add(entry.name); zip.readBytes() }
        }
        assertEquals(listOf("chunk_00001.jsonl", "session_manifest.json"), names)
    }
    @Test fun tamperIsRejectedBeforeWritingExport() {
        val w = writer(); w.append(record()); w.finish()
        File(w.sessionDir, "chunk_00001.jsonl").appendText("tamper")
        val out = ByteArrayOutputStream()
        fails { SessionWriter.exportSession(w.sessionDir, out) }
        assertEquals(0, out.size())
    }
    @Test fun unsafePathCannotBeExported() {
        val w = writer(); w.append(record()); val f = w.finish(); val m = manifest(f)
        m.getJSONArray("chunks").getJSONObject(0).put("path", "../secret")
        f.writeText(m.toString())
        fails { SessionWriter.exportSession(w.sessionDir, ByteArrayOutputStream()) }
    }
    @Test fun atomicManifestFailureRetainsRecoveryEvidence() {
        val w = writer(); w.append(record())
        File(w.sessionDir, "session_manifest.json.tmp").mkdir()
        fails { w.finish() }
        assertTrue(File(w.sessionDir, "INCOMPLETE").isFile)
        assertTrue(File(w.sessionDir, "chunk_00001.jsonl").isFile)
        assertFalse(File(w.sessionDir, "session_manifest.json").exists())
    }
    @Test fun interruptedProducerWaitsForItsWriteAndPreservesInterrupt() {
        val w = writer()
        try {
            Thread.currentThread().interrupt()
            w.append(record())
            assertTrue(Thread.currentThread().isInterrupted)
        } finally { Thread.interrupted() }
        assertEquals("COMPLETE", manifest(w.finish()).getString("status"))
    }
    @Test fun trailingGarbageCannotBecomeARecoveredEvent() {
        val w = writer(); w.close()
        File(w.sessionDir, "chunk_00001.jsonl.partial").writeText(record().toString() + "garbage\n")
        val m = SessionWriter.recover(w.sessionDir, limits())
        assertEquals("EVIDENCE_DEGRADED", m.getString("status"))
        assertEquals(0, m.getJSONArray("streams").getJSONObject(0).getInt("sample_count"))
    }

}
