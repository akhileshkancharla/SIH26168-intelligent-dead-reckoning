package org.sih26168.s1logger

import android.Manifest
import android.app.*
import android.content.*
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.hardware.*
import android.location.*
import android.os.*
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executor

class RecordingService : Service(), SensorEventListener, LocationListener {
    private lateinit var sensorManager: SensorManager
    private lateinit var locationManager: LocationManager
    private lateinit var powerManager: PowerManager
    private lateinit var thread: HandlerThread
    private lateinit var handler: Handler
    private val sequencer = StreamSequencer()
    private var session: SessionWriter? = null
    private var stopping = false
    private var thermalStatus: Int? = null
    private var registeredSensors = mutableListOf<Sensor>()
    private var recoveredPriorSessions: List<String> = emptyList()

    private val stateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val action = intent?.action ?: return
            when (action) {
                Intent.ACTION_SCREEN_ON, Intent.ACTION_SCREEN_OFF -> event("screen_state", JsonUtil.objectOf(
                    "action" to action,
                    "interactive" to powerManager.isInteractive,
                ))
                Intent.ACTION_BATTERY_CHANGED -> event("battery_state", batteryJson(intent))
            }
        }
    }

    private val thermalListener = PowerManager.OnThermalStatusChangedListener { status ->
        thermalStatus = status
        event("thermal_state", JsonUtil.objectOf("thermal_status" to status))
    }

    private val gnssCallback = object : GnssStatus.Callback() {
        override fun onStarted() = event("gnss_status", JsonUtil.objectOf("event" to "started"))
        override fun onStopped() = event("gnss_status", JsonUtil.objectOf("event" to "stopped"))
        override fun onFirstFix(ttffMillis: Int) = event("gnss_status", JsonUtil.objectOf("event" to "first_fix", "ttff_ms" to ttffMillis))
        override fun onSatelliteStatusChanged(status: GnssStatus) {
            val satellites = JSONArray()
            for (i in 0 until status.satelliteCount) {
                satellites.put(JsonUtil.objectOf(
                    "svid" to status.getSvid(i),
                    "constellation_type" to status.getConstellationType(i),
                    "cn0_dbhz" to status.getCn0DbHz(i).toDouble(),
                    "elevation_deg" to status.getElevationDegrees(i).toDouble(),
                    "azimuth_deg" to status.getAzimuthDegrees(i).toDouble(),
                    "used_in_fix" to status.usedInFix(i),
                    "has_almanac" to status.hasAlmanacData(i),
                    "has_ephemeris" to status.hasEphemerisData(i),
                    "carrier_frequency_hz" to if (status.hasCarrierFrequencyHz(i)) status.getCarrierFrequencyHz(i).toDouble() else null,
                ))
            }
            event("gnss_status", JsonUtil.objectOf("event" to "satellite_snapshot", "satellites" to satellites))
        }
    }

    private val periodicFlush = object : Runnable {
        override fun run() {
            runCatching { session?.flush() }.onFailure { fatal("flush_failed", it) }
            if (session != null) handler.postDelayed(this, RecordingContract.FLUSH_INTERVAL_MS)
        }
    }

    override fun onCreate() {
        super.onCreate()
        sensorManager = getSystemService(SENSOR_SERVICE) as SensorManager
        locationManager = getSystemService(LOCATION_SERVICE) as LocationManager
        powerManager = getSystemService(POWER_SERVICE) as PowerManager
        thread = HandlerThread("s1-acquisition", Process.THREAD_PRIORITY_MORE_FAVORABLE).also { it.start() }
        handler = Handler(thread.looper)
        val sessionsRoot = File(filesDir, "sessions").also { it.mkdirs() }
        recoveredPriorSessions = SessionWriter.findIncomplete(sessionsRoot).mapNotNull {
            runCatching { SessionWriter.recover(it); it.name }.getOrNull()
        }
        activeInstance = this
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> if (session == null) startRecording()
            ACTION_STOP -> stopRecording("user_stop")
        }
        return START_NOT_STICKY
    }

    private fun startRecording() {
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            stopSelf(); return
        }
        stopping = false
        createNotificationChannel()
        try {
            val notification = buildNotification()
            if (Build.VERSION.SDK_INT >= 29) {
                startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
            } else {
                startForeground(NOTIFICATION_ID, notification)
            }
        } catch (_: RuntimeException) {
            stopSelf(); return
        }
        try {
            session = SessionWriter(File(filesDir, "sessions"))
            metadataAndContract()
            registerStateSources()
            registerSensors()
            registerLocation()
            handler.postDelayed(periodicFlush, RecordingContract.FLUSH_INTERVAL_MS)
            event("service", JsonUtil.objectOf("event" to "recording_started"))
        } catch (t: Throwable) {
            fatal("start_failed", t)
        }
    }

    private fun metadataAndContract() {
        val sensors = JSONArray()
        sensorManager.getSensorList(Sensor.TYPE_ALL).forEach { s ->
            sensors.put(JsonUtil.objectOf(
                "identity" to sensorIdentity(s), "name" to s.name, "vendor" to s.vendor,
                "version" to s.version, "type" to s.type, "string_type" to s.stringType,
                "resolution" to s.resolution.toDouble(), "maximum_range" to s.maximumRange.toDouble(),
                "power_ma" to s.power.toDouble(), "min_delay_us" to s.minDelay,
                "max_delay_us" to s.maxDelay, "fifo_reserved_event_count" to s.fifoReservedEventCount,
                "fifo_max_event_count" to s.fifoMaxEventCount, "reporting_mode" to s.reportingMode,
                "wake_up_sensor" to s.isWakeUpSensor,
            ))
        }
        val permissionState = JsonUtil.objectOf(
            "fine_location" to (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED),
            "coarse_location" to (checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED),
            "notifications" to (Build.VERSION.SDK_INT < 33 || checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED),
            "high_sampling_rate_sensors_declared" to true,
        )
        append("metadata", 0L, JsonUtil.objectOf(
            "record_type" to "session_metadata",
            "app_build" to "${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})",
            "git_commit" to BuildConfig.GIT_COMMIT,
            "manufacturer" to Build.MANUFACTURER,
            "model" to Build.MODEL,
            "android_release" to Build.VERSION.RELEASE,
            "api_level" to Build.VERSION.SDK_INT,
            "wall_clock_start_ms_auxiliary" to System.currentTimeMillis(),
            "clock_domains" to JsonUtil.objectOf(
                "sensor_source" to RecordingContract.CLOCK_ELAPSED_REALTIME_NS,
                "location_source" to RecordingContract.CLOCK_ELAPSED_REALTIME_NS,
                "callback_arrival" to RecordingContract.CLOCK_ELAPSED_REALTIME_NS,
                "wall_clock" to RecordingContract.CLOCK_UNIX_EPOCH_MS,
            ),
            "requested_sampling" to JsonUtil.objectOf(
                "sensor_period_us" to RecordingContract.SENSOR_PERIOD_US,
                "sensor_max_report_latency_us" to RecordingContract.SENSOR_MAX_REPORT_LATENCY_US,
                "location_provider" to LocationManager.GPS_PROVIDER,
                "location_min_time_ms" to RecordingContract.LOCATION_MIN_TIME_MS,
                "location_min_distance_m" to 0.0,
            ),
            "permissions" to permissionState,
            "initial_screen_interactive" to powerManager.isInteractive,
            "location_enabled" to locationManager.isLocationEnabled,
            "sensors" to sensors,
            "privacy_sensitive_fields" to JSONArray(listOf("latitude", "longitude", "altitude", "motion_sensor_values", "device_model")),
            "raw_gnss_measurements_included" to false,
            "recovered_prior_session_count" to recoveredPriorSessions.size,
            "recovered_prior_session_ids" to JSONArray(recoveredPriorSessions),
        ))
    }

    private fun registerSensors() {
        val types = listOf(
            Sensor.TYPE_ACCELEROMETER, Sensor.TYPE_GYROSCOPE, Sensor.TYPE_MAGNETIC_FIELD,
            Sensor.TYPE_ACCELEROMETER_UNCALIBRATED, Sensor.TYPE_GYROSCOPE_UNCALIBRATED,
            Sensor.TYPE_MAGNETIC_FIELD_UNCALIBRATED,
        )
        types.forEach { type ->
            val candidates = sensorManager.getSensorList(type)
            if (candidates.isEmpty()) {
                event("sensor_availability", JsonUtil.objectOf("sensor_type" to type, "available" to false))
            }
            candidates.forEach { sensor ->
                val ok = sensorManager.registerListener(
                    this, sensor, RecordingContract.SENSOR_PERIOD_US,
                    RecordingContract.SENSOR_MAX_REPORT_LATENCY_US, handler,
                )
                event("sensor_availability", JsonUtil.objectOf(
                    "sensor_identity" to sensorIdentity(sensor), "sensor_type" to type,
                    "available" to true, "registration_succeeded" to ok,
                ))
                if (ok) registeredSensors += sensor
            }
        }
    }

    private fun registerLocation() {
        try {
            locationManager.requestLocationUpdates(
                LocationManager.GPS_PROVIDER, RecordingContract.LOCATION_MIN_TIME_MS, 0f, this, handler.looper,
            )
            val ok = if (Build.VERSION.SDK_INT >= 30) {
                locationManager.registerGnssStatusCallback(Executor { handler.post(it) }, gnssCallback)
            } else {
                @Suppress("DEPRECATION")
                locationManager.registerGnssStatusCallback(gnssCallback, handler)
            }
            event("location_registration", JsonUtil.objectOf(
                "provider" to LocationManager.GPS_PROVIDER, "gnss_status_registered" to ok,
                "provider_enabled" to locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER),
            ))
        } catch (e: SecurityException) {
            fatal("location_permission_lost", e)
        } catch (e: IllegalArgumentException) {
            event("location_registration", JsonUtil.objectOf("provider" to LocationManager.GPS_PROVIDER, "error" to "provider_unavailable"))
        }
    }

    private fun registerStateSources() {
        registerReceiver(stateReceiver, IntentFilter().apply {
            addAction(Intent.ACTION_SCREEN_ON); addAction(Intent.ACTION_SCREEN_OFF); addAction(Intent.ACTION_BATTERY_CHANGED)
        })
        if (Build.VERSION.SDK_INT >= 29) {
            thermalStatus = powerManager.currentThermalStatus
            powerManager.addThermalStatusListener(Executor { handler.post(it) }, thermalListener)
        }
    }

    override fun onSensorChanged(event: SensorEvent) {
        val arrival = SystemClock.elapsedRealtimeNanos()
        val sensor = event.sensor
        append("sensor:${sensorIdentity(sensor)}", event.timestamp, JsonUtil.objectOf(
            "record_type" to "sensor_event",
            "sensor_identity" to sensorIdentity(sensor),
            "sensor_type" to sensor.type,
            "sensor_string_type" to sensor.stringType,
            "accuracy" to event.accuracy,
            "values" to JsonUtil.arrayOf(event.values.copyOf()),
            "units" to units(sensor.type),
            "axes" to "raw_android_device_axes_unmodified",
            "source_timestamp_ns" to event.timestamp,
            "source_clock_domain" to RecordingContract.CLOCK_ELAPSED_REALTIME_NS,
            "callback_arrival_timestamp_ns" to arrival,
            "arrival_minus_source_ns" to (arrival - event.timestamp),
            "requested_period_us" to RecordingContract.SENSOR_PERIOD_US,
            "requested_max_report_latency_us" to RecordingContract.SENSOR_MAX_REPORT_LATENCY_US,
        ), arrival)
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {
        event("sensor_accuracy", JsonUtil.objectOf("sensor_identity" to sensor?.let(::sensorIdentity), "accuracy" to accuracy))
    }

    override fun onLocationChanged(location: Location) {
        val arrival = SystemClock.elapsedRealtimeNanos()
        val source = location.elapsedRealtimeNanos
        append("location:${location.provider}", source, JsonUtil.objectOf(
            "record_type" to "location_fix",
            "provider" to location.provider,
            "latitude_deg" to location.latitude,
            "longitude_deg" to location.longitude,
            "has_altitude" to location.hasAltitude(),
            "altitude_m" to if (location.hasAltitude()) location.altitude else null,
            "has_horizontal_accuracy" to location.hasAccuracy(),
            "horizontal_accuracy_m" to if (location.hasAccuracy()) location.accuracy.toDouble() else null,
            "has_vertical_accuracy" to location.hasVerticalAccuracy(),
            "vertical_accuracy_m" to if (location.hasVerticalAccuracy()) location.verticalAccuracyMeters.toDouble() else null,
            "has_speed" to location.hasSpeed(),
            "speed_mps" to if (location.hasSpeed()) location.speed.toDouble() else null,
            "has_speed_accuracy" to location.hasSpeedAccuracy(),
            "speed_accuracy_mps" to if (location.hasSpeedAccuracy()) location.speedAccuracyMetersPerSecond.toDouble() else null,
            "has_bearing" to location.hasBearing(),
            "bearing_deg" to if (location.hasBearing()) location.bearing.toDouble() else null,
            "has_bearing_accuracy" to location.hasBearingAccuracy(),
            "bearing_accuracy_deg" to if (location.hasBearingAccuracy()) location.bearingAccuracyDegrees.toDouble() else null,
            "source_wall_clock_ms_auxiliary" to location.time,
            "source_elapsed_realtime_ns" to source,
            "source_clock_domain" to RecordingContract.CLOCK_ELAPSED_REALTIME_NS,
            "callback_arrival_timestamp_ns" to arrival,
            "age_at_callback_ns" to (arrival - source),
            "mock" to if (Build.VERSION.SDK_INT >= 31) location.isMock else @Suppress("DEPRECATION") location.isFromMockProvider,
        ), arrival)
    }

    override fun onProviderEnabled(provider: String) = event("provider_state", JsonUtil.objectOf("provider" to provider, "enabled" to true))
    override fun onProviderDisabled(provider: String) = event("provider_state", JsonUtil.objectOf("provider" to provider, "enabled" to false))

    private fun event(stream: String, fields: JSONObject) {
        val now = SystemClock.elapsedRealtimeNanos()
        if (!fields.has("record_type")) fields.put("record_type", stream)
        append(stream, now, fields, now)
    }

    private fun append(stream: String, sourceNs: Long, fields: JSONObject, arrivalNs: Long = SystemClock.elapsedRealtimeNanos()) {
        val active = session ?: return
        fields.put("schema_version", RecordingContract.SCHEMA_VERSION)
        fields.put("session_id", active.sessionId)
        fields.put("stream", stream)
        fields.put("sequence", sequencer.next(stream))
        if (!fields.has("source_timestamp_ns")) fields.put("source_timestamp_ns", sourceNs)
        if (!fields.has("source_clock_domain")) fields.put("source_clock_domain", RecordingContract.CLOCK_ELAPSED_REALTIME_NS)
        if (!fields.has("callback_arrival_timestamp_ns")) fields.put("callback_arrival_timestamp_ns", arrivalNs)
        try { active.append(fields) } catch (t: Throwable) { fatal("write_failed", t) }
    }

    private fun stopRecording(reason: String) {
        if (stopping) return
        stopping = true
        handler.removeCallbacks(periodicFlush)
        sensorManager.unregisterListener(this)
        runCatching { locationManager.removeUpdates(this) }
        runCatching { locationManager.unregisterGnssStatusCallback(gnssCallback) }
        runCatching { unregisterReceiver(stateReceiver) }
        if (Build.VERSION.SDK_INT >= 29) runCatching { powerManager.removeThermalStatusListener(thermalListener) }
        val active = session
        if (active != null) {
            event("service", JsonUtil.objectOf("event" to "recording_stopping", "reason" to reason))
            val metadata = JsonUtil.objectOf(
                "final_screen_interactive" to powerManager.isInteractive,
                "final_thermal_status" to thermalStatus,
                "registered_sensor_count" to registeredSensors.size,
                "permission_fine_location_at_stop" to (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED),
            )
            runCatching { active.close(reason, metadata) }
        }
        session = null
        registeredSensors.clear()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun fatal(code: String, throwable: Throwable) {
        val active = session
        if (active != null && !stopping) {
            stopping = true
            runCatching {
                val now = SystemClock.elapsedRealtimeNanos()
                active.append(JsonUtil.objectOf(
                    "schema_version" to RecordingContract.SCHEMA_VERSION,
                    "session_id" to active.sessionId,
                    "stream" to "error",
                    "record_type" to "error",
                    "sequence" to sequencer.next("error"),
                    "source_timestamp_ns" to now,
                    "source_clock_domain" to RecordingContract.CLOCK_ELAPSED_REALTIME_NS,
                    "callback_arrival_timestamp_ns" to now,
                    "code" to code,
                    "exception" to throwable.javaClass.name,
                    "message" to throwable.message,
                ))
                active.close("fatal_error:$code", JsonUtil.objectOf("recoverable" to false))
            }
        }
        handler.removeCallbacks(periodicFlush)
        sensorManager.unregisterListener(this)
        runCatching { locationManager.removeUpdates(this) }
        runCatching { locationManager.unregisterGnssStatusCallback(gnssCallback) }
        runCatching { unregisterReceiver(stateReceiver) }
        if (Build.VERSION.SDK_INT >= 29) runCatching { powerManager.removeThermalStatusListener(thermalListener) }
        session = null
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun sensorIdentity(sensor: Sensor): String = "${sensor.type}:${sensor.vendor}:${sensor.name}:${sensor.version}"

    private fun units(type: Int): String = when (type) {
        Sensor.TYPE_ACCELEROMETER, Sensor.TYPE_ACCELEROMETER_UNCALIBRATED -> "m/s^2 (uncalibrated variants may append bias estimates)"
        Sensor.TYPE_GYROSCOPE, Sensor.TYPE_GYROSCOPE_UNCALIBRATED -> "rad/s (uncalibrated variants may append drift estimates)"
        Sensor.TYPE_MAGNETIC_FIELD, Sensor.TYPE_MAGNETIC_FIELD_UNCALIBRATED -> "uT (uncalibrated variants may append bias estimates)"
        else -> "see Android SensorEvent contract"
    }

    private fun batteryJson(intent: Intent): JSONObject {
        val level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
        val scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
        val status = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
        return JsonUtil.objectOf(
            "level" to level, "scale" to scale,
            "fraction" to if (level >= 0 && scale > 0) level.toDouble() / scale else null,
            "status" to status,
            "charging" to (status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL),
            "plugged" to intent.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0),
            "temperature_tenths_c" to intent.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, -1),
            "voltage_mv" to intent.getIntExtra(BatteryManager.EXTRA_VOLTAGE, -1),
        )
    }

    private fun createNotificationChannel() {
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "S1 recording", NotificationManager.IMPORTANCE_LOW).apply {
            description = "Visible indicator for user-started local sensor and location recording"
        })
    }

    private fun buildNotification(): Notification {
        val stopIntent = PendingIntent.getService(
            this, 1, Intent(this, RecordingService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val openIntent = PendingIntent.getActivity(
            this, 2, Intent(this, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(org.sih26168.s1logger.R.drawable.ic_stat_recording)
            .setContentTitle("SIH26168 S1 recording")
            .setContentText("IMU and GPS-provider evidence is being logged locally")
            .setContentIntent(openIntent)
            .setOngoing(true)
            .setCategory(Notification.CATEGORY_SERVICE)
            .addAction(Notification.Action.Builder(null, "Stop", stopIntent).build())
            .build()
    }

    override fun onBind(intent: Intent?) = null

    override fun onDestroy() {
        if (session != null) stopRecording("service_destroyed")
        activeInstance = null
        thread.quitSafely()
        super.onDestroy()
    }

    companion object {
        const val ACTION_START = "org.sih26168.s1logger.START"
        const val ACTION_STOP = "org.sih26168.s1logger.STOP"
        private const val CHANNEL_ID = "s1_recording"
        private const val NOTIFICATION_ID = 26168
        @Volatile private var activeInstance: RecordingService? = null

        fun recordLifecycle(event: String) {
            val service = activeInstance ?: return
            service.handler.post {
                service.event("lifecycle", JsonUtil.objectOf("event" to event))
            }
        }
    }
}
