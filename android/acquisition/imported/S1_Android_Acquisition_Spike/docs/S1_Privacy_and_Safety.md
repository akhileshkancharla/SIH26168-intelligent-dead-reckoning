# S1 Privacy and Safety

## Data minimization

Collection begins only after a visible user presses **Start Recording** and fine
location has been granted. The application has no Internet permission, network
client, analytics SDK, Play-services dependency, background upload, account,
advertising identifier, Android ID, IMEI, phone number, contact access, or
microphone/camera access. Data remains in app-private storage until the user
explicitly exports one completed session through Android's document picker.

The logger necessarily records sensitive trajectory and movement evidence:
latitude, longitude, optional altitude, speed/bearing, raw motion-sensor values,
times, and manufacturer/model. These can reveal places, habits, movement and
device class. Export only controlled test sessions, store them in an
access-controlled project location, never commit raw traces to a public
repository, and delete phone-local copies when no longer required.

Sensor name/vendor/version are retained because they are required to interpret
device variability. Unique hardware identifiers are excluded. Session IDs are
random and are not stable user identifiers.

## Permission and foreground-service safety

The logger asks for fine location because `GnssStatus` requires it and the
scientific source is the named GPS provider. Android 14+ requires the manifest
`location` foreground-service type and `FOREGROUND_SERVICE_LOCATION` permission,
with a granted while-in-use location permission before promotion. The app starts
the service only from a visible button; it does not request background location
or start from boot. See Android's official
[location foreground-service requirements](https://developer.android.com/develop/background-work/services/fgs/service-types#location)
and [launch sequence/restrictions](https://developer.android.com/develop/background-work/services/fgs/launch).

Notification permission denial on API 33+ is recorded. The app does not treat
it as location authorization. Fine-location denial prevents recording. Location
disabled and provider-disabled changes are explicit evidence.

Android documents that continuous sensors are restricted for background apps
from API 28, so acquisition is hosted by the foreground service. The manifest
declares `HIGH_SAMPLING_RATE_SENSORS`; official sensor guidance notes that high
rates can otherwise be limited and can still be limited by the device-wide
microphone privacy toggle. See [Sensors overview](https://developer.android.com/develop/sensors-and-location/sensors/sensors_overview).

## Operational safety

- The driver must never operate or look at the phone during a motion test.
- Prefer a passenger operator, secured mount, controlled test track, walking
  test, or non-driving bench substitute.
- Do not obstruct the driver's view, airbags, controls, ventilation, or charging
  safety. Stop if the mount loosens, the phone overheats, or battery swelling,
  cable damage, rain, or unsafe traffic conditions occur.
- Record public-road movement only when lawful and necessary. Avoid homes,
  schools, medical locations, bystanders, and sensitive facilities.
- Do not induce low storage by filling a personal device. Use the logger's cap,
  a test profile/emulator, or a controlled quota.
- Permission denial, disabled location, and restart tests must occur while
  parked/safe. Force-stop is not treated as recoverable service evidence.

## Limitations

A foreground service improves execution eligibility but is not a guarantee
against OEM task killers, user stop, force-stop, reboot, thermal shutdown,
storage failure, or process death. S1 exists to measure these behaviors on named
devices. Incomplete recovery preserves finalized and partial chunks but cannot
recreate unwritten callback data.

Battery percentage is coarse and affected by other workloads, calibration and
charging. Report it only with initial/final state, duration, charging status,
device conditions and a control where practical. Android thermal status is an
OS classification available from API 29; it is not a direct component
temperature measurement. See the official
[`PowerManager` thermal API](https://developer.android.com/reference/android/os/PowerManager#getCurrentThermalStatus()).
