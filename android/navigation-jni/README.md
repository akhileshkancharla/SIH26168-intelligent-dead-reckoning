# Batch navigation JNI boundary

WP-03.4 implements C-06 as a versioned, little-endian direct-buffer boundary
around the portable C-07 API. The JNI layer owns only opaque-handle lifecycle,
wire validation/translation, call serialization, and deterministic error
translation. It does not own or repair navigation state, biases, covariance,
mode, validity, origins, clocks, or evidence identifiers.

All calls use caller-owned direct `ByteBuffer` instances. Native code never
retains a Java reference or a buffer address after a call. A registry-issued
64-bit token is not a pointer; zero is null, an erased token is stale, and a
second destroy deterministically reports `STALE_HANDLE`. Each live handle has a
non-recursive mutex. The Android navigation executor is expected to serialize
calls, and a concurrent call is rejected rather than blocked or reordered.

The wire format is explicit rather than compiler-structure-dependent:

- magic `SJNI`, version 2, message kind, and exact total byte length;
- bounded UTF-8 strings and bounded lists;
- IEEE-754 binary64 values without clipping or substitution;
- complete I-03, I-12, I-07, and I-08 fields;
- one operation response containing the typed C-07 result plus state and
  covariance snapshots from the same serialized call.

Transport bounds (1 MiB message, 1,024 samples, 64 provider IDs, 4 KiB per
string) are memory-safety limits, not scientific thresholds. Malformed buffers,
pending JNI exceptions, native exceptions, and allocation failures have typed
boundary statuses. C-07 rejection and numerical-failure statuses remain
separate and are returned unchanged; numerical failure therefore publishes the
C-07-owned `INVALID`/`FAULT` snapshot.

Host C++ tests exercise the codec, registry, lifecycle, deterministic execution,
and C-07 round trips. Android/JVM tests exercise the matching Kotlin codec and
allocation/error behavior. Android builds compile the thin JNI shared library;
the host build intentionally compiles only the platform-independent boundary.
