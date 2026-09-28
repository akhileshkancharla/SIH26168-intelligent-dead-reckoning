"""Frozen, deterministic GNSS-blackout masking for WP-11.3.

This module builds an inference view from already-extracted, synchronized
feature records.  It never edits the source records: GNSS fields hidden by a
declared half-open blackout interval are moved to a separate reference view
for evaluation and are absent from the inference view.  No interpolation,
forward fill, sentinel replacement, model training, or metric computation is
performed here.

The protocol deliberately models only the offline C-16 boundary.  Runtime
outage detection and navigation state remain owned by C-09/C-07, and the
authoritative I-14 contract remains outside this work package.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence


PROTOCOL_SCHEMA_VERSION = 1
FROZEN_STATUS = "FROZEN"
SOFTWARE_SIMULATED = "SOFTWARE_SIMULATED"

# Offline feature names derived from the measurement members of the
# authoritative I-02 LocationGnssFixV1 contract.  Provenance, clock, mock and
# field-mask metadata are deliberately excluded: a GNSS blackout may withhold
# measurements from inference, but it must not erase their audit identity.
APPROVED_GNSS_FEATURES = frozenset(
    {
        "gnss.lat_deg",
        "gnss.lon_deg",
        "gnss.alt_m",
        "gnss.hacc_m",
        "gnss.vacc_m",
        "gnss.speed_mps",
        "gnss.speed_acc_mps",
        "gnss.bearing_deg",
        "gnss.bearing_acc_deg",
    }
)

_PROTOCOL_KEYS = {"schema_version", "protocol_id", "clock_id", "status", "intervals"}
_INTERVAL_KEYS = {
    "event_id",
    "mask_id",
    "start_ns",
    "end_ns",
    "type",
    "reason",
    "hidden_fields",
}
_RECORD_KEYS = {"record_id", "epoch_ns", "clock_id", "features"}


class BlackoutMaskError(ValueError):
    """Raised when a protocol or feature record fails closed."""


@dataclass(frozen=True)
class BlackoutInterval:
    event_id: str
    mask_id: str
    start_ns: int
    end_ns: int
    reason: str
    hidden_fields: tuple[str, ...]
    type: str = SOFTWARE_SIMULATED

    def contains(self, epoch_ns: int) -> bool:
        """Return whether ``epoch_ns`` lies in this half-open interval."""

        return self.start_ns <= epoch_ns < self.end_ns


@dataclass(frozen=True)
class FrozenBlackoutProtocol:
    protocol_id: str
    clock_id: str
    intervals: tuple[BlackoutInterval, ...]
    sha256: str
    schema_version: int = PROTOCOL_SCHEMA_VERSION
    status: str = FROZEN_STATUS


@dataclass(frozen=True)
class MaskedFeatureRecord:
    record_id: str
    epoch_ns: int
    clock_id: str
    inference_features: Mapping[str, Any]
    reference_features: Mapping[str, Any]
    active_mask_id: str | None


@dataclass(frozen=True)
class MaskAuditEvent:
    record_id: str
    epoch_ns: int
    event_id: str
    mask_id: str
    hidden_fields: tuple[str, ...]


@dataclass(frozen=True)
class MaskingResult:
    protocol_sha256: str
    records: tuple[MaskedFeatureRecord, ...]
    audit_events: tuple[MaskAuditEvent, ...]


def _nonempty_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BlackoutMaskError(f"{field} must be a non-empty string")
    return value


def _timestamp(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise BlackoutMaskError(f"{field} must be a non-negative integer timestamp")
    return value


def _canonical_document(
    protocol_id: str,
    clock_id: str,
    intervals: Sequence[BlackoutInterval],
) -> dict[str, Any]:
    return {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "protocol_id": protocol_id,
        "clock_id": clock_id,
        "status": FROZEN_STATUS,
        "intervals": [
            {
                "event_id": interval.event_id,
                "mask_id": interval.mask_id,
                "start_ns": interval.start_ns,
                "end_ns": interval.end_ns,
                "type": interval.type,
                "reason": interval.reason,
                "hidden_fields": list(interval.hidden_fields),
            }
            for interval in intervals
        ],
    }


def freeze_protocol(document: Mapping[str, Any]) -> FrozenBlackoutProtocol:
    """Validate, normalize, and content-address a blackout protocol.

    Intervals are sorted by time, hidden fields are sorted, and the digest is
    computed from compact canonical JSON.  Thus semantically identical input
    ordering produces the same frozen identity.  Training/evaluation callers
    should record ``sha256`` alongside every run that consumes the protocol.
    """

    if not isinstance(document, Mapping) or set(document) != _PROTOCOL_KEYS:
        raise BlackoutMaskError(f"protocol fields must match exactly {sorted(_PROTOCOL_KEYS)}")
    if type(document["schema_version"]) is not int or document["schema_version"] != PROTOCOL_SCHEMA_VERSION:
        raise BlackoutMaskError(f"unsupported protocol schema_version: {document['schema_version']!r}")
    if document["status"] != FROZEN_STATUS:
        raise BlackoutMaskError("protocol status must be FROZEN before it can be consumed")

    protocol_id = _nonempty_text(document["protocol_id"], "protocol_id")
    clock_id = _nonempty_text(document["clock_id"], "clock_id")
    raw_intervals = document["intervals"]
    if not isinstance(raw_intervals, list) or not raw_intervals:
        raise BlackoutMaskError("intervals must be a non-empty list")

    intervals: list[BlackoutInterval] = []
    for index, item in enumerate(raw_intervals):
        prefix = f"intervals[{index}]"
        if not isinstance(item, Mapping) or set(item) != _INTERVAL_KEYS:
            raise BlackoutMaskError(f"{prefix} fields must match exactly {sorted(_INTERVAL_KEYS)}")
        event_id = _nonempty_text(item["event_id"], f"{prefix}.event_id")
        mask_id = _nonempty_text(item["mask_id"], f"{prefix}.mask_id")
        reason = _nonempty_text(item["reason"], f"{prefix}.reason")
        start_ns = _timestamp(item["start_ns"], f"{prefix}.start_ns")
        end_ns = _timestamp(item["end_ns"], f"{prefix}.end_ns")
        if start_ns >= end_ns:
            raise BlackoutMaskError(f"{prefix} must have start_ns < end_ns")
        if item["type"] != SOFTWARE_SIMULATED:
            raise BlackoutMaskError(
                f"{prefix}.type must be SOFTWARE_SIMULATED; natural outages are not training masks"
            )
        raw_hidden = item["hidden_fields"]
        if not isinstance(raw_hidden, list) or not raw_hidden:
            raise BlackoutMaskError(f"{prefix}.hidden_fields must be a non-empty list")
        if any(not isinstance(name, str) or not name.strip() for name in raw_hidden):
            raise BlackoutMaskError(f"{prefix}.hidden_fields must contain non-empty strings")
        if len(set(raw_hidden)) != len(raw_hidden):
            raise BlackoutMaskError(f"{prefix}.hidden_fields contains duplicates")
        unsupported_hidden = sorted(set(raw_hidden) - APPROVED_GNSS_FEATURES)
        if unsupported_hidden:
            raise BlackoutMaskError(
                f"{prefix}.hidden_fields contains fields outside the approved I-02 GNSS "
                f"measurement set: {unsupported_hidden}"
            )
        intervals.append(
            BlackoutInterval(
                event_id=event_id,
                mask_id=mask_id,
                start_ns=start_ns,
                end_ns=end_ns,
                reason=reason,
                hidden_fields=tuple(sorted(raw_hidden)),
            )
        )

    if len({interval.event_id for interval in intervals}) != len(intervals):
        raise BlackoutMaskError("event_id values must be unique")
    if len({interval.mask_id for interval in intervals}) != len(intervals):
        raise BlackoutMaskError("mask_id values must be unique")

    intervals.sort(key=lambda interval: (interval.start_ns, interval.end_ns, interval.mask_id))
    for previous, current in zip(intervals, intervals[1:]):
        if current.start_ns < previous.end_ns:
            raise BlackoutMaskError(
                f"blackout intervals overlap: {previous.mask_id!r} and {current.mask_id!r}"
            )

    canonical = _canonical_document(protocol_id, clock_id, intervals)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return FrozenBlackoutProtocol(
        protocol_id=protocol_id,
        clock_id=clock_id,
        intervals=tuple(intervals),
        sha256=digest,
    )


def _validate_frozen_protocol(protocol: FrozenBlackoutProtocol) -> None:
    """Reject a manually forged or subsequently inconsistent protocol object."""

    if not isinstance(protocol, FrozenBlackoutProtocol):
        raise BlackoutMaskError("protocol must be produced by freeze_protocol")
    rebuilt = freeze_protocol(
        _canonical_document(protocol.protocol_id, protocol.clock_id, protocol.intervals)
    )
    if rebuilt != protocol:
        raise BlackoutMaskError("frozen blackout protocol identity or canonical content is inconsistent")


def verify_protocol_identity(protocol: FrozenBlackoutProtocol, expected_sha256: str) -> None:
    """Fail closed if a run references a different frozen protocol."""

    _validate_frozen_protocol(protocol)
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise BlackoutMaskError("expected protocol SHA-256 must be 64 hexadecimal characters")
    try:
        int(expected_sha256, 16)
    except ValueError as exc:
        raise BlackoutMaskError("expected protocol SHA-256 must be hexadecimal") from exc
    if protocol.sha256 != expected_sha256.lower():
        raise BlackoutMaskError("frozen blackout protocol SHA-256 mismatch")


def _validate_scalar(value: Any, field: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    raise BlackoutMaskError(f"{field} must be a finite JSON scalar or null")


def mask_records(
    records: Sequence[Mapping[str, Any]],
    protocol: FrozenBlackoutProtocol,
    *,
    expected_protocol_sha256: str | None = None,
) -> MaskingResult:
    """Return immutable inference/reference views under ``protocol``.

    The input must be a strictly time-ordered sequence on the protocol clock.
    For a record in ``[start_ns, end_ns)``, configured hidden fields are absent
    from ``inference_features`` and copied to ``reference_features``.  Values
    are never zeroed or forward-filled, preventing the original value from
    leaking through a sentinel or derived replacement.
    """

    _validate_frozen_protocol(protocol)
    if expected_protocol_sha256 is not None:
        verify_protocol_identity(protocol, expected_protocol_sha256)
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise BlackoutMaskError("records must be a sequence")
    if not records:
        raise BlackoutMaskError("records must be non-empty")

    output: list[MaskedFeatureRecord] = []
    events: list[MaskAuditEvent] = []
    seen_ids: set[str] = set()
    previous_epoch: int | None = None

    for index, record in enumerate(records):
        prefix = f"records[{index}]"
        if not isinstance(record, Mapping) or set(record) != _RECORD_KEYS:
            raise BlackoutMaskError(f"{prefix} fields must match exactly {sorted(_RECORD_KEYS)}")
        record_id = _nonempty_text(record["record_id"], f"{prefix}.record_id")
        if record_id in seen_ids:
            raise BlackoutMaskError(f"duplicate record_id: {record_id!r}")
        seen_ids.add(record_id)
        epoch_ns = _timestamp(record["epoch_ns"], f"{prefix}.epoch_ns")
        if previous_epoch is not None and epoch_ns <= previous_epoch:
            raise BlackoutMaskError("records must be strictly increasing by epoch_ns")
        previous_epoch = epoch_ns
        if record["clock_id"] != protocol.clock_id:
            raise BlackoutMaskError(f"{prefix}.clock_id does not match the frozen protocol")
        features = record["features"]
        if not isinstance(features, Mapping):
            raise BlackoutMaskError(f"{prefix}.features must be a mapping")
        for name, value in features.items():
            if not isinstance(name, str) or not name.strip():
                raise BlackoutMaskError(f"{prefix}.features keys must be non-empty strings")
            _validate_scalar(value, f"{prefix}.features[{name!r}]")

        interval = next((candidate for candidate in protocol.intervals if candidate.contains(epoch_ns)), None)
        hidden = set(interval.hidden_fields) if interval else set()
        inference = {name: value for name, value in features.items() if name not in hidden}
        reference = {name: value for name, value in features.items() if name in hidden}
        output.append(
            MaskedFeatureRecord(
                record_id=record_id,
                epoch_ns=epoch_ns,
                clock_id=protocol.clock_id,
                inference_features=MappingProxyType(inference),
                reference_features=MappingProxyType(reference),
                active_mask_id=interval.mask_id if interval else None,
            )
        )
        if interval is not None:
            events.append(
                MaskAuditEvent(
                    record_id=record_id,
                    epoch_ns=epoch_ns,
                    event_id=interval.event_id,
                    mask_id=interval.mask_id,
                    hidden_fields=tuple(sorted(reference)),
                )
            )

    result = MaskingResult(protocol_sha256=protocol.sha256, records=tuple(output), audit_events=tuple(events))
    assert_no_withheld_features(result, protocol)
    return result


def assert_no_withheld_features(result: MaskingResult, protocol: FrozenBlackoutProtocol) -> None:
    """Defense-in-depth canary proving no active mask field reached inference."""

    intervals_by_mask = {interval.mask_id: interval for interval in protocol.intervals}
    if result.protocol_sha256 != protocol.sha256:
        raise BlackoutMaskError("masking result references a different frozen protocol")
    for record in result.records:
        if record.active_mask_id is None:
            continue
        interval = intervals_by_mask.get(record.active_mask_id)
        if interval is None:
            raise BlackoutMaskError(f"unknown active mask_id in result: {record.active_mask_id!r}")
        leaked = set(record.inference_features) & set(interval.hidden_fields)
        if leaked:
            raise BlackoutMaskError(
                f"withheld GNSS field reached inference for {record.record_id!r}: {sorted(leaked)}"
            )
