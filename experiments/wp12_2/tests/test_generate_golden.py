from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

import numpy as np


MODULE_PATH = Path(__file__).resolve().parents[1] / "generate_golden.py"
SPEC = importlib.util.spec_from_file_location("wp12_2_generate_golden", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Node:
    def __init__(self, name: str, shape: list[int], tensor_type: str) -> None:
        self.name = name
        self.shape = shape
        self.type = tensor_type


def fake_onnxruntime(*, fail_run: bool = False) -> types.ModuleType:
    module = types.ModuleType("onnxruntime")
    module.__version__ = "1.20.0-test"

    class GraphOptimizationLevel:
        ORT_DISABLE_ALL = "disabled"

    class SessionOptions:
        def __init__(self) -> None:
            self.graph_optimization_level: object | None = None

    class InferenceSession:
        def __init__(
            self,
            model: str,
            *,
            sess_options: object,
            providers: list[str],
        ) -> None:
            self.model = model
            self.options = sess_options
            self.providers = providers

        def get_inputs(self) -> list[Node]:
            return [Node("imu_window", [1, 2], "tensor(float)")]

        def get_outputs(self) -> list[Node]:
            return [Node("displacement", [1, 2], "tensor(float)")]

        def run(
            self,
            output_names: list[str],
            inputs: dict[str, np.ndarray],
        ) -> list[np.ndarray]:
            if fail_run:
                raise RuntimeError("runtime failed")
            if output_names != ["displacement"]:
                raise AssertionError(output_names)
            return [inputs["imu_window"] * np.float32(2.0)]

    module.GraphOptimizationLevel = GraphOptimizationLevel
    module.SessionOptions = SessionOptions
    module.InferenceSession = InferenceSession
    return module


def write_promotion(root: Path, **overrides: object) -> Path:
    document: dict[str, object] = {
        "schema_version": 1,
        "recommendation": "promote",
        "scientific_status": "promotion-approved",
        "evidence_class": "held-out-real-world",
        "candidate_id": "approved-model",
    }
    document.update(overrides)
    path = root / "promotion.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def write_bundle(root: Path) -> Path:
    promotion = write_promotion(root)
    bundle = root / "bundle"
    bundle.mkdir()
    model = bundle / "model.onnx"
    model.write_bytes(b"approved-onnx-model")
    manifest = {
        "schema_version": 1,
        "model_id": "approved-model",
        "sha256": sha256(model),
        "format": "onnx",
        "opset": 17,
        "runtime_min": "onnxruntime-private-pin",
        "input_contract": "two finite float32 values",
        "window": "one fixed window",
        "normalization": "immutable-normalization-id",
        "outputs": ["displacement"],
        "bounds": "documented displacement bounds",
        "training_run": "immutable-training-run",
        "dataset_manifest": "immutable-dataset-manifest",
        "metrics": {"held_out_rmse": 1.0},
        "redistribution_status": "private; approval required",
        "exporter_version": "wp12.1-v1",
        "candidate_descriptor_sha256": "1" * 64,
        "promotion_evidence_sha256": sha256(promotion),
    }
    (bundle / "model_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return bundle


def write_request(root: Path, **overrides: object) -> Path:
    tensor = root / "input.npy"
    np.save(tensor, np.array([[1.0, 2.0]], dtype=np.float32), allow_pickle=False)
    document: dict[str, object] = {
        "schema_version": 1,
        "model_id": "approved-model",
        "source_evidence": "immutable private fixture id",
        "inputs": [
            {
                "name": "imu_window",
                "file": "input.npy",
                "sha256": sha256(tensor),
            }
        ],
    }
    document.update(overrides)
    request = root / "request.json"
    request.write_text(json.dumps(document), encoding="utf-8")
    return request


class ValidationTests(unittest.TestCase):
    def test_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text(
                '{"schema_version": 1, "schema_version": 1}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(generator.GoldenBlocked, "duplicate JSON key"):
                generator.load_json(path)

    def test_rejects_malformed_manifest_hashes(self) -> None:
        manifest = {
            "schema_version": 1,
            "model_id": "model",
            "sha256": "not-a-hash",
            "format": "onnx",
            "opset": 17,
            "runtime_min": "runtime",
            "input_contract": "contract",
            "window": "window",
            "normalization": "normalization",
            "outputs": ["output"],
            "bounds": "bounds",
            "training_run": "run",
            "dataset_manifest": "dataset",
            "metrics": {},
            "redistribution_status": "private",
            "exporter_version": "wp12.1-v1",
            "candidate_descriptor_sha256": "1" * 64,
            "promotion_evidence_sha256": "2" * 64,
        }
        with self.assertRaisesRegex(generator.GoldenBlocked, "lowercase SHA-256"):
            generator.validate_model_manifest(manifest)

    def test_rejects_empty_manifest_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = write_bundle(root)
            manifest_path = bundle / "model_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["metrics"] = {}
            with self.assertRaisesRegex(
                generator.GoldenBlocked,
                "non-empty object",
            ):
                generator.validate_model_manifest(manifest)

    def test_rejects_duplicate_request_inputs(self) -> None:
        item = {"name": "input", "file": "input.npy", "sha256": "3" * 64}
        request = {
            "schema_version": 1,
            "model_id": "model",
            "source_evidence": "fixture",
            "inputs": [item, dict(item)],
        }
        with self.assertRaisesRegex(generator.GoldenBlocked, "duplicate input"):
            generator.validate_request(request)


class GenerationTests(unittest.TestCase):
    def test_missing_bundle_fails_before_runtime_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = write_request(root)
            output = root / "golden"
            with self.assertRaisesRegex(generator.GoldenBlocked, "verified WP-12.1"):
                generator.generate_golden(root / "missing", root / "promotion.json", request, output)
            self.assertFalse(output.exists())

    def test_model_hash_mismatch_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = write_bundle(root)
            (bundle / "model.onnx").write_bytes(b"tampered")
            request = write_request(root)
            output = root / "golden"
            with self.assertRaisesRegex(generator.GoldenBlocked, "hash does not match"):
                generator.generate_golden(bundle, root / "promotion.json", request, output)
            self.assertFalse(output.exists())

    def test_input_hash_mismatch_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = write_bundle(root)
            request = write_request(root)
            document = json.loads(request.read_text(encoding="utf-8"))
            document["inputs"][0]["sha256"] = "4" * 64
            request.write_text(json.dumps(document), encoding="utf-8")
            output = root / "golden"
            with mock.patch.dict(
                sys.modules,
                {"onnxruntime": fake_onnxruntime()},
            ):
                with self.assertRaisesRegex(generator.GoldenBlocked, "hash mismatch"):
                    generator.generate_golden(bundle, root / "promotion.json", request, output)
            self.assertFalse(output.exists())

    def test_do_not_promote_evidence_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = write_bundle(root)
            write_promotion(
                root,
                recommendation="do-not-promote",
                scientific_status="exploratory-only",
                evidence_class="synthetic-fixture",
            )
            manifest_path = bundle / "model_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["promotion_evidence_sha256"] = sha256(root / "promotion.json")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            request = write_request(root)
            output = root / "golden"
            with self.assertRaisesRegex(generator.GoldenBlocked, "not 'promote'"):
                generator.generate_golden(
                    bundle,
                    root / "promotion.json",
                    request,
                    output,
                )
            self.assertFalse(output.exists())

    def test_refuses_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = write_bundle(root)
            request = write_request(root)
            output = root / "golden"
            output.mkdir()
            with self.assertRaisesRegex(
                generator.GoldenBlocked,
                "existing output directory",
            ):
                generator.generate_golden(bundle, root / "promotion.json", request, output)

    def test_runtime_failure_leaves_no_bundle_or_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = write_bundle(root)
            request = write_request(root)
            output = root / "golden"
            with mock.patch.dict(
                sys.modules,
                {"onnxruntime": fake_onnxruntime(fail_run=True)},
            ):
                with self.assertRaisesRegex(
                    generator.GoldenBlocked,
                    "inference failed",
                ):
                    generator.generate_golden(bundle, root / "promotion.json", request, output)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".golden.staging-*")), [])

    def test_success_publishes_hashed_tensors_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = write_bundle(root)
            request = write_request(root)
            output = root / "golden"
            with mock.patch.dict(
                sys.modules,
                {"onnxruntime": fake_onnxruntime()},
            ):
                manifest_path = generator.generate_golden(bundle, root / "promotion.json", request, output)

            self.assertEqual(manifest_path, output / "golden_manifest.json")
            self.assertEqual(
                set(path.name for path in output.iterdir()),
                {"input_000.npy", "output_000.npy", "golden_manifest.json"},
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["model_id"], "approved-model")
            self.assertEqual(manifest["runtime"], "onnxruntime")
            self.assertEqual(manifest["providers"], ["CPUExecutionProvider"])
            self.assertEqual(manifest["inputs"][0]["name"], "imu_window")
            self.assertEqual(manifest["outputs"][0]["name"], "displacement")
            self.assertEqual(
                manifest["inputs"][0]["sha256"],
                sha256(output / "input_000.npy"),
            )
            self.assertEqual(
                manifest["outputs"][0]["sha256"],
                sha256(output / "output_000.npy"),
            )
            np.testing.assert_array_equal(
                np.load(output / "output_000.npy", allow_pickle=False),
                np.array([[2.0, 4.0]], dtype=np.float32),
            )
            self.assertEqual(list(root.glob(".golden.staging-*")), [])


if __name__ == "__main__":
    unittest.main()
