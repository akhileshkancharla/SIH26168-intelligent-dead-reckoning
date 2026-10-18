package org.sih26168.s1logger

import android.Manifest
import android.content.pm.PackageManager
import android.hardware.SensorManager
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.json.JSONObject
import java.io.File

@RunWith(AndroidJUnit4::class)
class RecordingInstrumentationTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext

    @Test fun schemaSerializationRoundTrip() {
        val encoded = JsonUtil.objectOf(
            "schema_version" to RecordingContract.SCHEMA_VERSION,
            "source_timestamp_ns" to 123L,
            "values" to JsonUtil.arrayOf(floatArrayOf(1f, 2f, 3f)),
        ).toString()
        val decoded = JSONObject(encoded)
        assertEquals(RecordingContract.SCHEMA_VERSION, decoded.getString("schema_version"))
        assertEquals(123L, decoded.getLong("source_timestamp_ns"))
        assertEquals(3, decoded.getJSONArray("values").length())
    }

    @Test fun chunkFinalizationAndHashVerification() {
        val root = File(context.cacheDir, "s1-test-finalize-${System.nanoTime()}").also { it.mkdirs() }
        val writer = SessionWriter(root)
        writer.append(JsonUtil.objectOf("record_type" to "fixture", "source_timestamp_ns" to 1L))
        val manifestFile = writer.close("test", JSONObject())
        val manifest = JSONObject(manifestFile.readText())
        val chunk = manifest.getJSONArray("chunks").getJSONObject(0)
        val path = File(writer.sessionDir, chunk.getString("path"))
        assertEquals(chunk.getString("sha256"), SessionWriter.sha256(path))
        assertFalse(File(writer.sessionDir, "INCOMPLETE").exists())
    }

    @Test fun incompleteSessionRecoveryIsExplicit() {
        val root = File(context.cacheDir, "s1-test-recovery-${System.nanoTime()}").also { it.mkdirs() }
        val session = File(root, "abandoned").also { it.mkdirs() }
        File(session, "INCOMPLETE").writeText("incomplete\n")
        File(session, "chunk_00001.jsonl.partial").writeText("{\"record_type\":\"fixture\"}\n")
        val manifest = SessionWriter.recover(session)
        assertFalse(manifest.getBoolean("complete"))
        assertEquals("recovered_after_incomplete_termination", manifest.getString("stop_reason"))
        assertTrue(File(session, "chunk_00001.jsonl").exists())
    }

    @Test fun manifestPermissionDeclarations() {
        val info = context.packageManager.getPackageInfo(context.packageName, PackageManager.GET_PERMISSIONS)
        val permissions = info.requestedPermissions?.toSet().orEmpty()
        assertTrue(permissions.contains(Manifest.permission.ACCESS_FINE_LOCATION))
        assertTrue(permissions.contains(Manifest.permission.FOREGROUND_SERVICE))
        assertTrue(permissions.contains(Manifest.permission.FOREGROUND_SERVICE_LOCATION))
        assertTrue(permissions.contains(Manifest.permission.HIGH_SAMPLING_RATE_SENSORS))
    }

    @Test fun lifecycleEventEncoding() {
        val record = JsonUtil.objectOf("record_type" to "lifecycle", "event" to "activity_recreated")
        assertEquals("lifecycle", record.getString("record_type"))
        assertEquals("activity_recreated", record.getString("event"))
    }

    @Test fun unsupportedSensorReturnsEmptyList() {
        val manager = context.getSystemService(android.content.Context.SENSOR_SERVICE) as SensorManager
        assertTrue(manager.getSensorList(Int.MAX_VALUE).isEmpty())
    }
}
