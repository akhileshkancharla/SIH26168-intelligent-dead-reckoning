#!/usr/bin/env python3
"""WP-10.2 (Issue #80): six-schema IO-VNBD validation allowlist.

Per C-15 in docs/architecture/SIH26168_High_Level_Architecture_Revision3.md
and R-007 in docs/architecture/SIH26168_Risk_Register_v1.csv, real IO-VNBD
data uses exactly six schemas; anything else must be quarantined, never
silently accepted ("Quarantine unknown schema/hash/unit; stop experiment").

This module is the enforcement *engine* only. The actual six real IO-VNBD
schema identifiers are not known to this repository: they come from
SIH26168_IO_VNBD_Dataset_Feasibility_Audit_v1.1, which is listed as an
architecture evidence input in
docs/architecture/SIH26168_ARCHITECTURE_MANIFEST_v1.json but is not itself
committed here (organizer-supplied, and this WP must not fabricate
architecture or dataset facts it does not have). The shipped
config/io_vnbd_schema_allowlist.json is therefore a TEMPLATE with its
`status` field set to TEMPLATE_PENDING_S0_AUDIT_ASSIGNMENT: this module
refuses to enforce a non-ACTIVE allowlist, so a template can never be
mistaken for a real, reviewed allowlist. A human with the feasibility
audit must replace the six placeholder entries and set status to ACTIVE
before this module is used against any real dataset.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST_CONFIG_SCHEMA_PATH = ROOT / "tools/dataset/config/schema_allowlist_config.schema.json"
DEFAULT_ALLOWLIST_CONFIG_PATH = ROOT / "tools/dataset/config/io_vnbd_schema_allowlist.json"

TEMPLATE_STATUS = "TEMPLATE_PENDING_S0_AUDIT_ASSIGNMENT"
ACTIVE_STATUS = "ACTIVE"

_TEMPLATE_PLACEHOLDER_PREFIX = "PENDING_SCHEMA_"


class SchemaAllowlistError(Exception):
    """Raised for any allowlist configuration or enforcement failure.

    Matches C-15's own failure mode: this is always a hard stop, never a
    warning to log and continue past.
    """


def load_allowlist_config_schema() -> Dict[str, Any]:
    return json.loads(ALLOWLIST_CONFIG_SCHEMA_PATH.read_text(encoding="utf-8"))


def load_allowlist_document(path: Path = DEFAULT_ALLOWLIST_CONFIG_PATH) -> Dict[str, Any]:
    """Load and structurally validate an allowlist config document.

    Structural validity alone does not mean the allowlist is usable for
    real enforcement -- see require_active_allowlist for the status gate.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchemaAllowlistError(f"allowlist config is not valid JSON: {path}: {exc}") from exc
    schema = load_allowlist_config_schema()
    try:
        jsonschema.Draft202012Validator(schema).validate(document)
    except jsonschema.ValidationError as exc:
        raise SchemaAllowlistError(f"allowlist config failed schema validation: {exc.message}") from exc
    return document


def is_template_allowlist(document: Dict[str, Any]) -> bool:
    """True if `document` is (or looks like) the unfilled template.

    Checked two ways -- by declared status, and independently by whether
    *any* entry still carries the placeholder prefix (not only when every
    entry does) -- so a document with, say, five real identifiers and one
    remaining PENDING_SCHEMA_* placeholder is still caught. A mixed
    real/placeholder allowlist is exactly as unreviewed and unsafe to
    enforce as one where nothing was replaced at all: the six-schema
    contract only holds once every entry is genuine.
    """
    if document.get("status") == TEMPLATE_STATUS:
        return True
    entries = document.get("allowlist", [])
    return any(str(e).startswith(_TEMPLATE_PLACEHOLDER_PREFIX) for e in entries)


