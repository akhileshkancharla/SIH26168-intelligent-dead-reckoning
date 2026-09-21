#!/usr/bin/env python3
"""WP-10.5 (Issue #83): runtime-feature and forbidden-label firewall.

Per C-15 in docs/architecture/SIH26168_High_Level_Architecture_Revision3.md,
IO-VNBD carries both fields a deployed model may legitimately consume at
inference time (live sensor/GNSS-derived features) and fields that only
exist as ground truth or reference telemetry (vehicle CAN/precise-position
labels, evaluation-only fields). Training a model on a forbidden label as
if it were an input feature is a leakage failure mode distinct from --
and just as serious as -- the file/session leakage that
tools/dataset/grouping.py and tools/dataset/splits.py guard against; this
module is the deny-by-default gate for that failure mode.

The active inventory in config/feature_firewall.json freezes the minimal
nine-channel causal phone-IMU profile from the Development Design Baseline and
the complete 29-field V29_MAIN vehicle/reference schema from the accepted S0
audit register. Forbidden IDs use `<schema_id>.<interpreted_field>` so generic
names such as `latitude` cannot be confused with phone fields. Private data and
source paths remain outside Git; FEATURE_CONTRACT_PROPOSAL.md records the
sanitized source revision and evidence hashes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
FIREWALL_CONFIG_SCHEMA_PATH = ROOT / "tools/dataset/config/feature_firewall_config.schema.json"
DEFAULT_FIREWALL_CONFIG_PATH = ROOT / "tools/dataset/config/feature_firewall.json"

TEMPLATE_STATUS = "TEMPLATE_PENDING_REVIEW"
ACTIVE_STATUS = "ACTIVE"

_TEMPLATE_FEATURE_PLACEHOLDER_PREFIX = "PENDING_FEATURE_"
_TEMPLATE_LABEL_PLACEHOLDER_PREFIX = "PENDING_LABEL_"

ALLOWED = "ALLOWED"
FORBIDDEN_LABEL = "FORBIDDEN_LABEL"
NOT_RUNTIME_AVAILABLE = "NOT_RUNTIME_AVAILABLE"


class FeatureFirewallError(Exception):
    """Raised for any firewall configuration or enforcement failure.

    A hard stop, never a warning to log and continue past -- matching
    C-15's own "quarantine; stop the experiment" failure mode.
    """


def load_firewall_config_schema() -> Dict[str, Any]:
    return json.loads(FIREWALL_CONFIG_SCHEMA_PATH.read_text(encoding="utf-8"))


def load_firewall_document(path: Path = DEFAULT_FIREWALL_CONFIG_PATH) -> Dict[str, Any]:
    """Load, structurally validate, and cross-check a firewall config document.

    Structural validity alone does not mean the firewall is usable for
    real enforcement -- see require_active_firewall for the status gate.
    Raises FeatureFirewallError if a feature name appears in both
    `runtime_allowed_features` and `forbidden_labels` -- forbidden takes
    precedence as defense in depth (see classify_feature), but a document
    declaring the same name as both allowed and forbidden is internally
    contradictory and must be rejected outright rather than silently
    resolved.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FeatureFirewallError(f"firewall config is not valid JSON: {path}: {exc}") from exc
    schema = load_firewall_config_schema()
    try:
        jsonschema.Draft202012Validator(schema).validate(document)
    except jsonschema.ValidationError as exc:
        raise FeatureFirewallError(f"firewall config failed schema validation: {exc.message}") from exc

    overlap = set(document.get("runtime_allowed_features", [])) & set(document.get("forbidden_labels", []))
    if overlap:
        raise FeatureFirewallError(
            "firewall config declares the same name in both runtime_allowed_features "
            f"and forbidden_labels: {sorted(overlap)}; this is an internally "
            "contradictory configuration and must be fixed by a human reviewer, not "
            "silently resolved"
        )
    return document


def is_template_firewall(document: Dict[str, Any]) -> bool:
    """True if `document` is (or looks like) the unfilled template.

    Checked two ways -- by declared status, and independently by whether
    *any* entry on either list still carries its placeholder prefix (not
    only when every entry on a side does) -- so a document hand-edited to
    claim ACTIVE without actually replacing every placeholder entry is
    still caught. An ACTIVE list containing real names plus one leftover
    PENDING_FEATURE_*/PENDING_LABEL_* entry is exactly as unreviewed as a
    side where nothing was replaced at all -- the firewall contract only
    holds once every entry on both sides is genuine.
    """
    if document.get("status") == TEMPLATE_STATUS:
        return True

    features = document.get("runtime_allowed_features", [])
    labels = document.get("forbidden_labels", [])
    features_have_placeholder = any(str(f).startswith(_TEMPLATE_FEATURE_PLACEHOLDER_PREFIX) for f in features)
    labels_have_placeholder = any(str(l).startswith(_TEMPLATE_LABEL_PLACEHOLDER_PREFIX) for l in labels)
    return features_have_placeholder or labels_have_placeholder


