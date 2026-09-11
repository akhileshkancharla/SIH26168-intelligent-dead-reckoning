from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "ci" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


selector = load("select_checks")
gate = load("verify_ci_result")


class SelectionTests(unittest.TestCase):
    def lanes(self, *paths):
        return {key for key, value in selector.select_paths(list(paths))["selected"].items() if value}

    def test_documentation_only(self):
        self.assertEqual(self.lanes("README.md", "docs/guides/usage.md"), set())

    def test_dataset_with_updated_snapshot_and_manifest(self):
        self.assertEqual(self.lanes("tools/dataset/manifest.py", "docs/architecture/dependency-graph/graph.json",
                                    "docs/bootstrap/repository_manifest.json"), {"dataset"})

    def test_contracts_ci_architecture_unknown_and_dependencies_run_everything(self):
        for path in ("contracts/schemas/new.json", "contracts/fixtures/test.json", "tools/contracts/new.py",
                     "pyproject.toml", ".github/workflows/ci.yml", "ci/select_checks.py", "AGENTS.md",
                     "docs/architecture/design.md", "new-module/logic.py", "requirements.txt"):
            with self.subTest(path=path):
                self.assertEqual(self.lanes(path), set(selector.LANES))

    def test_native_and_android_include_cross_language_consumers(self):
        for path in ("core/navigation/src/logic.cpp", "android/navigation-jni/new.cpp", "CMakeLists.txt",
                     "android/app/src/main/AndroidManifest.xml", "android/app/src/main/res/values/strings.xml",
                     "android/settings.gradle.kts"):
            with self.subTest(path=path):
                self.assertEqual(self.lanes(path), {"cpp", "android", "python"})

    def test_bootstrap_and_acquisition(self):
        for path in ("tools/bootstrap/tests/test_smoke.py", "tools/acquisition/s1_fixture_roundtrip.py"):
            self.assertEqual(self.lanes(path), {"python"})

    def test_empty_and_malformed_paths_are_conservative(self):
        for paths in ([], ["../README.md"], ["docs/../core/test.md"], ["docs\\file.md"], ["docs/bad\nfile.md"]):
            self.assertTrue(all(selector.select_paths(paths)["selected"].values()))

    def test_large_diff_is_not_truncated(self):
        paths = [f"docs/page-{index}.md" for index in range(1000)] + ["contracts/VERSION"]
        self.assertTrue(all(selector.select_paths(paths)["selected"].values()))

    def test_push_manual_and_missing_identity_run_full(self):
        for event in ("push", "workflow_dispatch", "pull_request"):
            self.assertTrue(all(selector.plan_for_event(event, {}, "")["selected"].values()))


class GitDiffTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="sih-ci-diff-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "CI Test")
        self.git("config", "user.email", "ci@example.invalid")
        self.write("README.md", "base\n")
        self.write("tools/dataset/old.py", "# sample\n")
        self.commit("base")
        self.base = self.git("rev-parse", "HEAD")
        self.git("checkout", "-b", "feature")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, check=True,
                              text=True, encoding="utf-8").stdout.strip()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit(self, message):
        self.git("add", ".")
        self.git("commit", "-m", message)

    def merge_plan(self):
        head = self.git("rev-parse", "HEAD")
        self.git("checkout", "main")
        self.git("merge", "--no-ff", "feature", "-m", "PR merge")
        merge = self.git("rev-parse", "HEAD")
        event = {"pull_request": {"base": {"sha": self.base}, "head": {"sha": head}}}
        return selector.plan_for_event("pull_request", event, merge, self.root), event, merge

    def test_cumulative_pr_diff_includes_earlier_commit(self):
        self.write("contracts/schema.json", "{}\n")
        self.commit("contract")
        self.write("docs/last commit.md", "docs\n")
        self.commit("docs")
        plan, _, _ = self.merge_plan()
        self.assertTrue(all(plan["selected"].values()))

    def test_rename_out_of_dataset_retains_deleted_path(self):
        self.write("docs/moved.md", "# sample\n")
        self.git("rm", "tools/dataset/old.py")
        self.commit("rename")
        plan, _, _ = self.merge_plan()
        self.assertEqual(plan["selected"], {"dataset": True, "python": False, "cpp": False, "android": False})

    def test_deletion_selects_original_consumer(self):
        self.git("rm", "tools/dataset/old.py")
        self.commit("delete")
        plan, _, _ = self.merge_plan()
        self.assertTrue(plan["selected"]["dataset"])
        self.assertFalse(plan["selected"]["android"])

    def test_missing_history_or_unexpected_checkout_selects_full(self):
        self.write("docs/guide.md", "docs\n")
        self.commit("docs")
        _, event, merge = self.merge_plan()
        with patch.object(selector, "git", side_effect=subprocess.CalledProcessError(128, "git")):
            self.assertTrue(all(selector.plan_for_event("pull_request", event, merge, self.root)["selected"].values()))
        self.assertTrue(all(selector.plan_for_event("pull_request", event, "f" * 40, self.root)["selected"].values()))


class GateTests(unittest.TestCase):
    def setUp(self):
        self.needs = {"changes": {"result": "success", "outputs": dict.fromkeys(gate.LANES, "false")},
                      "policy": {"result": "success"}}
        self.needs.update({lane: {"result": "skipped"} for lane in gate.LANES})

    def test_documentation_and_selected_success(self):
        self.assertEqual(gate.validate(self.needs), [])
        self.needs["changes"]["outputs"]["dataset"] = "true"
        self.needs["dataset"]["result"] = "success"
        self.assertEqual(gate.validate(self.needs), [])

    def test_failed_or_cancelled_or_skipped_required_work_cannot_pass(self):
        for job in ("changes", "policy", *gate.LANES):
            for result in ("failure", "cancelled", "skipped", None):
                with self.subTest(job=job, result=result):
                    needs = copy.deepcopy(self.needs)
                    needs["changes"]["outputs"] = dict.fromkeys(gate.LANES, "true")
                    for lane in gate.LANES:
                        needs[lane]["result"] = "success"
                    needs[job]["result"] = result
                    self.assertTrue(gate.validate(needs))

    def test_invalid_or_missing_outputs_and_results(self):
        for flag in (None, "", "TRUE", True, "maybe"):
            needs = copy.deepcopy(self.needs)
            needs["changes"]["outputs"]["dataset"] = flag
            self.assertTrue(gate.validate(needs))
        for job in self.needs:
            needs = copy.deepcopy(self.needs)
            del needs[job]
            self.assertTrue(gate.validate(needs))

    def test_failure_in_unselected_group_is_not_hidden(self):
        self.needs["dataset"]["result"] = "failure"
        self.assertTrue(gate.validate(self.needs))

    def test_cli_fails_on_malformed_results(self):
        with patch.dict("os.environ", {"NEEDS_JSON": "not JSON"}):
            self.assertEqual(gate.main(), 1)
        with patch.dict("os.environ", {"NEEDS_JSON": json.dumps(self.needs)}):
            self.assertEqual(gate.main(), 0)


if __name__ == "__main__":
    unittest.main()
