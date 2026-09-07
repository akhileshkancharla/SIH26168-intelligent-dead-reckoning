"""WP-10.1 (Issue #79): tests for tools/dataset/workspace.py.

These tests never touch the repository's own working tree with created
directories -- every workspace root used here is a tempfile.TemporaryDirectory
that is guaranteed outside the repo, and the tests asserting the *rejection*
path do so without ever calling mkdir on a path inside the repo.
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


workspace = _load_module("wp10_workspace", REPO_ROOT / "tools" / "dataset" / "workspace.py")


class WorkspaceLocationGuardTest(unittest.TestCase):
    def test_repo_root_itself_is_rejected(self):
        with self.assertRaises(workspace.WorkspaceLocationError):
            workspace.assert_outside_repository(REPO_ROOT)

    def test_path_inside_repo_is_rejected(self):
        with self.assertRaises(workspace.WorkspaceLocationError):
            workspace.assert_outside_repository(REPO_ROOT / "private" / "io_vnbd")

    def test_sibling_of_repo_is_accepted(self):
        # Must not raise.
        workspace.assert_outside_repository(REPO_ROOT.parent / "sih26168-private-data")

    def test_default_workspace_root_is_outside_the_repo(self):
        root = workspace.default_workspace_root()
        # Must not raise -- default_workspace_root()'s own contract is
        # that its result always passes this guard.
        workspace.assert_outside_repository(root)

    def test_env_var_override_is_honored(self, monkeypatch=None):
        with tempfile.TemporaryDirectory() as tmp:
            import os

            old = os.environ.get(workspace.WORKSPACE_ROOT_ENV_VAR)
            os.environ[workspace.WORKSPACE_ROOT_ENV_VAR] = tmp
            try:
                self.assertEqual(workspace.default_workspace_root(), Path(tmp).resolve())
            finally:
                if old is None:
                    os.environ.pop(workspace.WORKSPACE_ROOT_ENV_VAR, None)
                else:
                    os.environ[workspace.WORKSPACE_ROOT_ENV_VAR] = old


class EnsureWorkspaceTest(unittest.TestCase):
    def test_ensure_workspace_creates_expected_subdirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sih26168-private-data"
            created = workspace.ensure_workspace(root)
            self.assertEqual(created, root.resolve())
            for name in workspace.WORKSPACE_SUBDIRS:
                subdir = root / name
                self.assertTrue(subdir.is_dir(), f"missing workspace subdir: {name}")
                self.assertTrue((subdir / "README.txt").is_file())

    def test_ensure_workspace_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sih26168-private-data"
            workspace.ensure_workspace(root)
            # A second call must not raise or clobber the READMEs.
            workspace.ensure_workspace(root)
            for name in workspace.WORKSPACE_SUBDIRS:
                self.assertTrue((root / name).is_dir())

    def test_ensure_workspace_refuses_a_path_inside_the_repo(self):
        with self.assertRaises(workspace.WorkspaceLocationError):
            workspace.ensure_workspace(REPO_ROOT / "private" / "io_vnbd")
        # And critically: it must not have created anything.
        self.assertFalse((REPO_ROOT / "private" / "io_vnbd").exists())

    def test_ensure_workspace_rejects_a_symlinked_workspace_root(self):
        # A symlinked root must be refused outright, never followed --
        # even though its resolved target is itself perfectly safe.
        with tempfile.TemporaryDirectory() as tmp:
            real_target = Path(tmp) / "real-target"
            real_target.mkdir()
            symlinked_root = Path(tmp) / "symlinked-root"
            symlinked_root.symlink_to(real_target, target_is_directory=True)
            with self.assertRaises(workspace.WorkspaceLocationError):
                workspace.ensure_workspace(symlinked_root)
            # Nothing must have been created through the symlink.
            for name in workspace.WORKSPACE_SUBDIRS:
                self.assertFalse((real_target / name).exists())

    def test_ensure_workspace_rejects_a_symlinked_subdirectory_pointing_into_the_repo(self):
        # This is exactly the attack the review flagged: a real, safe
        # workspace root passes the root-level assert_outside_repository
        # guard, but one of its subdirectory names (archives/extracted/
        # manifests) already exists as a symlink that would redirect
        # README.txt -- or later private outputs -- into this
        # repository's own working tree.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sih26168-private-data"
            root.mkdir()
            # A dangling symlink is enough to prove rejection -- the
            # target must never actually be created inside the real repo
            # checkout, even by this test.
            inside_repo_target = REPO_ROOT / "private" / "io_vnbd_symlink_target"
            subdir_name = workspace.WORKSPACE_SUBDIRS[0]
            symlinked_subdir = root / subdir_name
            symlinked_subdir.symlink_to(inside_repo_target, target_is_directory=True)
            with self.assertRaises(workspace.WorkspaceLocationError):
                workspace.ensure_workspace(root)
            self.assertFalse(inside_repo_target.exists())

    def test_ensure_workspace_rejects_a_symlinked_subdirectory_even_pointing_outside_the_repo(self):
        # Symlinked subdirectories are refused outright (never followed),
        # regardless of where they point -- not only when the target
        # happens to be unsafe.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sih26168-private-data"
            root.mkdir()
            real_target = Path(tmp) / "real-subdir-target"
            real_target.mkdir()
            subdir_name = workspace.WORKSPACE_SUBDIRS[0]
            symlinked_subdir = root / subdir_name
            symlinked_subdir.symlink_to(real_target, target_is_directory=True)
            with self.assertRaises(workspace.WorkspaceLocationError):
                workspace.ensure_workspace(root)

    def test_ensure_workspace_never_writes_inside_the_repo_even_by_default(self):
        # Guards against a future regression where default_workspace_root()
        # is changed to something repo-relative without updating the guard,
        # without actually materializing anything beside the real repo
        # checkout on disk (this test must be safe to run against a
        # developer's or CI's real working copy).
        import os

        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get(workspace.WORKSPACE_ROOT_ENV_VAR)
            os.environ[workspace.WORKSPACE_ROOT_ENV_VAR] = tmp
            try:
                root = workspace.ensure_workspace()
                self.assertFalse(
                    str(root).startswith(str(REPO_ROOT)),
                    f"default private workspace root must never be inside the repo: {root}",
                )
            finally:
                if old is None:
                    os.environ.pop(workspace.WORKSPACE_ROOT_ENV_VAR, None)
                else:
                    os.environ[workspace.WORKSPACE_ROOT_ENV_VAR] = old


if __name__ == "__main__":
    unittest.main()