def require_active_firewall(document: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Return (runtime_allowed_features, forbidden_labels), or raise.

    Raises FeatureFirewallError if `document` fails structural (schema)
    validation, declares the same name on both lists, has a status that
    is not ACTIVE, or is ACTIVE but still structurally indistinguishable
    from the unfilled template (see is_template_firewall) -- any of these
    means real enforcement must not proceed. The structural and overlap
    checks run even when `document` did not come from
    load_firewall_document: this is the public enforcement gate, and an
    in-memory document must not be able to bypass required fields,
    uniqueness, or the allowed/forbidden contradiction guard just by
    skipping the loader.
    """
    schema = load_firewall_config_schema()
    try:
        jsonschema.Draft202012Validator(schema).validate(document)
    except jsonschema.ValidationError as exc:
        raise FeatureFirewallError(f"firewall config failed schema validation: {exc.message}") from exc

    overlap = set(document.get("runtime_allowed_features", [])) & set(document.get("forbidden_labels", []))
    if overlap:
        raise FeatureFirewallError(
            "firewall config declares the same name in both runtime_allowed_features "
            f"and forbidden_labels: {sorted(overlap)}; this is an internally "
            "contradictory configuration and must be fixed by a human reviewer, not "
            "silently resolved"
        )

    if document.get("status") != ACTIVE_STATUS or is_template_firewall(document):
        raise FeatureFirewallError(
            "runtime-feature/forbidden-label firewall is not active: it is still "
            f"an unresolved {TEMPLATE_STATUS} template. A human with the "
            "runtime feature spec and SIH26168_IO_VNBD_Dataset_Feasibility_Audit_v1.1 "
            "must replace both placeholder lists with the real runtime-available "
            "feature names and the real ground-truth-only label names, and set "
            "status to ACTIVE, before this firewall can be enforced against any "
            "feature set -- an unresolved firewall is itself a stop "
            "condition, per C-15's 'quarantine; stop the experiment' failure mode."
        )
    return list(document["runtime_allowed_features"]), list(document["forbidden_labels"])


def classify_feature(feature_name: str, runtime_allowed: List[str], forbidden_labels: List[str]) -> str:
    """Classify a single feature name as ALLOWED, FORBIDDEN_LABEL, or
    NOT_RUNTIME_AVAILABLE.

    Forbidden-label status is checked first and wins over runtime
    availability, even if a name were (incorrectly) present on both
    lists -- this is the defense-in-depth ordering described in
    config/feature_firewall_config.schema.json's `forbidden_labels`
    description. In normal operation load_firewall_document already
    rejects any document where the two lists overlap, so this ordering
    only matters for a firewall assembled directly in memory by a
    caller that skipped that check.
    """
    if feature_name in forbidden_labels:
        return FORBIDDEN_LABEL
    if feature_name in runtime_allowed:
        return ALLOWED
    return NOT_RUNTIME_AVAILABLE


def audit_feature_set(proposed_features: List[str], firewall_document: Dict[str, Any]) -> Dict[str, str]:
    """Return {feature_name: classification} for every name in
    `proposed_features`, without raising.

    Pure classification, for audit/reporting -- see enforce_feature_set
    for the hard-stop variant that a training pipeline should actually
    call before consuming a feature set.
    """
    runtime_allowed, forbidden_labels = require_active_firewall(firewall_document)
    return {
        feature_name: classify_feature(feature_name, runtime_allowed, forbidden_labels)
        for feature_name in proposed_features
    }


def enforce_feature_set(proposed_features: List[str], firewall_document: Dict[str, Any]) -> None:
    """Raise FeatureFirewallError if `proposed_features` contains any name
    that is not ALLOWED under the active firewall.

    Both FORBIDDEN_LABEL and NOT_RUNTIME_AVAILABLE names are hard-stop
    failures -- a name is never allowed through by omission. This is the
    deny-by-default gate a training/feature-extraction pipeline is meant
    to call before consuming any proposed feature set.
    """
    classifications = audit_feature_set(proposed_features, firewall_document)
    forbidden = sorted(name for name, verdict in classifications.items() if verdict == FORBIDDEN_LABEL)
    not_available = sorted(name for name, verdict in classifications.items() if verdict == NOT_RUNTIME_AVAILABLE)
    if forbidden or not_available:
        raise FeatureFirewallError(
            "proposed feature set failed the runtime-feature/forbidden-label "
            f"firewall; quarantine and stop the experiment: forbidden_labels={forbidden}, "
            f"not_runtime_available={not_available}"
        )


def enforce_feature_window(records: list[dict], firewall_document: Dict[str, Any],
                           *, start_ns: int, end_ns: int, clock_id: str) -> None:
    """Compose active configuration enforcement with the frozen metadata gate.

    A trusted extractor must construct provenance from the reviewed source map.
    Any unresolved template still stops real-data use at the first gate.
    """
    from tools.dataset.feature_provenance import validate_minimal_window

    require_active_firewall(firewall_document)
    try:
        validate_minimal_window(records, start_ns=start_ns, end_ns=end_ns, clock_id=clock_id)
    except ValueError as exc:
        raise FeatureFirewallError(str(exc)) from exc
    enforce_feature_set([record["name"] for record in records], firewall_document)
