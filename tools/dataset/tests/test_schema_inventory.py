"""Synthetic inventory evidence; no dataset download."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("schema_inventory", Path(__file__).resolve().parents[1] / "schema_inventory.py")
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


class InventoryTests(unittest.TestCase):
    def describe(self, content, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private.csv"
            path.write_text(content, encoding="utf-8")
            args = dict(delimiter=",", units=["s", "m/s^2"], timestamp_semantics="synthetic elapsed seconds", source_revision="synthetic-v1")
            args.update(overrides)
            return inventory.describe_header(path, **args)

    def test_no_rows_or_paths_and_no_activation(self):
        result = self.describe('time,accel\nSECRET_ROW,99\n')
        encoded = json.dumps(result)
        self.assertNotIn("SECRET_ROW", encoded)
        self.assertNotIn("private.csv", encoded)
        self.assertEqual(result["status"], "CANDIDATE_REQUIRES_S0_RECONCILIATION")
        self.assertEqual(result, self.describe('time,accel\nDIFFERENT,123\n'))

    def test_fingerprint_distinguishes_order_units_and_clock(self):
        baseline = self.describe("time,accel\n")["schema_fingerprint"]
        for result in (self.describe("accel,time\n"), self.describe("time,accel\n", units=["ms", "m/s^2"]), self.describe("time,accel\n", timestamp_semantics="UTC")):
            self.assertNotEqual(baseline, result["schema_fingerprint"])

    def test_invalid_headers_and_missing_evidence(self):
        for content in ("", "a,a\n", "a,\n"):
            with self.assertRaises(ValueError):
                self.describe(content)
        for overrides in ({"units": ["s"]}, {"timestamp_semantics": ""}, {"source_revision": ""}):
            with self.assertRaises(ValueError):
                self.describe("time,accel\n", **overrides)
