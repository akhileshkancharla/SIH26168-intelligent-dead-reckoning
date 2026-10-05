"""Publish an evidence-bounded WP-11.5 evaluation recommendation.

The publisher consumes a WP-11.4 aggregate report, verifies its provenance
shape, and emits machine- and human-readable publication artifacts.  It cannot
promote a model: the upstream report does not carry the S4, packaging, runtime
parity, rights, leakage, or approved-threshold evidence required for that act.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
PUBLISHER_VERSION = "wp11.5-v2"
UPSTREAM_STATUS = "exploratory-not-promoted"
REQUIRED_KINDS = {"baseline", "model", "feature_ablation"}


class PublicationError(ValueError):
    """Raised when the upstream evidence is unsafe to publish."""


def _load_evidence_json(source_bytes: bytes) -> dict[str, Any]:
    """Parse strict JSON while rejecting duplicate keys and non-object roots."""

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PublicationError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise PublicationError(f"non-standard JSON constant is not allowed: {value}")

    try:
        document = json.loads(
            source_bytes.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublicationError("source_bytes must contain the evaluated JSON document") from error
    if not isinstance(document, dict):
        raise PublicationError("source_bytes must contain a top-level JSON object")
    return document


def _text(document: dict[str, Any], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PublicationError(f"{field} must be a non-empty string")
    return value


def _sha256(value: str, field: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise PublicationError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PublicationError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise PublicationError(f"{field} must be finite and non-negative")
    return number


def evaluate(report: dict[str, Any], source_bytes: bytes, upstream_reference: str) -> dict[str, Any]:
    """Validate an ablation report and build a fail-closed recommendation."""
    hashed_document = _load_evidence_json(source_bytes)
    canonical_hashed = json.dumps(hashed_document, sort_keys=True, separators=(",", ":"))
    canonical_report = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if canonical_hashed != canonical_report:
        raise PublicationError("source_bytes must exactly represent the evaluated report")
    schema_version = report.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SCHEMA_VERSION
    ):
        raise PublicationError(f"schema_version must be {SCHEMA_VERSION}")
    runner_version = _text(report, "runner_version")
    if _text(report, "scientific_status") != UPSTREAM_STATUS:
        raise PublicationError(f"scientific_status must remain {UPSTREAM_STATUS}")

    input_sha256 = _sha256(_text(report, "input_sha256"), "input_sha256")
    dataset_sha256 = _sha256(
        _text(report, "dataset_manifest_sha256"), "dataset_manifest_sha256"
    )
    split_id = _text(report, "split_id")
    mask_id = _text(report, "mask_id")
    sample_count = report.get("sample_count")
    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count <= 0:
        raise PublicationError("sample_count must be a positive integer")
    if not isinstance(upstream_reference, str) or not upstream_reference.strip():
        raise PublicationError("upstream_reference must be a non-empty string")

    limitations = report.get("limitations")
    if not isinstance(limitations, list) or not limitations or not all(
        isinstance(item, str) and item.strip() for item in limitations
    ):
        raise PublicationError("limitations must contain non-empty strings")

    variants = report.get("variants")
    if not isinstance(variants, list) or not variants:
        raise PublicationError("variants must be a non-empty list")
    seen_ids: set[str] = set()
    kinds: set[str] = set()
    summaries: list[dict[str, Any]] = []
    for index, variant in enumerate(variants):
        if not isinstance(variant, dict):
            raise PublicationError(f"variants[{index}] must be an object")
        variant_id = _text(variant, "variant_id")
        if variant_id in seen_ids:
            raise PublicationError(f"duplicate variant_id: {variant_id}")
        seen_ids.add(variant_id)
        kind = _text(variant, "kind")
        if kind not in REQUIRED_KINDS:
            raise PublicationError(f"unsupported variant kind: {kind}")
        kinds.add(kind)
        evidence_sha256 = _sha256(_text(variant, "evidence_sha256"), "evidence_sha256")
        metrics = variant.get("metrics")
        if not isinstance(metrics, dict):
            raise PublicationError(f"{variant_id}.metrics must be an object")
        summaries.append(
            {
                "variant_id": variant_id,
                "kind": kind,
                "evidence_sha256": evidence_sha256,
                "rmse_m": _finite(metrics.get("rmse_m"), f"{variant_id}.rmse_m"),
                "p95_m": _finite(metrics.get("p95_m"), f"{variant_id}.p95_m"),
                "endpoint_m": _finite(metrics.get("endpoint_m"), f"{variant_id}.endpoint_m"),
            }
        )
    missing = REQUIRED_KINDS - kinds
    if missing:
        raise PublicationError("missing required variant kinds: " + ", ".join(sorted(missing)))
    if sum(variant["kind"] == "model" for variant in summaries) != 1:
        raise PublicationError("exactly one full model variant is required")

    full_model_id = _text(report, "full_model_variant_id")
    best_baseline_id = _text(report, "best_baseline_variant_id")
    by_id = {variant["variant_id"]: variant for variant in summaries}
    if full_model_id not in by_id or by_id[full_model_id]["kind"] != "model":
        raise PublicationError("full_model_variant_id must identify a model variant")
    if best_baseline_id not in by_id or by_id[best_baseline_id]["kind"] != "baseline":
        raise PublicationError("best_baseline_variant_id must identify a baseline variant")

    is_synthetic = split_id.startswith("synthetic-") or mask_id.startswith("synthetic-")
    gate_findings = [
        "Upstream scientific status is exploratory-not-promoted.",
        "No S4 completion or approved promotion-threshold evidence is present.",
        "No model-package, runtime parity, latency, or device evidence is present.",
    ]
    if is_synthetic:
        gate_findings.insert(0, "Input identifiers mark the evidence as a synthetic fixture.")

    return {
        "schema_version": SCHEMA_VERSION,
        "publisher_version": PUBLISHER_VERSION,
        "title": "WP-11.5 exploratory evaluation and promotion recommendation",
        "upstream_reference": upstream_reference.strip(),
        "upstream_report_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "upstream_runner_version": runner_version,
        "upstream_input_sha256": input_sha256,
        "dataset_manifest_sha256": dataset_sha256,
        "split_id": split_id,
        "mask_id": mask_id,
        "sample_count": sample_count,
        "evidence_class": "synthetic-fixture" if is_synthetic else "exploratory",
        "scientific_status": "exploratory-only",
        "recommendation": "do-not-promote",
        "best_baseline_variant_id": best_baseline_id,
        "full_model_variant_id": full_model_id,
        "model_vs_best_baseline_rmse_delta_m": (
            by_id[full_model_id]["rmse_m"] - by_id[best_baseline_id]["rmse_m"]
        ),
        "variants": sorted(summaries, key=lambda variant: variant["variant_id"]),
        "gate_findings": gate_findings,
        "claims_permitted": [
            "The publication pipeline deterministically summarized the supplied aggregate fixture.",
            "The current evidence is insufficient for model promotion.",
        ],
        "claims_prohibited": [
            "real-world performance",
            "production readiness",
            "model promotion",
            "safety or field validity",
        ],
        "upstream_limitations": list(limitations),
    }


def render_markdown(publication: dict[str, Any]) -> str:
    """Render a compact, reviewable publication from validated data."""
    lines = [
        "# WP-11.5 exploratory evaluation and promotion recommendation",
        "",
        "## Recommendation",
        "",
        "**DO NOT PROMOTE.** The supplied evidence is exploratory and does not satisfy the",
        "Architecture Revision 3 model-promotion gates.",
        "",
        "## Evidence identity",
        "",
        f"- Upstream reference: `{publication['upstream_reference']}`",
        f"- Upstream report SHA-256: `{publication['upstream_report_sha256']}`",
        f"- Upstream input SHA-256: `{publication['upstream_input_sha256']}`",
        f"- Dataset manifest SHA-256: `{publication['dataset_manifest_sha256']}`",
        f"- Split / mask: `{publication['split_id']}` / `{publication['mask_id']}`",
        f"- Evidence class: `{publication['evidence_class']}`",
        f"- Publisher version: `{publication['publisher_version']}`",
        "",
        "## Exploratory aggregate metrics",
        "",
        "| Variant | Kind | RMSE (m) | p95 (m) | Endpoint (m) |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for variant in publication["variants"]:
        lines.append(
            f"| `{variant['variant_id']}` | {variant['kind']} | "
            f"{variant['rmse_m']:.6f} | {variant['p95_m']:.6f} | "
            f"{variant['endpoint_m']:.6f} |"
        )
    lines.extend(["", "These values describe only the supplied aggregate evidence and are not a field claim."])
    lines.extend(["", "## Gate findings", ""])
    lines.extend(f"- {finding}" for finding in publication["gate_findings"])
    lines.extend(["", "## Claim boundary", "", "Permitted:"])
    lines.extend(f"- {claim}" for claim in publication["claims_permitted"])
    lines.extend(["", "Prohibited:"])
    lines.extend(f"- {claim}" for claim in publication["claims_prohibited"])
    lines.extend(["", "## Upstream limitations", ""])
    lines.extend(f"- {limitation}" for limitation in publication["upstream_limitations"])
    return "\n".join(lines) + "\n"


def encode_publication(publication: dict[str, Any]) -> bytes:
    """Return the canonical UTF-8/LF JSON representation."""
    return (
        json.dumps(publication, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--upstream-reference", required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()

    source_bytes = args.input.read_bytes()
    report = json.loads(source_bytes.decode("utf-8"))
    publication = evaluate(report, source_bytes, args.upstream_reference)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_bytes(encode_publication(publication))
    args.output_markdown.write_bytes(render_markdown(publication).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
