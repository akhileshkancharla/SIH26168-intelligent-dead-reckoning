# Android Acquisition

SCAFFOLD — NOT IMPLEMENTED

Android acquisition import belongs to WP-02.

## Synthetic S1 contract verification

WP-02.6 provides a host-side, synthetic-only round-trip check for the I-01 `RawSensorSample` and I-02 `LocationGnssFix` recording contracts:

```bash
python tools/acquisition/s1_fixture_roundtrip.py
python -m unittest tools.bootstrap.tests.test_s1_fixture_round_trip -v