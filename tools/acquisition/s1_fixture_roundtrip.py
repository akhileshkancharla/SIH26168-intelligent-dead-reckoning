#!/usr/bin/env python3
"""Validate and canonically round-trip the public synthetic S1 fixture.

This host-only harness verifies I-01/I-02 payloads inside the Contract v1
evidence envelope. It never invokes Android APIs or downstream estimators.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import jsonschema
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = ROOT / "contracts/fixtures/s1_acquisition_round_trip_v1_fixture.json"
SCHEMAS_DIR = ROOT / "contracts/schemas"
COMMON_SCHEMAS_DIR = SCHEMAS_DIR / "common"

PAYLOAD_SCHEMA_FILES = {
    "RawSensorSample": "raw_sensor_sample_v1.schema.json",
    "LocationGnssFix": "location_gnss_fix_v1.schema.json",
}

SENSOR_ANDROID_TYPES = {
    "ACCELEROMETER": 1,
    "MAGNETIC_FIELD": 2,
    "GYROSCOPE": 4,
    "AMBIENT_TEMPERATURE": 13,
}

GNSS_NULLABLE_FIELDS = {
    "alt_m",
    "vacc_m",
    "speed_mps",
    "speed_acc_mps",
    "bearing_deg",
    "bearing_acc_deg",
}


class FixtureValidationError(ValueError):
    """Raised when evidence violates an S1 schema or semantic invariant."""


def _reject_non_standard_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant is prohibited: {value}")


def load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_non_standard_constant,
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic strict-JSON bytes used for fidelity comparison."""
    try:
        text = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise FixtureValidationError(f"value is not strict JSON: {exc}") from exc
    return text.encode("utf-8")


def _load_contracts() -> tuple[
    jsonschema.Draft202012Validator,
    dict[str, jsonschema.Draft202012Validator],
]:
    timestamp = load_json(COMMON_SCHEMAS_DIR / "timestamp_v1.schema.json")
    provenance = load_json(COMMON_SCHEMAS_DIR / "provenance_v1.schema.json")
    envelope = load_json(COMMON_SCHEMAS_DIR / "evidence_envelope_v1.schema.json")

    for schema in (timestamp, provenance, envelope):
        jsonschema.Draft202012Validator.check_schema(schema)

    registry = (
        Registry()
        .with_resource("timestamp_v1.schema.json", Resource.from_contents(timestamp))
        .with_resource("provenance_v1.schema.json", Resource.from_contents(provenance))
        .with_resource(timestamp["$id"], Resource.from_contents(timestamp))
        .with_resource(provenance["$id"], Resource.from_contents(provenance))
    )
    envelope_validator = jsonschema.Draft202012Validator(envelope, registry=registry)

    payload_validators = {}
    for payload_type, filename in PAYLOAD_SCHEMA_FILES.items():
        schema = load_json(SCHEMAS_DIR / filename)
        jsonschema.Draft202012Validator.check_schema(schema)
        payload_validators[payload_type] = jsonschema.Draft202012Validator(schema)
    return envelope_validator, payload_validators


