#!/usr/bin/env python3
"""WP-10.3 (Issue #81): duplicate and parent-session grouping.

Per C-15's "duplicate parent grouping" validation rule for I-20 and
R-007's "Six schemas; no shared clock; duplicates" risk, every file that
enters a DatasetManifest must resolve to exactly one immutable group_id
(contracts/schemas/dataset_manifest_v1.schema.json's `group_ids`), so that
WP-10.4's split construction can guarantee zero overlap between
train/validation/test at the *group* level, not just the file level.

Two files belong to the same group if either:
  - they are byte-identical (same SHA-256 digest) -- an exact duplicate; or
  - they declare the same non-empty parent_session_id -- they come from
    the same recording session/journey, so letting them land in different
    splits would leak session-specific signal across the split boundary.

This module operates on abstract FileRecord inputs (identifier, sha256,
optional parent_session_id) and does not itself know how to read a real
IO-VNBD archive or what its per-file metadata format looks like -- that
ingestion step is out of this module's scope (and, like WP-10.2's real
schema names, depends on dataset-specific knowledge this repository does
not have). Group IDs are derived deterministically from group membership
alone, so the same input always produces the same group_ids regardless of
processing order -- no randomness, no wall-clock, no incidental ordering.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class FileRecord:
    """One file's grouping-relevant metadata.

    `parent_session_id` is None when the source declares no session
    grouping for this file -- per I-20's nullability rule ("Unknown
    fields never guessed"), a missing parent_session_id is never
    defaulted to some sentinel that could accidentally collide with a
    real session ID.
    """

    identifier: str
    sha256: str
    parent_session_id: Optional[str] = None


class _UnionFind:
    """Minimal union-find (disjoint-set) with path compression and union
    by rank, scoped to this module -- grouping is the only place in
    tools/dataset that needs it.
    """

    def __init__(self, items: List[str]) -> None:
        self._parent = {item: item for item in items}
        self._rank = {item: 0 for item in items}

    def find(self, item: str) -> str:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a == root_b:
            return
        if self._rank[root_a] < self._rank[root_b]:
            root_a, root_b = root_b, root_a
        self._parent[root_b] = root_a
        if self._rank[root_a] == self._rank[root_b]:
            self._rank[root_a] += 1


def _deterministic_group_id(member_identifiers: List[str]) -> str:
    """Derive a stable group_id from a component's sorted member identifiers.

    Using a hash of the *sorted* member set (rather than, say, the first
    member seen) means the resulting group_id does not depend on input
    ordering or on which record happened to be processed first.
    """
    canonical = "\x1f".join(sorted(member_identifiers))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"grp-{digest[:16]}"


def compute_groups(records: List[FileRecord]) -> Dict[str, str]:
    """Return {identifier: group_id} for every record, per the duplicate/
    parent-session union rule described in this module's docstring.

    Raises ValueError if `records` contains two entries with the same
    identifier but different sha256/parent_session_id (an inconsistent
    input, not a grouping decision this module can make silently), or if
    `records` is empty.
    """
    if not records:
        raise ValueError("compute_groups requires at least one FileRecord")

    seen: Dict[str, FileRecord] = {}
    for record in records:
        prior = seen.get(record.identifier)
        if prior is not None and prior != record:
            raise ValueError(
                f"inconsistent records for identifier {record.identifier!r}: {prior} vs {record}"
            )
        seen[record.identifier] = record

    identifiers = [r.identifier for r in records]
    uf = _UnionFind(identifiers)

    by_hash: Dict[str, List[str]] = {}
    by_session: Dict[str, List[str]] = {}
    for record in records:
        by_hash.setdefault(record.sha256, []).append(record.identifier)
        if record.parent_session_id:
            by_session.setdefault(record.parent_session_id, []).append(record.identifier)

    for group in by_hash.values():
        for other in group[1:]:
            uf.union(group[0], other)
    for group in by_session.values():
        for other in group[1:]:
            uf.union(group[0], other)

    components: Dict[str, List[str]] = {}
    for identifier in identifiers:
        root = uf.find(identifier)
        components.setdefault(root, []).append(identifier)

    identifier_to_group: Dict[str, str] = {}
    for members in components.values():
        group_id = _deterministic_group_id(members)
        for member in members:
            identifier_to_group[member] = group_id
    return identifier_to_group


def duplicate_members_by_group(records: List[FileRecord], groups: Dict[str, str]) -> Dict[str, List[str]]:
    """Return {group_id: [identifiers]} restricted to groups containing an
    exact (same-hash) duplicate pair -- a reporting helper distinguishing
    "grouped because duplicate" from "grouped because same session" for
    evidence/audit purposes. A group formed purely by shared
    parent_session_id (no hash collisions) is omitted.
    """
    by_group_hash_counts: Dict[str, Dict[str, List[str]]] = {}
    for record in records:
        group_id = groups[record.identifier]
        by_group_hash_counts.setdefault(group_id, {}).setdefault(record.sha256, []).append(record.identifier)

    result: Dict[str, List[str]] = {}
    for group_id, hash_map in by_group_hash_counts.items():
        duplicate_identifiers = [ident for idents in hash_map.values() if len(idents) > 1 for ident in idents]
        if duplicate_identifiers:
            result[group_id] = sorted(duplicate_identifiers)
    return result


def apply_groups_to_manifest(document: dict, groups: Dict[str, str]) -> None:
    """Set `document["group_ids"]` to the sorted unique group_ids from
    `groups`, mutating the DatasetManifest document in place.

    Does not itself validate the resulting document -- call
    tools.dataset.manifest.validate_manifest afterward.
    """
    document["group_ids"] = sorted(set(groups.values()))