def require_active_allowlist(document: Dict[str, Any]) -> List[str]:
    """Return the six allowlisted schema identifiers, or raise.

    Raises SchemaAllowlistError if `document` fails structural (schema)
    validation, if its status is not ACTIVE, or if it is ACTIVE but still
    structurally indistinguishable from the unfilled template (see
    is_template_allowlist) -- any of these means real enforcement must
    not proceed. The structural check runs even when `document` did not
    come from load_allowlist_document: this is the public enforcement
    gate, and an in-memory document such as
    {"status": "ACTIVE", "allowlist": ["one"]} must be rejected here too,
    not only when loaded from disk -- an ACTIVE allowlist with fewer (or
    more) than exactly six entries violates the six-schema contract just
    as much as one that is still templated.
    """
    schema = load_allowlist_config_schema()
    try:
        jsonschema.Draft202012Validator(schema).validate(document)
    except jsonschema.ValidationError as exc:
        raise SchemaAllowlistError(f"allowlist config failed schema validation: {exc.message}") from exc

    if document.get("status") != ACTIVE_STATUS or is_template_allowlist(document):
        raise SchemaAllowlistError(
            "IO-VNBD schema allowlist is not active: it is still the "
            f"{TEMPLATE_STATUS} template shipped by WP-10.2. A human with "
            "SIH26168_IO_VNBD_Dataset_Feasibility_Audit_v1.1 must replace the six "
            "placeholder entries with the real allowlisted schema identifiers and "
            "set status to ACTIVE before this allowlist can be enforced against "
            "any dataset -- per C-15's 'quarantine unknown schema; stop experiment' "
            "failure mode, an unresolved allowlist is itself a stop condition."
        )
    return list(document["allowlist"])


def classify_schemas(candidate_schemas: List[str], allowlist: List[str]) -> Tuple[List[str], List[str]]:
    """Partition `candidate_schemas` into (allowed, unknown) against `allowlist`.

    Pure classification -- callers decide what to do with the `unknown`
    half (WP-10.1's DatasetManifest.exclusions with reason
    UNKNOWN_SCHEMA is the intended sink; see
    enforce_manifest_against_allowlist below for that wiring).
    """
    allowed_set = set(allowlist)
    allowed = [s for s in candidate_schemas if s in allowed_set]
    unknown = [s for s in candidate_schemas if s not in allowed_set]
    return allowed, unknown


def enforce_manifest_against_allowlist(manifest_document: Dict[str, Any], allowlist_document: Dict[str, Any]) -> None:
    """Raise SchemaAllowlistError if a DatasetManifest's `schemas` field
    contains anything outside the active allowlist.

    `manifest_document` is a DatasetManifest (I-20) document as produced
    by tools/dataset/manifest.py -- this function only reads its
    `schemas` field and does not itself validate the manifest's own shape
    (call tools.dataset.manifest.validate_manifest for that).
    """
    allowlist = require_active_allowlist(allowlist_document)

    candidate_schemas = manifest_document.get("schemas")
    if not isinstance(candidate_schemas, list) or not candidate_schemas or not all(
        isinstance(s, str) and s for s in candidate_schemas
    ):
        # A missing, empty, or malformed `schemas` field is not "nothing to
        # check" -- classify_schemas([], allowlist) would silently return
        # unknown=[] and let a manifest that never declared its schemas at
        # all pass enforcement. Per C-15's "quarantine unknown schema; stop
        # experiment" failure mode, an un-declared schema set is itself a
        # stop condition, exactly like an unresolved allowlist.
        raise SchemaAllowlistError(
            "DatasetManifest 'schemas' field is missing, empty, or not a list of "
            f"non-empty strings; cannot enforce the allowlist against it: {candidate_schemas!r}"
        )

    _, unknown = classify_schemas(candidate_schemas, allowlist)
    if unknown:
        raise SchemaAllowlistError(
            "DatasetManifest declares schema(s) outside the six-schema IO-VNBD "
            f"allowlist; quarantine and stop the experiment: {sorted(unknown)}"
        )
