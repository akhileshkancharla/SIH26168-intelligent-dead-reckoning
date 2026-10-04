import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

import jsonschema


MAPS_DIR = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MAPS_DIR))

import verify_s6b1_artifact as verifier  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SyntheticS6B1:
    def __init__(
        self,
        directory: Path,
        *,
        corrupt_member: bool = False,
        extra_member: str | None = None,
        final_selected: bool = False,
    ) -> None:
        self.directory = directory / "delivery"
        self.directory.mkdir()
        self.root = "S6B1_MGIT_Road_Graph_Foundation"
        pbf = b"synthetic-pbf-bytes"
        region = b'{"type":"FeatureCollection","features":[]}'
        graph = b"synthetic-sqlite-bytes"
        graph_schema = b"CREATE TABLE synthetic(id INTEGER PRIMARY KEY);\n"
        requirements = b"osmium==4.3.1\n"
        pbf_hash = sha256(pbf)
        region_hash = sha256(region)
        graph_hash = sha256(graph)
        logical_hash = sha256(b"synthetic-logical-graph")

        source_manifest = {
            "schema_version": 1,
            "pbf_sha256": pbf_hash,
            "pbf_public_redistribution_authorized": False,
            "osm_attribution": "© OpenStreetMap contributors; ODbL 1.0.",
            "files": [
                {"path": "source/mgit_frozen.osm.pbf", "sha256": pbf_hash},
                {"path": "source/region.geojson", "sha256": region_hash},
            ],
        }
        graph_validation = {
            "status": "passed",
            "graph": {
                "node_count": 3,
                "edge_count": 4,
                "way_count": 2,
                "sqlite_sha256": graph_hash,
            },
            "logical_content_sha256": logical_hash,
            "route_candidates": {
                "route_count": 1,
                "routes": [
                    {
                        "route_id": "SYNTHETIC-ROUTE",
                        "status": "FIELD_VALIDATION_PENDING",
                        "final_selected": final_selected,
                    }
                ],
            },
        }
        test_results = {
            "counts": {"passed": 2, "failed": 0, "skipped": 0},
            "tests": [
                {"name": "synthetic_hashes", "status": "passed"},
                {"name": "synthetic_graph", "status": "passed"},
            ],
        }
        deterministic = {
            "byte_identical": True,
            "logical_identical": True,
            "first_sqlite_sha256": graph_hash,
            "second_sqlite_sha256": graph_hash,
            "first_logical_sha256": logical_hash,
            "second_logical_sha256": logical_hash,
        }
        source_validation = {
            "pbf_header": {"bounds": [-0.01, -0.01, 0.01, 0.01]},
            "region_bounds": [-0.01, -0.01, 0.01, 0.01],
            "header_bounds_exactly_match_region": True,
        }

        def encoded(value: object) -> bytes:
            return (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")

        files = {
            "README.md": b"Synthetic test artifact.\n",
            "requirements-lock.txt": requirements,
            "source/mgit_frozen.osm.pbf": pbf,
            "source/region.geojson": region,
            "source/source_manifest.json": encoded(source_manifest),
            "graph/graph_schema.sql": graph_schema,
            "graph/mgit_graph.sqlite": graph,
            "results/graph_validation.json": encoded(graph_validation),
            "results/test_results.json": encoded(test_results),
            "results/deterministic_build_results.json": encoded(deterministic),
            "results/source_validation.json": encoded(source_validation),
        }
        manifest = {
            "schema_version": 1,
            "artifact": "S6B1_MGIT_Road_Graph_Foundation_v1",
            "build_version": "S6B1-v1",
            "map_version": f"mgit-pbf-{pbf_hash[:16]}-v1",
            "gate_decision": "S6B1-CONDITIONAL",
            "source_pbf_sha256": pbf_hash,
            "region_sha256": region_hash,
            "test_counts": {"passed": 2, "failed": 0, "skipped": 0},
            "files": [
                {"path": path, "size_bytes": len(data), "sha256": sha256(data)}
                for path, data in sorted(files.items())
            ],
        }
        manifest_bytes = encoded(manifest)
        manifest_path = self.directory / "S6B1_ARTIFACT_MANIFEST_v1.json"
        manifest_path.write_bytes(manifest_bytes)

        archive_path = self.directory / "S6B1_MGIT_Road_Graph_Foundation_v1.zip"
        with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
            for path, data in files.items():
                if corrupt_member and path == "graph/mgit_graph.sqlite":
                    data = b"X" * len(data)
                archive.writestr(f"{self.root}/{path}", data)
            archive.writestr(f"{self.root}/S6B1_ARTIFACT_MANIFEST_v1.json", manifest_bytes)
            if extra_member is not None:
                archive.writestr(extra_member, b"unexpected")

        self.reference = {
            "schema_version": 1,
            "map_version": f"mgit-pbf-{pbf_hash[:16]}-v1",
            "source_pbf_sha256": pbf_hash,
            "region_sha256": region_hash,
            "graph_sha256": graph_hash,
            "display_sha256": None,
            "toolchain": {
                "build_version": "S6B1-v1",
                "python_version": "3.12",
                "osmium_version": "4.3.1",
                "requirements_lock_sha256": sha256(requirements),
            },
            "crs": {
                "geodetic": "CRS84/WGS84",
                "axis_order": "longitude,latitude",
                "local_frame_id": "SYNTHETIC_NED_0_0_0_WGS84_v1",
                "local_frame_axes": ["north", "east", "down"],
                "anchor": {
                    "longitude_deg": 0.0,
                    "latitude_deg": 0.0,
                    "ellipsoid_height_m": 0.0,
                },
            },
            "bounds": [-0.01, -0.01, 0.01, 0.01],
            "notices": [
                "Synthetic fixture; no private bytes.",
                "© OpenStreetMap contributors; ODbL 1.0.",
            ],
            "route_status": "FIELD_VALIDATION_PENDING",
            "gate_decision": "S6B1-CONDITIONAL",
            "graph_logical_sha256": logical_hash,
            "delivery": {
                "artifact": "S6B1_MGIT_Road_Graph_Foundation_v1",
                "archive_root": self.root,
                "manifest": {
                    "filename": manifest_path.name,
                    "size_bytes": manifest_path.stat().st_size,
                    "sha256": verifier.sha256_file(manifest_path),
                },
                "archive": {
                    "filename": archive_path.name,
                    "size_bytes": archive_path.stat().st_size,
                    "sha256": verifier.sha256_file(archive_path),
                },
            },
            "verification": {
                "graph_schema_sha256": sha256(graph_schema),
                "node_count": 3,
                "edge_count": 4,
                "way_count": 2,
                "tests_passed": 2,
                "tests_failed": 0,
                "tests_skipped": 0,
                "byte_identical_rebuild": True,
                "logical_identical_rebuild": True,
            },
            "source_pbf_redistribution_authorized": False,
            "limitations": ["Synthetic verifier test only."],
        }
        self.reference_path = directory / "reference.json"
        self.write_reference()

    def write_reference(self) -> None:
        self.reference_path.write_text(
            json.dumps(self.reference, indent=2) + "\n", encoding="utf-8"
        )


class MapGraphManifestContractTest(unittest.TestCase):
    def test_schema_is_tier_a_and_fixture_validates(self):
        schema = json.loads(
            (ROOT / "contracts/schemas/map_graph_manifest_v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        fixture = json.loads(
            (ROOT / "contracts/fixtures/map_graph_manifest_v1_fixture.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["required"]),
            {
                "schema_version",
                "map_version",
                "source_pbf_sha256",
                "region_sha256",
                "graph_sha256",
                "display_sha256",
                "toolchain",
                "crs",
                "bounds",
                "notices",
                "route_status",
            },
        )
        jsonschema.Draft202012Validator(schema).validate(fixture)

    def test_tracked_reference_validates_and_remains_hash_only(self):
        schema = json.loads(verifier.DEFAULT_SCHEMA.read_text(encoding="utf-8"))
        reference = json.loads(verifier.DEFAULT_REFERENCE.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(reference)
        verifier.verify_map_version_lineage(
            reference["map_version"],
            reference["source_pbf_sha256"],
            label="reference",
        )
        self.assertFalse(reference["source_pbf_redistribution_authorized"])
        self.assertIsNone(reference["display_sha256"])
        self.assertEqual(reference["route_status"], "FIELD_VALIDATION_PENDING")


class S6B1ArtifactVerifierTest(unittest.TestCase):
    def verify(self, fixture: SyntheticS6B1):
        return verifier.verify_artifact(
            fixture.directory, fixture.reference_path, verifier.DEFAULT_SCHEMA
        )

    def test_valid_external_artifact_passes_without_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture = SyntheticS6B1(directory)
            before = sorted(path.name for path in directory.iterdir())
            result = self.verify(fixture)
            after = sorted(path.name for path in directory.iterdir())
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["manifest_entries_verified"], 11)
            self.assertEqual(before, after)

    def test_delivery_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticS6B1(Path(temporary))
            fixture.reference["delivery"]["archive"]["sha256"] = "0" * 64
            fixture.write_reference()
            with self.assertRaisesRegex(verifier.VerificationError, "delivery SHA-256"):
                self.verify(fixture)

    def test_map_version_hash_token_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticS6B1(Path(temporary))
            fixture.reference["map_version"] = "mgit-pbf-0000000000000000-v1"
            fixture.write_reference()
            with self.assertRaisesRegex(
                verifier.VerificationError,
                "map_version hash token does not match source PBF",
            ):
                self.verify(fixture)

    def test_additional_delivery_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticS6B1(Path(temporary))
            (fixture.directory / "unexpected.bin").write_bytes(b"unexpected")
            with self.assertRaisesRegex(verifier.VerificationError, "exactly the manifest and ZIP"):
                self.verify(fixture)

    def test_member_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticS6B1(Path(temporary), corrupt_member=True)
            with self.assertRaisesRegex(verifier.VerificationError, "member SHA-256"):
                self.verify(fixture)

    def test_extra_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticS6B1(
                Path(temporary), extra_member="S6B1_MGIT_Road_Graph_Foundation/extra.txt"
            )
            with self.assertRaisesRegex(verifier.VerificationError, "member set"):
                self.verify(fixture)

    def test_path_traversal_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticS6B1(
                Path(temporary), extra_member="S6B1_MGIT_Road_Graph_Foundation/../escape.txt"
            )
            with self.assertRaisesRegex(verifier.VerificationError, "unsafe traversal"):
                self.verify(fixture)

    def test_final_route_claim_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticS6B1(Path(temporary), final_selected=True)
            with self.assertRaisesRegex(verifier.VerificationError, "final selected route"):
                self.verify(fixture)


if __name__ == "__main__":
    unittest.main()
