# Android acquisition

WP-02.4 implements the bounded C-02 session writer in
`src/main/java/org/sih26168/s1logger/SessionWriter.kt`. The existing `:app`
compiles this source directory and the focused JVM tests; no second Android
module or imported-build dependency is introduced.

The read-only S1 import remains byte-for-byte unchanged. The adaptation uses
I-18 v1 (`status`, `size_bytes`, explicit metadata), not the legacy manifest.

## Caller contract

- Construct the writer with an app-private sessions root, explicit I-18 metadata,
  `INCOMPLETE`, no chunks, zero stream counts/losses and null sequence bounds.
  Supply every build/device/boot/config/stream field; legacy metadata is not inferred.
  Each declared stream has an entry in `loss_counts`.
- Append already validated records with matching `session_id`, declared `stream_id`
  and a strictly increasing non-negative integer `sequence`. Other record fields
  are preserved. Payload contract validation remains the producer's responsibility.
- Calls block for bounded backpressure; disk I/O and the periodic fsync timer use
  one worker. The default limits retain S1's 5 MiB chunks, 2 GiB session,
  100 MiB free-space reserve and 10-second flush interval.
- `finish(observedLossCounts)` finalizes chunks and publishes the manifest last.
  Observed sequence gaps, reported loss or a previous write/flush failure prohibit
  `COMPLETE`. Report total observed loss per stream, including known sequence gaps.
  An exception leaves diagnostic evidence for recovery. `close()` abandons without
  publishing a successful manifest.
- On a later **manual launch**, after ensuring no writer owns a session, call
  `findIncomplete` / `recover`. Recovery retains the saved boot/clock identity,
  scans only bounded numbered chunks, preserves torn bytes and never invents an
  event. Abandoned sessions are `INCOMPLETE` or `EVIDENCE_DEGRADED`. A previously
  published verified manifest survives a crash before marker removal unchanged.
  Legacy directories without explicit context are rejected. Recovery loss counts
  describe observed sequence gaps, not an estimate of unobserved lost callbacks.
- `exportSession(selectedSessionDirectory, userSelectedOutputStream)` verifies one
  `COMPLETE` session and writes exactly its declared chunks and manifest, in order.
  The caller owns the destination, must discard partial output on any exception,
  and must obtain explicit user selection (for Android, a document-picker URI).
  The writer does not select the latest session, traverse arbitrary ZIP paths,
  include unrelated files, or upload anything.

Live acquisition and document-picker call sites are not present in the monorepo
app and are not fabricated here. This is a build-connected writer API, not a claim
that the replay app now records sensors. Runtime integration, Android/device
validation and owner review remain required before WP-02.4 can be accepted.
File fsync and same-filesystem atomic rename are implemented; power-loss durability
of directory entries still requires target-device/filesystem testing.

## Focused validation

```bash
gradle -p android --no-daemon :app:testDebugUnitTest --tests org.sih26168.s1logger.SessionWriterTest :app:lintDebug :app:assembleDebug
python ci/run_python_checks.py python
python ci/verify_repository.py all
```

See `docs/operations/WP-02.4_IMPLEMENTATION.md` for the actual evidence and limits.
These writer tests belong to #34; the separate #35 acquisition test work package
and #43 are not started.

## Synthetic S1 contract verification

WP-02.6 provides a host-side, synthetic-only round-trip check for I-01 and I-02:

```bash
python tools/acquisition/s1_fixture_roundtrip.py
python -m unittest tools.bootstrap.tests.test_s1_fixture_round_trip -v
```