def _validate_schema(
    validator: jsonschema.Draft202012Validator,
    value: Any,
    label: str,
) -> None:
    errors = sorted(
        validator.iter_errors(value),
        key=lambda error: list(error.absolute_path),
    )
    if not errors:
        return

    error = errors[0]
    path = ".".join(str(part) for part in error.absolute_path) or "<root>"
    raise FixtureValidationError(f"{label}.{path}: {error.message}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureValidationError(message)


def _validate_envelope_coherence(
    envelope: dict[str, Any],
    index: int,
) -> None:
    label = f"records[{index}]"
    timestamp = envelope["timestamp"]
    provenance = envelope["provenance"]
    payload = envelope["payload"]

    _require(
        envelope["schema_version"] == 1,
        f"{label}: envelope schema_version must be 1",
    )
    _require(
        payload["schema_version"] == 1,
        f"{label}: payload schema_version must be 1",
    )
    _require(
        timestamp["clock_id"] == "CLOCK_BOOTTIME",
        f"{label}: S1 monotonic clock_id must be CLOCK_BOOTTIME",
    )
    _require(
        timestamp.get("source_timestamp_ns") == payload["source_timestamp_ns"],
        f"{label}: envelope and payload source timestamps differ",
    )
    _require(
        timestamp["arrival_elapsed_realtime_ns"]
        == payload["arrival_elapsed_realtime_ns"],
        f"{label}: envelope and payload arrival timestamps differ",
    )
    _require(
        timestamp["epoch_ns"] == payload["source_timestamp_ns"],
        f"{label}: fixture epoch must preserve its source monotonic timestamp",
    )
    _require(
        payload["source_timestamp_ns"]
        <= payload["arrival_elapsed_realtime_ns"],
        f"{label}: callback arrival precedes the source timestamp",
    )
    _require(
        provenance["evidence_id"] == payload["evidence_id"],
        f"{label}: envelope and payload evidence IDs differ",
    )
    _require(
        provenance["provenance_type"] == "DETERMINISTIC_REPLAY",
        f"{label}: synthetic S1 fixture must be labelled DETERMINISTIC_REPLAY",
    )
    _require(
        provenance.get("synthetic") is True,
        f"{label}: synthetic S1 fixture must set provenance.synthetic=true",
    )

    gate = envelope["validity_gate"]
    _require(
        gate["is_finite"] is True,
        f"{label}: valid fixture must assert finite values",
    )
    _require(
        gate["is_valid"] is True,
        f"{label}: golden fixture must be schema-valid",
    )


def _validate_sensor_sample(
    envelope: dict[str, Any],
    index: int,
) -> None:
    label = f"records[{index}].payload"
    payload = envelope["payload"]
    provenance = envelope["provenance"]
    sensor_type = payload["sensor_type"]
    values = payload["values"]

    _require(
        payload["session_id"] == provenance["session_id"],
        f"{label}: session IDs differ",
    )
    _require(
        payload["stream_id"] == provenance["stream_id"],
        f"{label}: stream IDs differ",
    )
    _require(
        all(
            isinstance(value, (int, float)) and math.isfinite(value)
            for value in values
        ),
        f"{label}: every sensor value must be finite",
    )
    _require(
        sensor_type in SENSOR_ANDROID_TYPES,
        f"{label}: unknown sensor type {sensor_type!r}",
    )
    _require(
        payload["source_metadata"]["android_sensor_type"]
        == SENSOR_ANDROID_TYPES[sensor_type],
        f"{label}: Android hardware type does not match sensor_type",
    )

    magnitude = math.sqrt(sum(float(value) ** 2 for value in values))
    if sensor_type == "ACCELEROMETER":
        _require(
            magnitude <= 160.0,
            f"{label}: acceleration exceeds 160 m/s^2 envelope",
        )
    if sensor_type == "GYROSCOPE":
        _require(
            magnitude <= 35.0,
            f"{label}: angular velocity exceeds 35 rad/s envelope",
        )


def _validate_gnss_fix(
    envelope: dict[str, Any],
    index: int,
) -> None:
    label = f"records[{index}].payload"
    payload = envelope["payload"]
    field_mask = set(payload["field_mask"])

    _require(
        payload["provider"] == "GPS_PROVIDER",
        f"{label}: S1 baseline provider must be GPS_PROVIDER",
    )

    for field in GNSS_NULLABLE_FIELDS:
        _require(
            (field in field_mask) == (payload[field] is not None),
            f"{label}: field_mask and nullable value disagree for {field}",
        )

    for field in ("lat_deg", "lon_deg", "hacc_m"):
        _require(
            math.isfinite(float(payload[field])),
            f"{label}: {field} must be finite",
        )

    for field in GNSS_NULLABLE_FIELDS:
        if payload[field] is not None:
            _require(
                math.isfinite(float(payload[field])),
                f"{label}: {field} must be finite when present",
            )


def _validate_stream_order(records: list[dict[str, Any]]) -> None:
    sensor_streams: dict[
        tuple[str, str],
        list[tuple[int, int]],
    ] = defaultdict(list)
    location_streams: dict[
        tuple[str, str],
        list[int],
    ] = defaultdict(list)

    for envelope in records:
        provenance = envelope["provenance"]
        payload = envelope["payload"]

        if envelope["payload_type"] == "RawSensorSample":
            key = (
                provenance["session_id"],
                provenance["stream_id"],
            )
            sensor_streams[key].append(
                (
                    payload["sequence"],
                    payload["source_timestamp_ns"],
                )
            )
        else:
            key = (
                provenance["session_id"],
                payload["provider"],
            )
            location_streams[key].append(
                payload["source_timestamp_ns"]
            )

    for stream, observations in sensor_streams.items():
        sequences = [item[0] for item in observations]
        timestamps = [item[1] for item in observations]

        _require(
            all(
                current > previous
                for previous, current in zip(sequences, sequences[1:])
            ),
            f"I-01 sequence is not strictly increasing for stream {stream}",
        )
        _require(
            all(
                current > previous
                for previous, current in zip(timestamps, timestamps[1:])
            ),
            f"I-01 source timestamp is not strictly increasing for stream {stream}",
        )

    for stream, timestamps in location_streams.items():
        _require(
            all(
                current > previous
                for previous, current in zip(timestamps, timestamps[1:])
            ),
            f"I-02 source timestamp is not strictly increasing for provider {stream}",
        )


def _round_trip_through_contract_binding(
    envelope: dict[str, Any],
    index: int,
) -> None:
    contracts_path = ROOT / "tools/contracts"
    if str(contracts_path) not in sys.path:
        sys.path.insert(0, str(contracts_path))

    from sih26168_contracts.models import EvidenceEnvelopeV1

    parsed = EvidenceEnvelopeV1.from_dict(envelope)
    serialized = parsed.to_dict()

    _require(
        serialized == envelope,
        f"records[{index}]: generated Python binding changed evidence",
    )

    encoded = canonical_json_bytes(serialized)
    reparsed = json.loads(
        encoded.decode("utf-8"),
        parse_constant=_reject_non_standard_constant,
    )
    _require(
        reparsed == envelope,
        f"records[{index}]: canonical JSON round-trip changed evidence",
    )


def validate_document(document: dict[str, Any]) -> dict[str, Any]:
    """Validate an in-memory S1 fixture and return its evidence summary."""
    _require(
        isinstance(document, dict),
        "fixture root must be an object",
    )
    _require(
        document.get("fixture_version") == 1,
        "fixture_version must be 1",
    )
    _require(
        document.get("classification") == "SYNTHETIC_PUBLIC_TEST_ONLY",
        "fixture must be classified SYNTHETIC_PUBLIC_TEST_ONLY",
    )

    records = document.get("records")
    _require(
        isinstance(records, list) and records,
        "fixture records must be a non-empty array",
    )

    envelope_validator, payload_validators = _load_contracts()
    evidence_ids = set()
    counts = {
        payload_type: 0
        for payload_type in PAYLOAD_SCHEMA_FILES
    }

    for index, envelope in enumerate(records):
        _validate_schema(
            envelope_validator,
            envelope,
            f"records[{index}]",
        )

        payload_type = envelope["payload_type"]
        _require(
            payload_type in payload_validators,
            f"records[{index}]: unsupported payload_type {payload_type!r}",
        )

        _validate_schema(
            payload_validators[payload_type],
            envelope["payload"],
            f"records[{index}].payload",
        )
        _validate_envelope_coherence(envelope, index)

        evidence_id = envelope["provenance"]["evidence_id"]
        _require(
            evidence_id not in evidence_ids,
            f"duplicate evidence_id: {evidence_id}",
        )
        evidence_ids.add(evidence_id)

        if payload_type == "RawSensorSample":
            _validate_sensor_sample(envelope, index)
        else:
            _validate_gnss_fix(envelope, index)

        _round_trip_through_contract_binding(envelope, index)
        counts[payload_type] += 1

    _validate_stream_order(records)

    canonical = canonical_json_bytes(document)
    reparsed_document = json.loads(
        canonical.decode("utf-8"),
        parse_constant=_reject_non_standard_constant,
    )
    _require(
        reparsed_document == document,
        "whole-fixture canonical round-trip changed evidence",
    )

    return {
        "fixture_id": document.get("fixture_id"),
        "record_count": len(records),
        "raw_sensor_sample_count": counts["RawSensorSample"],
        "location_gnss_fix_count": counts["LocationGnssFix"],
        "sha256": hashlib.sha256(canonical).hexdigest(),
    }


def validate_fixture(
    path: Path = DEFAULT_FIXTURE,
) -> dict[str, Any]:
    return validate_document(load_json(path))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and canonically round-trip the synthetic "
            "S1 I-01/I-02 fixture."
        )
    )
    parser.add_argument(
        "fixture",
        nargs="?",
        type=Path,
        default=DEFAULT_FIXTURE,
        help=(
            "fixture path "
            "(defaults to the repository S1 synthetic fixture)"
        ),
    )
    args = parser.parse_args()

    try:
        summary = validate_fixture(args.fixture)
    except (
        FixtureValidationError,
        json.JSONDecodeError,
        OSError,
        ValueError,
    ) as exc:
        print(
            f"FAIL: S1 fixture round-trip: {exc}",
            file=sys.stderr,
        )
        return 1

    print(
        "PASS: S1 fixture round-trip "
        f"records={summary['record_count']} "
        f"i01={summary['raw_sensor_sample_count']} "
        f"i02={summary['location_gnss_fix_count']} "
        f"sha256={summary['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())