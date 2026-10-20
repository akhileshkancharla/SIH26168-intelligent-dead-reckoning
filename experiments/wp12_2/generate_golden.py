"""Generate immutable ONNX golden tensors for WP-12.2.

The generator accepts only a hash-verified WP-12.1 bundle and immutable .npy
input tensors. It runs ONNX Runtime on CPU and atomically publishes copied
inputs, produced outputs, and a provenance manifest. The repository currently
contains no promotion-approved model bundle, so no golden tensors are committed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

SCHEMA_VERSION = 1
GENERATOR_VERSION = "wp12.2-v1"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
APPROVED_REAL_EVIDENCE_CLASSES = frozenset(
    {"held-out-real-world", "real-world-field-validation"}
)
ONNX_DTYPES = {
    "tensor(bool)": "bool",
    "tensor(float)": "float32",
    "tensor(double)": "float64",
    "tensor(int32)": "int32",
    "tensor(int64)": "int64",
}


class GoldenBlocked(RuntimeError):
    """Raised when a golden-vector request is incomplete or ineligible."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise GoldenBlocked(f"duplicate JSON key: {key}")
        document[key] = value
    return document


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(
                GoldenBlocked(f"non-standard JSON constant: {token}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GoldenBlocked(f"cannot read canonical JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise GoldenBlocked(f"{path} must contain one JSON object")
    return value


def _text(document: dict[str, Any], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value.strip():
        raise GoldenBlocked(f"{field} must be a non-empty string")
    return value.strip()


def _integer(document: dict[str, Any], field: str) -> int:
    value = document.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise GoldenBlocked(f"{field} must be an integer")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise GoldenBlocked(f"cannot hash {path}: {error}") from error
    return digest.hexdigest()


def _expected_sha(document: dict[str, Any], field: str) -> str:
    value = _text(document, field).lower()
    if not SHA256_PATTERN.fullmatch(value):
        raise GoldenBlocked(f"{field} must be a lowercase SHA-256")
    return value


def _canonical_bytes(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def _finite_metrics(value: Any) -> dict[str, int | float]:
    if not isinstance(value, dict):
        raise GoldenBlocked("model manifest metrics must be an object")
    validated: dict[str, int | float] = {}
    for name, metric in value.items():
        if (
            not isinstance(name, str)
            or not name.strip()
            or isinstance(metric, bool)
            or not isinstance(metric, (int, float))
            or not math.isfinite(metric)
        ):
            raise GoldenBlocked(
                "model manifest metrics must map non-empty names to finite numbers"
            )
        validated[name.strip()] = metric
    if len(validated) != len(value):
        raise GoldenBlocked("model manifest metric names collide after trimming")
    return validated


def validate_model_manifest(document: dict[str, Any]) -> dict[str, Any]:
    if _integer(document, "schema_version") != SCHEMA_VERSION:
        raise GoldenBlocked("model manifest schema_version must be 1")
    if _text(document, "format").lower() != "onnx":
        raise GoldenBlocked("model manifest format must be onnx")
    opset = _integer(document, "opset")
    if not 13 <= opset <= 21:
        raise GoldenBlocked("model manifest opset must be between 13 and 21")
    outputs = document.get("outputs")
    if (
        not isinstance(outputs, list)
        or not outputs
        or any(not isinstance(value, str) or not value.strip() for value in outputs)
    ):
        raise GoldenBlocked("model manifest outputs must be non-empty strings")
    normalized = [value.strip() for value in outputs]
    if len(set(normalized)) != len(normalized):
        raise GoldenBlocked("model manifest outputs must be unique after trimming")
    for field in (
        "runtime_min",
        "input_contract",
        "window",
        "normalization",
        "bounds",
        "training_run",
        "dataset_manifest",
        "redistribution_status",
        "exporter_version",
    ):
        _text(document, field)
    _finite_metrics(document.get("metrics"))
    return {
        "model_id": _text(document, "model_id"),
        "model_sha256": _expected_sha(document, "sha256"),
        "outputs": normalized,
        "redistribution_status": _text(document, "redistribution_status"),
        "candidate_descriptor_sha256": _expected_sha(
            document, "candidate_descriptor_sha256"
        ),
        "promotion_evidence_sha256": _expected_sha(
            document, "promotion_evidence_sha256"
        ),
    }


def validate_promotion(document: dict[str, Any], model_id: str) -> None:
    if _integer(document, "schema_version") != SCHEMA_VERSION:
        raise GoldenBlocked("promotion schema_version must be 1")
    if document.get("recommendation") != "promote":
        raise GoldenBlocked("promotion recommendation is not 'promote'")
    if document.get("scientific_status") not in {
        "promotion-approved",
        "candidate-approved",
    }:
        raise GoldenBlocked("promotion evidence is not candidate-approved")
    if _text(document, "evidence_class") not in APPROVED_REAL_EVIDENCE_CLASSES:
        raise GoldenBlocked("promotion evidence is not approved real-world evidence")
    if _text(document, "candidate_id") != model_id:
        raise GoldenBlocked("promotion candidate_id does not match model manifest")

def validate_request(document: dict[str, Any]) -> dict[str, Any]:
    if _integer(document, "schema_version") != SCHEMA_VERSION:
        raise GoldenBlocked("request schema_version must be 1")
    inputs = document.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise GoldenBlocked("inputs must be a non-empty list")
    validated_inputs: list[dict[str, str]] = []
    names: set[str] = set()
    files: set[str] = set()
    for index, item in enumerate(inputs):
        if not isinstance(item, dict):
            raise GoldenBlocked(f"inputs[{index}] must be an object")
        name = _text(item, "name")
        file_name = _text(item, "file")
        if name in names:
            raise GoldenBlocked(f"duplicate input name: {name}")
        if file_name in files:
            raise GoldenBlocked(f"duplicate input file: {file_name}")
        if Path(file_name).suffix.lower() != ".npy":
            raise GoldenBlocked(f"input {name} must use an .npy file")
        names.add(name)
        files.add(file_name)
        validated_inputs.append(
            {
                "name": name,
                "file": file_name,
                "sha256": _expected_sha(item, "sha256"),
            }
        )
    return {
        "model_id": _text(document, "model_id"),
        "source_evidence": _text(document, "source_evidence"),
        "inputs": validated_inputs,
    }


def _fixed_shape(node: Any) -> tuple[int, ...]:
    shape = getattr(node, "shape", None)
    if (
        not isinstance(shape, (list, tuple))
        or not shape
        or any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            for value in shape
        )
    ):
        raise GoldenBlocked(f"ONNX tensor {node.name} must have a fixed positive shape")
    return tuple(shape)


def _tensor_record(path: Path, name: str, array: Any) -> dict[str, Any]:
    return {
        "name": name,
        "file": path.name,
        "sha256": _sha256(path),
        "dtype": str(array.dtype),
        "shape": list(array.shape),
    }


def generate_golden(
    bundle_directory: Path,
    promotion_path: Path,
    request_path: Path,
    output_directory: Path,
) -> Path:
    model_path = bundle_directory / "model.onnx"
    model_manifest_path = bundle_directory / "model_manifest.json"
    if not model_path.is_file() or not model_manifest_path.is_file():
        raise GoldenBlocked(
            "verified WP-12.1 bundle must contain model.onnx and model_manifest.json"
        )

    model_manifest = validate_model_manifest(load_json(model_manifest_path))
    if _sha256(model_path) != model_manifest["model_sha256"]:
        raise GoldenBlocked("model.onnx hash does not match model_manifest.json")
    if not promotion_path.is_file():
        raise GoldenBlocked("matching promotion evidence is required")
    if _sha256(promotion_path) != model_manifest["promotion_evidence_sha256"]:
        raise GoldenBlocked("promotion evidence hash does not match model manifest")
    validate_promotion(load_json(promotion_path), model_manifest["model_id"])

    request = validate_request(load_json(request_path))
    if request["model_id"] != model_manifest["model_id"]:
        raise GoldenBlocked("request model_id does not match model manifest")
    if output_directory.exists():
        raise GoldenBlocked(f"refusing existing output directory: {output_directory}")

    try:
        import numpy as np
        import onnxruntime as ort
    except ImportError as error:
        raise GoldenBlocked(
            "generation requires pinned numpy and onnxruntime in the approved private workspace"
        ) from error

    try:
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        session = ort.InferenceSession(
            str(model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        runtime_inputs = session.get_inputs()
        runtime_outputs = session.get_outputs()
    except Exception as error:
        raise GoldenBlocked(f"cannot initialize ONNX Runtime session: {error}") from error

    requested_by_name = {item["name"]: item for item in request["inputs"]}
    runtime_input_names = [node.name for node in runtime_inputs]
    if set(requested_by_name) != set(runtime_input_names):
        raise GoldenBlocked("request input names do not exactly match ONNX inputs")
    runtime_output_names = [node.name for node in runtime_outputs]
    if runtime_output_names != model_manifest["outputs"]:
        raise GoldenBlocked("ONNX outputs do not match model manifest order")

    arrays: dict[str, Any] = {}
    for node in runtime_inputs:
        expected_dtype = ONNX_DTYPES.get(node.type)
        if expected_dtype is None:
            raise GoldenBlocked(f"unsupported ONNX dtype for {node.name}: {node.type}")
        item = requested_by_name[node.name]
        input_path = (request_path.parent / item["file"]).resolve()
        if not input_path.is_file():
            raise GoldenBlocked(f"input tensor does not exist: {input_path}")
        if _sha256(input_path) != item["sha256"]:
            raise GoldenBlocked(f"input tensor hash mismatch: {node.name}")
        try:
            array = np.load(input_path, allow_pickle=False)
        except Exception as error:
            raise GoldenBlocked(f"cannot load input tensor {node.name}: {error}") from error
        if str(array.dtype) != expected_dtype:
            raise GoldenBlocked(
                f"input {node.name} dtype {array.dtype} != {expected_dtype}"
            )
        if tuple(array.shape) != _fixed_shape(node):
            raise GoldenBlocked(f"input {node.name} shape does not match ONNX")
        if np.issubdtype(array.dtype, np.floating) and not bool(np.isfinite(array).all()):
            raise GoldenBlocked(f"input {node.name} contains non-finite values")
        arrays[node.name] = array

    try:
        results = session.run(runtime_output_names, arrays)
    except Exception as error:
        raise GoldenBlocked(f"ONNX Runtime inference failed: {error}") from error
    if len(results) != len(runtime_outputs):
        raise GoldenBlocked("ONNX Runtime returned an unexpected output count")
    for node, array in zip(runtime_outputs, results):
        if not isinstance(array, np.ndarray):
            raise GoldenBlocked(f"output {node.name} is not a NumPy tensor")
        expected_dtype = ONNX_DTYPES.get(node.type)
        if expected_dtype is None or str(array.dtype) != expected_dtype:
            raise GoldenBlocked(f"output {node.name} dtype does not match ONNX")
        if tuple(array.shape) != _fixed_shape(node):
            raise GoldenBlocked(f"output {node.name} shape does not match ONNX")
        if np.issubdtype(array.dtype, np.floating) and not bool(np.isfinite(array).all()):
            raise GoldenBlocked(f"output {node.name} contains non-finite values")

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.staging-",
            dir=output_directory.parent,
        )
    )
    try:
        input_records: list[dict[str, Any]] = []
        for index, node in enumerate(runtime_inputs):
            path = staging / f"input_{index:03d}.npy"
            np.save(path, arrays[node.name], allow_pickle=False)
            input_records.append(_tensor_record(path, node.name, arrays[node.name]))

        output_records: list[dict[str, Any]] = []
        for index, (node, array) in enumerate(zip(runtime_outputs, results)):
            path = staging / f"output_{index:03d}.npy"
            np.save(path, array, allow_pickle=False)
            output_records.append(_tensor_record(path, node.name, array))

        golden_manifest = {
            "schema_version": SCHEMA_VERSION,
            "generator_version": GENERATOR_VERSION,
            "model_id": model_manifest["model_id"],
            "model_sha256": model_manifest["model_sha256"],
            "model_manifest_sha256": _sha256(model_manifest_path),
            "candidate_descriptor_sha256": model_manifest[
                "candidate_descriptor_sha256"
            ],
            "promotion_evidence_sha256": model_manifest[
                "promotion_evidence_sha256"
            ],
            "input_request_sha256": _sha256(request_path),
            "source_evidence": request["source_evidence"],
            "runtime": "onnxruntime",
            "runtime_version": _text({"version": ort.__version__}, "version"),
            "providers": ["CPUExecutionProvider"],
            "redistribution_status": model_manifest["redistribution_status"],
            "inputs": input_records,
            "outputs": output_records,
        }
        manifest_path = staging / "golden_manifest.json"
        manifest_path.write_bytes(_canonical_bytes(golden_manifest))
        staging.replace(output_directory)
    except Exception as error:
        shutil.rmtree(staging, ignore_errors=True)
        if isinstance(error, GoldenBlocked):
            raise
        raise GoldenBlocked(
            f"golden tensor serialization or atomic publication failed: {error}"
        ) from error

    return output_directory / "golden_manifest.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--promotion", required=True, type=Path)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = generate_golden(
            args.bundle.resolve(),
            args.promotion.resolve(),
            args.request.resolve(),
            args.output_dir.resolve(),
        )
    except GoldenBlocked as error:
        raise SystemExit(f"BLOCKED: {error}") from error
    print(f"golden manifest {manifest}")


if __name__ == "__main__":
    main()
