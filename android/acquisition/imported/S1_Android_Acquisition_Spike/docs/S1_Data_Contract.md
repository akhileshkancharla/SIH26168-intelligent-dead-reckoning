# S1 Versioned Recording Contract

Contract identifier: `s1.android.acquisition.v1`

## 1. Evidence model

Each recording is a directory with immutable finalized chunks named
`chunk_NNNNN.jsonl` and a `session_manifest.json`. A chunk is first written as
`.partial`, flushed every ten seconds, synchronized to storage, atomically
renamed when finalized, and SHA-256 hashed. `INCOMPLETE` exists until the final
manifest is durable. On the next application process start, orphaned partial
chunks are finalized and the session receives `complete: false` and stop reason
`recovered_after_incomplete_termination`.

Each JSONL line is one object. Required common fields are:

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | string | Exact contract identifier |
| `session_id` | UUID string | Random per explicit Start operation |
| `stream` | string | Provenance-preserving stream key |
| `record_type` | string | Payload discriminator |
| `sequence` | integer | Starts at 1 and increases independently per stream |
| `source_timestamp_ns` | integer | Original source epoch when one exists; otherwise event-observation time |
| `source_clock_domain` | string | Clock definition, normally `android.elapsed_realtime_ns` |
| `callback_arrival_timestamp_ns` | integer | `SystemClock.elapsedRealtimeNanos()` at callback entry |

Evidence order is physical JSONL order across chunks in manifest order. An
analyzer must not sort this order away. Sequence, duplicates, non-monotonic
source time, and source-to-arrival latency make batching/reordering observable.

## 2. Clock contract

`SensorEvent.timestamp` is the original event time in nanoseconds. Android
documents it as monotonically increasing for each sensor and using the same
time base as `SystemClock.elapsedRealtimeNanos()`.

`Location.elapsedRealtimeNanos` is the fix time in elapsed realtime since boot.
Android documents it as monotonic, continuing through deep sleep, valid for
ordering within one boot, and set on `LocationManager` locations.

`callback_arrival_timestamp_ns` is sampled by the logger at callback entry in
the same elapsed-realtime domain. Therefore `arrival - source` is an observable
delivery-age/latency measure. It is not substituted for source time.

`source_wall_clock_ms_auxiliary` and session wall-clock fields exist only for
human association. They must never drive scientific ordering, intervals, or
synchronization. Clocks must not be compared across devices or boot cycles.

Official references: [SensorEvent timestamp](https://developer.android.com/reference/android/hardware/SensorEvent#timestamp),
[Location elapsed realtime](https://developer.android.com/reference/android/location/Location#getElapsedRealtimeNanos()), and
[SystemClock](https://developer.android.com/reference/android/os/SystemClock#elapsedRealtimeNanos()).

## 3. Sensor records

`record_type: sensor_event` adds:

- `sensor_identity`, `sensor_type`, and `sensor_string_type`
- `accuracy`
- `values`, copied directly from the callback without axis conversion
- `units` and `axes: raw_android_device_axes_unmodified`
- original source time, callback arrival, and `arrival_minus_source_ns`
- requested period and maximum report latency

All available instances of calibrated and uncalibrated accelerometer,
gyroscope, and magnetometer types are independently registered and logged.
Absence and registration failure are explicit `sensor_availability` events.
Metadata records name, vendor, version, resolution, range, reported power,
delays, FIFO capacity, reporting mode, and wake-up status. Requested sampling
does not state or imply delivered rate.

Values and units follow the official [SensorEvent contract](https://developer.android.com/reference/android/hardware/SensorEvent).
No bias correction, filtering, interpolation, canonical frame transform, or
estimator processing occurs in the logger.

## 4. Location and GNSS-family records

`record_type: location_fix` is sourced only from explicit
`LocationManager.GPS_PROVIDER`. It records provider, latitude/longitude,
availability and value for altitude, horizontal/vertical accuracy, speed and
bearing, source wall time, source elapsed-realtime time, arrival time, age, mock
status, sequence, and session. Missing optional fields stay missing via paired
`has_*` flags and JSON null; they are never fabricated.

`record_type: gnss_status` contains receiver started/stopped/first-fix events or
a satellite-status snapshot. Satellite status is diagnostic context, **not a
position measurement**. It must not be fused as independent position evidence.
Raw GNSS measurements are deliberately absent from v1.

Provider selection follows the official named-provider
[`requestLocationUpdates`](https://developer.android.com/reference/android/location/LocationManager#requestLocationUpdates(java.lang.String,long,float,android.location.LocationListener,android.os.Looper)).
GNSS status uses official
[`registerGnssStatusCallback`](https://developer.android.com/reference/android/location/LocationManager#registerGnssStatusCallback(java.util.concurrent.Executor,android.location.GnssStatus.Callback)).

## 5. Context and lifecycle records

- `lifecycle`: activity created/recreated/started/resumed/paused/stopped/destroyed
- `service`: recording start and stop reason
- `screen_state`: screen action and `PowerManager.isInteractive`
- `thermal_state`: official integer thermal status on API 29+
- `battery_state`: level, scale, fraction, status, charging, plug type,
  temperature and voltage where the battery broadcast supplies them
- `provider_state`, `location_registration`, `sensor_availability`,
  `sensor_accuracy`, and `error`

Battery percentage is coarse OS evidence. It cannot attribute consumption to
the logger without a controlled comparison. Thermal status is unavailable on
API 28 and must then remain absent rather than be invented.

## 6. Session manifest

The final manifest records schema and session identifiers, `complete`, stop
reason, ordered chunk path/size/SHA-256 tuples, total log bytes, and final state
metadata. Session metadata inside the first chunk carries app build, Git commit
when provided through `GIT_COMMIT`, non-unique device profile, Android/API,
sensor inventory, requested configuration, clock definitions, permissions,
screen/location state, raw-GNSS exclusion, and privacy-sensitive field list.

Storage guards reserve 100 MiB free space and cap a session at 2 GiB. Crossing
either limit finalizes with an explicit fatal stop reason when possible.

## 7. Analyzer rules

The analyzer validates file presence, size, hashes, completion state and JSON;
then calculates interval/rate distributions in evidence order. Gap threshold is
reported with every result and is `max(100 ms, 3 × positive median interval)`.
Delivery bursts are consecutive callbacks separated by at most 2 ms; this is a
transparent diagnostic heuristic, not a claim about hardware FIFO internals.
Raw files are never rewritten.
