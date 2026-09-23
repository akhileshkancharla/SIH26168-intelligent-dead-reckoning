import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ci import verify_repository


class ForbiddenAllowlistTest(unittest.TestCase):
    def test_s1_fixture_approval_is_pinned_to_exact_identity(self):
        rel = (
            "android/acquisition/imported/S1_Android_Acquisition_Spike/"
            "fixtures/deterministic_session/chunk_00001.jsonl"
        )
        self.assertEqual(
            verify_repository.APPROVED_FORBIDDEN_FILES[rel],
            {
                "size_bytes": 4895,
                "sha256": (
                    "8cd785a19e3c472f8b13d3b28b148dd09cf74f067455b4b23aa131cd909672c2"
                ),
            },
        )

    def test_only_exact_path_size_and_hash_are_approved(self):
        payload = b"deterministic synthetic fixture\n"
        digest = hashlib.sha256(payload).hexdigest()
        approval = {"fixtures/approved.jsonl": {"size_bytes": len(payload), "sha256": digest}}
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture.jsonl"
            fixture.write_bytes(payload)
            with mock.patch.dict(
                verify_repository.APPROVED_FORBIDDEN_FILES, approval, clear=True
            ):
                self.assertTrue(
                    verify_repository.approved_forbidden_file(
                        fixture, "fixtures/approved.jsonl"
                    )
                )
                self.assertFalse(
                    verify_repository.approved_forbidden_file(
                        fixture, "fixtures/different.jsonl"
                    )
                )
                fixture.write_bytes(payload + b"tampered")
                self.assertFalse(
                    verify_repository.approved_forbidden_file(
                        fixture, "fixtures/approved.jsonl"
                    )
                )


if __name__ == "__main__":
    unittest.main()
