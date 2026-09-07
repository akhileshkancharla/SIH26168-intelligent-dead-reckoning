#!/usr/bin/env python3
"""WP-10.1 (Issue #79): private dataset workspace management.

Per docs/PRIVATE_ARTIFACT_POLICY.md ("Raw IO-VNBD bytes or extracts ...
must remain outside Git and CI") and ci/verify_repository.py's `forbidden`
check (which flags any on-disk path starting with `private/` or `data/`
under the repository root, regardless of Git tracking status), a private
dataset workspace must never be materialized inside this repository's
working tree -- not even in a directory .gitignore already excludes.

This module is the single place that decides where the private workspace
lives and enforces that it is always outside the repository, so no other
WP-10 tool has to re-derive or re-guess that boundary.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Overrides the private workspace root. Must resolve to a path outside
#: REPO_ROOT; ensure_workspace() refuses otherwise. Left unset, the
#: default lives beside (not inside) the repository checkout.
WORKSPACE_ROOT_ENV_VAR = "SIH26168_PRIVATE_DATA_ROOT"

# Sub-directories every private workspace root is given. Names only,
# never populated with real content by this module.
WORKSPACE_SUBDIRS = ("archives", "extracted", "manifests")


class WorkspaceLocationError(Exception):
    """Raised when a proposed private workspace root is unsafe to use.

    This is a hard stop, matching WP-10's own "Immediate stop: ...
    private destination is unclear" condition -- callers must not fall
    back to a repo-relative path on this error.
    """


def _is_inside(candidate: Path, container: Path) -> bool:
    try:
        candidate.relative_to(container)
        return True
    except ValueError:
        return False


def default_workspace_root() -> Path:
    """Return the private workspace root, honoring SIH26168_PRIVATE_DATA_ROOT.

    Without the environment variable set, defaults to a directory named
    `sih26168-private-data` that is a *sibling* of the repository checkout
    (REPO_ROOT.parent / "sih26168-private-data"), which is guaranteed to
    be outside REPO_ROOT by construction. Operators who want the private
    workspace somewhere else entirely (a separate disk/volume) should set
    SIH26168_PRIVATE_DATA_ROOT explicitly.
    """
    override = os.environ.get(WORKSPACE_ROOT_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return (REPO_ROOT.parent / "sih26168-private-data").resolve()


def assert_outside_repository(root: Path) -> None:
    """Raise WorkspaceLocationError if `root` is inside REPO_ROOT.

    This is the enforcement point every other WP-10 tool should call
    before writing anything to a private workspace path -- including
    tools built in later sub-issues (WP-10.2 onward) that accept a
    workspace root from configuration rather than from
    default_workspace_root() directly.
    """
    resolved = root.expanduser().resolve()
    if resolved == REPO_ROOT.resolve() or _is_inside(resolved, REPO_ROOT.resolve()):
        raise WorkspaceLocationError(
            f"private workspace root {resolved} is inside the repository checkout "
            f"({REPO_ROOT}); ci/verify_repository.py forbidden treats any on-disk "
            "private/ or data/-prefixed path here as a policy violation regardless "
            f"of Git tracking. Set {WORKSPACE_ROOT_ENV_VAR} to a path outside the repo."
        )


def ensure_workspace(root: Path | None = None) -> Path:
    """Create (if needed) and return the private workspace root.

    Creates WORKSPACE_SUBDIRS under `root` (or default_workspace_root()
    when omitted) with restrictive permissions, and writes a short README
    into each explaining its purpose. Never writes dataset content -- that
    is WP-10.2's ingestion tooling's job, operating against the root this
    function returns.
    """
    workspace_root = (root or default_workspace_root()).expanduser().resolve()
    assert_outside_repository(workspace_root)
    workspace_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in WORKSPACE_SUBDIRS:
        subdir = workspace_root / name
        subdir.mkdir(parents=True, exist_ok=True, mode=0o700)
        readme = subdir / "README.txt"
        if not readme.exists():
            readme.write_text(_SUBDIR_README[name], encoding="utf-8")
    return workspace_root


_SUBDIR_README = {
    "archives": (
        "WP-10 private workspace: archives/\n\n"
        "Immutable, as-received IO-VNBD source archives referenced by a\n"
        "DatasetManifest's archive_hashes. Read-only once hashed; never\n"
        "copied into the Git repository (see docs/PRIVATE_ARTIFACT_POLICY.md).\n"
    ),
    "extracted": (
        "WP-10 private workspace: extracted/\n\n"
        "Files extracted from archives/ for schema validation, grouping and\n"
        "split construction (WP-10.2 through WP-10.4). Referenced by a\n"
        "DatasetManifest's file_hashes. Never copied into the Git repository.\n"
    ),
    "manifests": (
        "WP-10 private workspace: manifests/\n\n"
        "Working copies of DatasetManifest documents (hash-only, no raw\n"
        "bytes) before they are reviewed and committed into the Git\n"
        "repository's own manifest location.\n"
    ),
}
