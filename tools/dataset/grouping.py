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
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


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


def _validate_record(record: FileRecord) -> None:
    """Raise ValueError if `record`'s fields cannot be trusted for grouping.

    An empty identifier, a malformed sha256, or a blank/whitespace-only
    parent_session_id are not grouping decisions this module can make
    silently: an empty/malformed hash would group unrelated files as
    duplicates by accident, and a blank session id would group unrelated
    records into one session (since '' == '' just like any other shared
    session id would union them). None (not an empty string) remains the
    only accepted way to say "no session" -- see FileRecord's docstring.
    """
    if not record.identifier or not record.identifier.strip():
        raise ValueError(f"FileRecord has an empty or blank identifier: {record!r}")
    if not _SHA256_HEX_PATTERN.match(record.sha256):
        raise ValueError(
            f"FileRecord {record.identifier!r} has a malformed sha256 (must be exactly 64 "
            f"lowercase hex characters): {record.sha256!r}"
        )
    if record.parent_session_id is not None and not record.parent_session_id.strip():
        raise ValueError(
            f"FileRecord {record.identifier!r} has a blank/whitespace-only parent_session_id "
            "-- use None (not an empty or whitespace string) to mean 'no session', or a blank "
            "session id would incorrectly group this record with any other blank-session record"
        )


def compute_groups(records: List[FileRecord]) -> Dict[str, str]:
    """Return {identifier: group_id} for every record, per the duplicate/
    parent-session union rule described in this module's docstring.

    Raises ValueError if `records` is empty, if any record fails
    _validate_record, or if `records` contains two entries with the same
    identifier but different sha256/parent_session_id (an inconsistent
    input, not a grouping decision this module can make silently).
    Repeated *identical* records (same identifier, sha256 and
    parent_session_id) are accepted and deduplicated before grouping, so
    they do not distort the resulting group_id or duplicate-evidence
    reporting (see duplicate_members_by_group) by being counted twice.
    """
    if not records:
        raise ValueError("compute_groups requires at least one FileRecord")

    seen: Dict[str, FileRecord] = {}
    for record in records:
        _validate_record(record)
        prior = seen.get(record.identifier)
        if prior is not None and prior != record:
            raise ValueError(
                f"inconsistent records for identifier {record.identifier!r}: {prior} vs {record}"
            )
        seen[record.identifier] = record

    # Built from the deduplicated `seen` records, not the raw `records`
    # list: a repeated identical record must not be counted twice when
    # forming by_hash/by_session groups, or one f1 record and two
    # identical f1 records would (incorrectly) produce a different
    # group_id than a single f1 record would, and duplicate_members_by_group
    # would (incorrectly) report the repeated identifier as if it were two
    # distinct duplicate files.
    deduplicated_records = list(seen.values())
    identifiers = [r.identifier for r in deduplicated_records]
    uf = _UnionFind(identifiers)

    by_hash: Dict[str, List[str]] = {}
    by_session: Dict[str, List[str]] = {}
    for record in deduplicated_records:
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

    `records` is deduplicated by identifier before counting, for the same
    reason compute_groups deduplicates internally: a repeated identical
    record must not be reported as if it were two distinct duplicate
    files.
    """
    deduplicated_records = list({record.identifier: record for record in records}.values())
    by_group_hash_counts: Dict[str, Dict[str, List[str]]] = {}
    for record in deduplicated_records:
        group_id = groups[record.identifier]
        by_group_hash_counts.setdefault(group_id, {}).setdefault(record.sha256, []).append(record.identifier)

    result: Dict[str, List[str]] = {}
    for group_id, hash_map in by_group_hash_counts.items():
        duplicate_identifiers = [ident for idents in hash_map.values() if len(idents) > 1 for ident in idents]
        if duplicate_identifiers:
            result[group_id] = sorted(duplicate_identifiers)
    return result


def apply_groups_to_manifest(document: dict, groups: Dict[str, str]) -> None:
    """Set `document["group_ids"]` and `document["file_group_ids"]` from
    `groups`, mutating the DatasetManifest document in place.

    `document["group_ids"]` is the sorted unique set of group_ids, kept
    for backward-compatible enumeration (e.g. WP-10.4's split
    assignment operates over this set). `document["file_group_ids"]` is
    the full identifier -> group_id membership mapping itself: storing
    only the unique group_id set previously discarded this mapping
    entirely, so a manifest could not prove that every file resolves to
    exactly one group, or let WP-10.4 verify group-safe splits without
    recomputing membership from private, non-committed metadata. See
    verify_group_membership for the completeness/no-extra cross-check
    against file_hashes and group_ids that this assignment alone does
    not guarantee (it trusts `groups` came from compute_groups over the
    same records that produced file_hashes).

    Does not itself validate the resulting document against the I-20
    schema -- call tools.dataset.manifest.validate_manifest for that, and
    verify_group_membership (below) for the cross-field invariant schema
    validation alone cannot express.
    """
    document["group_ids"] = sorted(set(groups.values()))
    document["file_group_ids"] = dict(sorted(groups.items()))


def verify_group_membership(document: dict) -> None:
    """Raise ValueError if `document`'s file_group_ids does not exactly
    match its file_hashes identifiers and its group_ids values, in both
    directions.

    This is the proof -- from the manifest's own committed fields alone,
    with no private or non-committed metadata to recompute from -- that
    every file recorded in file_hashes resolves to exactly one group
    (complete: no file_hashes identifier is missing from file_group_ids;
    no-extra: no file_group_ids identifier is absent from file_hashes),
    and that group_ids contains exactly the groups actually referenced
    (no undeclared group_id is used, and no declared group_id goes
    unused). WP-10.4's split construction depends on this guarantee
    holding before it ever runs.
    """
    file_identifiers = set(document.get("file_hashes", {}))
    membership_identifiers = set(document.get("file_group_ids", {}))
    missing = file_identifiers - membership_identifiers
    unexpected = membership_identifiers - file_identifiers
    if missing or unexpected:
        raise ValueError(
            "file_group_ids does not exactly match file_hashes identifiers: "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )

    declared_group_ids = set(document.get("group_ids", []))
    referenced_group_ids = set(document.get("file_group_ids", {}).values())
    undeclared = referenced_group_ids - declared_group_ids
    unused = declared_group_ids - referenced_group_ids
    if undeclared or unused:
        raise ValueError(
            "group_ids does not exactly match the group_ids referenced by file_group_ids: "
            f"undeclared={sorted(undeclared)}, unused={sorted(unused)}"
        )
