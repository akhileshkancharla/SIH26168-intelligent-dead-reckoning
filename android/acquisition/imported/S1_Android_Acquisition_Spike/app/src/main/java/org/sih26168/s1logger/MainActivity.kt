package org.sih26168.s1logger

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Typeface
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

class MainActivity : Activity() {
    private lateinit var status: TextView
    private var pendingStart = false
    private var pendingExport: File? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildUi()
        lifecycleEvent(if (savedInstanceState == null) "activity_created" else "activity_recreated")
    }

    override fun onStart() { super.onStart(); lifecycleEvent("activity_started") }
    override fun onResume() { super.onResume(); lifecycleEvent("activity_resumed") }
    override fun onPause() { lifecycleEvent("activity_paused"); super.onPause() }
    override fun onStop() { lifecycleEvent("activity_stopped"); super.onStop() }
    override fun onDestroy() { lifecycleEvent("activity_destroyed"); super.onDestroy() }

    private fun buildUi() {
        val pad = (20 * resources.displayMetrics.density).toInt()
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
        }
        box.addView(TextView(this).apply {
            text = getString(R.string.screen_title)
            textSize = 24f
            setTypeface(typeface, Typeface.BOLD)
        })
        box.addView(TextView(this).apply {
            text = getString(R.string.privacy_intro)
            textSize = 16f
            setPadding(0, pad / 2, 0, pad)
        })
        status = TextView(this).apply {
            text = getString(R.string.status_idle)
            textSize = 16f
            setPadding(0, 0, 0, pad / 2)
        }
        box.addView(status)
        box.addView(Button(this).apply {
            text = getString(R.string.start_recording)
            setOnClickListener { startRequested() }
        }, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        box.addView(Button(this).apply {
            text = getString(R.string.stop_recording)
            setOnClickListener {
                startService(Intent(this@MainActivity, RecordingService::class.java).setAction(RecordingService.ACTION_STOP))
                status.text = getString(R.string.stop_requested)
            }
        }, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        box.addView(Button(this).apply {
            text = getString(R.string.export_latest)
            setOnClickListener { exportLatest() }
        }, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        box.addView(TextView(this).apply {
            text = getString(R.string.request_explanation)
            setPadding(0, pad, 0, 0)
        })
        setContentView(ScrollView(this).apply { addView(box) })
    }

    private fun startRequested() {
        val missing = mutableListOf<String>()
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            missing += Manifest.permission.ACCESS_FINE_LOCATION
        }
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            missing += Manifest.permission.POST_NOTIFICATIONS
        }
        if (missing.isNotEmpty()) {
            pendingStart = true
            requestPermissions(missing.toTypedArray(), REQUEST_PERMISSIONS)
        } else {
            startRecording()
        }
    }

    private fun startRecording() {
        val intent = Intent(this, RecordingService::class.java).setAction(RecordingService.ACTION_START)
        try {
            startForegroundService(intent)
            status.text = getString(R.string.recording_requested)
        } catch (e: RuntimeException) {
            status.text = getString(R.string.start_failed, e.javaClass.simpleName)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_PERMISSIONS && pendingStart) {
            pendingStart = false
            if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
                startRecording()
            } else {
                status.text = getString(R.string.fine_location_denied)
            }
        }
    }

    private fun lifecycleEvent(event: String) {
        RecordingService.recordLifecycle(event)
    }

    private fun exportLatest() {
        val sessions = File(filesDir, "sessions")
        val latest = sessions.listFiles()
            ?.filter { File(it, "session_manifest.json").exists() && !File(it, "INCOMPLETE").exists() }
            ?.maxByOrNull { it.lastModified() }
        if (latest == null) {
            Toast.makeText(this, getString(R.string.no_finalized_session), Toast.LENGTH_LONG).show()
            return
        }
        pendingExport = latest
        val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "application/zip"
            putExtra(Intent.EXTRA_TITLE, "S1_session_${latest.name}.zip")
        }
        startActivityForResult(intent, REQUEST_EXPORT)
    }

    @Deprecated("Activity result retained deliberately for minSdk-compatible platform-only spike")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_EXPORT && resultCode == RESULT_OK) {
            val source = pendingExport
            val target = data?.data
            if (source != null && target != null) {
                runCatching { writeZip(source, target) }
                    .onSuccess { status.text = getString(R.string.export_complete, source.name) }
                    .onFailure { status.text = getString(R.string.export_failed, it.message) }
            }
            pendingExport = null
        }
    }

    private fun writeZip(directory: File, target: Uri) {
        contentResolver.openOutputStream(target, "w")!!.use { raw ->
            ZipOutputStream(raw.buffered()).use { zip ->
                directory.walkTopDown().filter { it.isFile }.sortedBy { it.relativeTo(directory).path }.forEach { file ->
                    val relative = file.relativeTo(directory).invariantSeparatorsPath
                    zip.putNextEntry(ZipEntry(relative).apply { time = 0L })
                    file.inputStream().use { it.copyTo(zip) }
                    zip.closeEntry()
                }
            }
        }
    }

    companion object {
        private const val REQUEST_PERMISSIONS = 100
        private const val REQUEST_EXPORT = 101
    }
}
