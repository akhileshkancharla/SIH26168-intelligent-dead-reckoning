import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ablation import AblationError, encode_report, evaluate, main


class AblationTests(unittest.TestCase):
    def evidence(self):
        common_ids = ["mask-0001", "mask-0002", "mask-0003"]
        return {
            "schema_version": 1,
            "dataset_manifest_sha256": "a" * 64,
            "split_id": "journey-safe-test-v1",
            "mask_id": "frozen-blackout-v1",
            "variants": [
                {
                    "variant_id": "constant_velocity",
                    "kind": "baseline",
                    "evidence_sha256": "b" * 64,
                    "sample_ids": common_ids,
                    "errors_m": [3.0, 4.0, 5.0],
                },
                {
                    "variant_id": "ridge_full",
                    "kind": "model",
                    "evidence_sha256": "c" * 64,
                    "sample_ids": common_ids,
                    "errors_m": [2.0, 3.0, 4.0],
                },
                {
                    "variant_id": "ridge_without_speed",
                    "kind": "feature_ablation",
                    "evidence_sha256": "d" * 64,
                    "omitted_features": ["speed_mps"],
                    "sample_ids": common_ids,
                    "errors_m": [2.5, 3.5, 4.5],
                },
            ],
        }

    def test_matched_comparison_is_deterministic(self):
        first = evaluate(self.evidence())
        second = evaluate(self.evidence())
        self.assertEqual(first, second)
        self.assertEqual(first["scientific_status"], "exploratory-not-promoted")
        self.assertEqual(first["runner_version"], "wp11.4-v1")
        self.assertEqual(first["best_baseline_variant_id"], "constant_velocity")
        self.assertEqual(first["full_model_variant_id"], "ridge_full")

    def test_rejects_mismatched_sample_order(self):
        evidence = self.evidence()
        evidence["variants"][2]["sample_ids"] = ["mask-0002", "mask-0001", "mask-0003"]
        with self.assertRaisesRegex(AblationError, "exact ordered matched sample set"):
            evaluate(evidence)

    def test_rejects_non_finite_error(self):
        evidence = self.evidence()
        evidence["variants"][1]["errors_m"][0] = float("nan")
        with self.assertRaisesRegex(AblationError, "finite and non-negative"):
            evaluate(evidence)

    def test_requires_upstream_evidence_digest(self):
        evidence = self.evidence()
        evidence["variants"][0].pop("evidence_sha256")
        with self.assertRaisesRegex(AblationError, "evidence_sha256"):
            evaluate(evidence)

    def test_requires_baseline_model_and_feature_ablation(self):
        evidence = self.evidence()
        evidence["variants"] = evidence["variants"][:2]
        with self.assertRaisesRegex(AblationError, "feature_ablation"):
            evaluate(evidence)

    def test_requires_exactly_one_full_model(self):
        evidence = self.evidence()
        duplicate = copy.deepcopy(evidence["variants"][1])
        duplicate["variant_id"] = "another_full_model"
        evidence["variants"].append(duplicate)
        with self.assertRaisesRegex(AblationError, "exactly one full model"):
            evaluate(evidence)

    def test_rejects_boolean_schema_version(self):
        evidence = self.evidence()
        evidence["schema_version"] = True
        with self.assertRaisesRegex(AblationError, "schema_version must be 1"):
            evaluate(evidence)

    def test_report_encoding_is_utf8_with_fixed_lf(self):
        encoded = encode_report(evaluate(self.evidence()))
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertNotIn(b"\r\n", encoded)
        self.assertEqual(encoded.decode("utf-8").count("\n"), encoded.count(b"\n"))

    def test_cli_writes_stable_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            input_path = Path(temporary) / "input.json"
            output_path = Path(temporary) / "report.json"
            input_path.write_text(json.dumps(self.evidence()), encoding="utf-8")
            previous = sys.argv
            try:
                sys.argv = ["ablation.py", str(input_path), "--output", str(output_path)]
                self.assertEqual(main(), 0)
            finally:
                sys.argv = previous
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["sample_count"], 3)
            output_bytes = output_path.read_bytes()
            self.assertEqual(output_bytes, encode_report(report))
            self.assertEqual(
                hashlib.sha256(output_bytes).hexdigest(),
                hashlib.sha256(encode_report(evaluate(self.evidence()))).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
