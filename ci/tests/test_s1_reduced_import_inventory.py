import hashlib
import json
import subprocess
import unittest
from pathlib import Path


class S1ReducedImportInventoryTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[2]
    IMPORT_ROOT = ROOT / "android" / "acquisition" / "imported" / "S1_Android_Acquisition_Spike"
    INVENTORY = ROOT / "docs" / "architecture" / "imports" / "WP-02.1_S1_ANDROID_ACQUISITION_IMPORT.json"
    MANIFEST = IMPORT_ROOT / "S1_ARTIFACT_MANIFEST_v1.json"

    def test_reduced_import_inventory_matches_manifest_and_files(self):
        inventory = json.loads(self.INVENTORY.read_text(encoding="utf-8"))
        manifest = json.loads(self.MANIFEST.read_text(encoding="utf-8"))

        self.assertEqual(inventory["schema_version"], "wp-02.1.reduced_import_inventory.v1")
        self.assertEqual(inventory["source_manifest"], "android/acquisition/imported/S1_Android_Acquisition_Spike/S1_ARTIFACT_MANIFEST_v1.json")
        self.assertEqual(inventory["source_manifest_sha256"], hashlib.sha256(self.MANIFEST.read_bytes()).hexdigest())

        imported = inventory["imported_files"]
        omitted = inventory["omitted_manifest_entries"]
        self.assertEqual(len(imported), 37)
        self.assertEqual(len(omitted), 14)

        manifest_imported = {x["path"] for x in manifest["files"] if not x["path"].startswith("results/")}
        manifest_omitted = {x["path"] for x in manifest["files"] if x["path"].startswith("results/")}
        self.assertEqual({x["path"] for x in imported}, manifest_imported)
        self.assertEqual({x["path"] for x in omitted}, manifest_omitted)

        prefix = self.IMPORT_ROOT.relative_to(self.ROOT).as_posix() + "/"
        tracked = subprocess.check_output(
            ["git", "ls-files", "-z", "--", prefix], cwd=self.ROOT
        ).decode("utf-8").split("\0")
        # The preserved source manifest is independently hashed above; its own
        # inventory deliberately excludes itself.
        expected = {entry["path"] for entry in imported} | {"S1_ARTIFACT_MANIFEST_v1.json"}
        self.assert_exact_tracked_payload(
            {path.removeprefix(prefix) for path in tracked if path}, expected
        )

        for entry in imported:
            path = self.IMPORT_ROOT / Path(entry["path"])
            self.assertTrue(path.is_file(), entry["path"])
            # Validate the tracked blob, independent of checkout line endings.
            blob = subprocess.check_output(["git", "show", ":" + prefix + entry["path"]], cwd=self.ROOT)
            self.assertEqual(len(blob), entry["size"], entry["path"])
            self.assertEqual(hashlib.sha256(blob).hexdigest(), entry["sha256"], entry["path"])

        for entry in omitted:
            self.assertEqual(entry["reason"], "results evidence intentionally excluded from reduced WP-02.1 import")

    def assert_exact_tracked_payload(self, tracked, expected):
        self.assertSetEqual(tracked, expected, "Tracked S1 payload differs from the reduced import inventory")

    def test_extra_tracked_file_is_rejected(self):
        with self.assertRaises(AssertionError):
            self.assert_exact_tracked_payload({"declared.kt", "undeclared.kt"}, {"declared.kt"})

    def test_missing_tracked_file_is_rejected(self):
        with self.assertRaises(AssertionError):
            self.assert_exact_tracked_payload(set(), {"declared.kt"})


if __name__ == "__main__":
    unittest.main()
