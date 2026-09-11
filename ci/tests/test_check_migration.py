import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("migration", Path(__file__).resolve().parents[1] / "migrate_required_checks.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class MigrationTests(unittest.TestCase):
    def test_preserves_unrelated_checks_provider_and_strictness(self):
        current = {"strict": True, "contexts": ["dataset-check", "external-audit"], "checks": [
            {"context": "dataset-check", "app_id": 123},
            {"context": "external-audit", "app_id": 456},
            {"context": "sensitive-review-check", "app_id": 789},
        ]}
        original = copy.deepcopy(current)
        result = migration.replacement(current, 123)
        self.assertEqual(current, original)
        self.assertTrue(result["strict"])
        checks = {item["context"]: item["app_id"] for item in result["checks"]}
        self.assertEqual(checks, {"external-audit": 456, "sensitive-review-check": 789,
                                  "pull-request-governance-check": 123, "ci-required": 123})
        self.assertEqual(migration.replacement(result, 123), result)

    def test_unrestricted_provider_and_legacy_contexts_remain(self):
        result = migration.replacement({"strict": False, "contexts": ["custom"], "checks": []}, 123)
        self.assertFalse(result["strict"])
        self.assertIn({"context": "custom", "app_id": -1}, result["checks"])

    def test_missing_protection_refused(self):
        with self.assertRaises(ValueError):
            migration.replacement({}, 123)

    def evidence(self):
        pr = {"state": "open", "number": 42, "base": {"ref": "main"},
              "head": {"sha": "abc", "repo": {"full_name": "owner/repo"}}}
        run = {"event": "pull_request", "path": ".github/workflows/ci.yml", "head_sha": "abc",
               "conclusion": "success", "status": "completed", "pull_requests": [{"number": 42}]}
        jobs = {"jobs": [{"name": "ci-required", "conclusion": "success"}]}
        return pr, run, jobs

    def test_successful_current_pr_gate_required(self):
        pr, run, jobs = self.evidence()
        self.assertEqual(migration.verify_evidence(pr, run, jobs, "owner/repo"), jobs["jobs"][0])
        for key, value in (("head_sha", "stale"), ("conclusion", "failure"), ("event", "push"),
                           ("path", ".github/workflows/other.yml"), ("pull_requests", [])):
            modified = dict(run, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                migration.verify_evidence(pr, modified, jobs, "owner/repo")
        jobs["jobs"][0]["conclusion"] = "skipped"
        with self.assertRaises(ValueError):
            migration.verify_evidence(pr, run, jobs, "owner/repo")

    def test_closed_or_fork_pr_refused(self):
        pr, run, jobs = self.evidence()
        pr["state"] = "closed"
        with self.assertRaises(ValueError):
            migration.verify_evidence(pr, run, jobs, "owner/repo")
        pr["state"] = "open"
        pr["head"]["repo"]["full_name"] = "fork/repo"
        with self.assertRaises(ValueError):
            migration.verify_evidence(pr, run, jobs, "owner/repo")


if __name__ == "__main__":
    unittest.main()
