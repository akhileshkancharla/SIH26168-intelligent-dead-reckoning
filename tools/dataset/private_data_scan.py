#!/usr/bin/env python3
"""WP-10.6 (Issue #84): private-data exclusion scanner for tools/dataset.

docs/PRIVATE_ARTIFACT_POLICY.md and ci/verify_repository.py's `forbidden`
check are the repository-wide guarantee that no raw private artifact ever
enters Git or CI. This module is a narrower, WP-10-scoped *complement* to
that check -- not a replacement for it -- so that tools/dataset's own test
suite can prove, on every run, that the directory this work package owns
never accumulates anything that looks like real dataset content: an
oversized file, a raw archive/sensor-data suffix, or a `private/`- or
`data/`-prefixed sub-path. It intentionally reuses the same reasoning as
ci/verify_repository.py's forbidden() (which scans the whole repository
filesystem, not just Git-tracked files) so that a violation inside
tools/dataset is caught here, at the smallest possible scope, in addition
to the repository-wide gate.

This module does not, and cannot, prove the *absence* of private data
anywhere a determined contributor might hide it -- it is one more
deny-by-default layer, not a substitute for the human review
docs/PRIVATE_ARTIFACT_POLICY.md requires before anything enters this
directory.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

#: Suffixes that never belong in tools/dataset: raw archives, extracted
#: sensor/telemetry formats, and other binary container formats a real
#: IO-VNBD extract could plausibly use. This directory ships only Python
#: source, JSON schemas/config/fixtures, and Markdown -- nothing here
#: needs any of these suffixes, ever.
FORBIDDEN_DATA_SUFFIXES = {
    ".zip", ".tar", ".gz", ".tgz", ".7z", ".rar",
    ".bin", ".dat", ".mat", ".h5", ".hdf5", ".npz", ".npy",
    ".parquet", ".sqlite", ".sqlite3", ".db",
    ".pbf", ".bag", ".mcap",
}

#: A generous ceiling for anything legitimately shipped by this
#: directory (source, schemas, small synthetic fixtures, docs) -- far
#: below the size any real IO-VNBD archive or extract would be. This is
#: deliberately smaller than ci/verify_repository.py's repository-wide
#: 5 MiB ceiling, because tools/dataset specifically must never hold
#: anything dataset-sized at all.
MAX_ALLOWED_FILE_BYTES = 256 * 1024

#: Path segment names that are never allowed anywhere under a scanned
#: tree, matching ci/verify_repository.py's forbidden() path-prefix
#: check (`data/`, `private/`) applied at any depth, not only at the
#: scanned root.
FORBIDDEN_PATH_SEGMENTS = {"data", "private"}

_EXCLUDED_DIR_NAMES = {"__pycache__"}


class PrivateDataScanError(Exception):
    """Raised when a scanned tree contains one or more disallowed paths.

    A hard stop, matching WP-10's "no raw bytes enter repo" acceptance
    criterion -- callers must not proceed past this without human review.
    """


def _iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _EXCLUDED_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        yield path


def scan_tree(root: Path) -> List[str]:
    """Return a list of human-readable violation descriptions for `root`.

    An empty list means the tree is clean. Never raises for an
    ordinary clean or dirty tree; see assert_tree_is_clean for the
    raising variant a test or CI step should actually call.
    """
    root = root.expanduser().resolve()
    violations: List[str] = []
    for path in _iter_files(root):
        rel = path.relative_to(root)
        rel_parts = rel.parts
        if any(part.casefold() in FORBIDDEN_PATH_SEGMENTS for part in rel_parts[:-1]):
            violations.append(f"forbidden path segment (data/ or private/): {rel.as_posix()}")
        if path.suffix.lower() in FORBIDDEN_DATA_SUFFIXES:
            violations.append(f"forbidden data-file suffix {path.suffix.lower()!r}: {rel.as_posix()}")
        size = path.stat().st_size
        if size > MAX_ALLOWED_FILE_BYTES:
            violations.append(
                f"file exceeds {MAX_ALLOWED_FILE_BYTES} byte ceiling ({size} bytes): {rel.as_posix()}"
            )
    return sorted(violations)


def assert_tree_is_clean(root: Path) -> None:
    """Raise PrivateDataScanError if scan_tree(root) finds any violation."""
    violations = scan_tree(root)
    if violations:
        raise PrivateDataScanError(
            "private-data exclusion scan failed; quarantine and stop -- "
            f"a human must remove or relocate these before proceeding: {violations}"
        )
