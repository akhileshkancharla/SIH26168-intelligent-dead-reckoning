#!/usr/bin/env python3
"""WP-10.4 (Issue #82): leakage-safe grouped dataset splits.

Builds on WP-10.3's group_ids (tools/dataset/grouping.py): a split is
assigned per *group*, never per file, so a session/duplicate group can
never straddle train/validation/test -- the exact leakage C-15's "zero
overlap between train/validation/test journey groups" validation rule
exists to prevent.

Assignment is by a stable hash of each group_id into one of the three
split buckets, weighted by the configured ratios (a form of consistent
hashing): the split a given group_id lands in depends only on that
group_id and the configured ratios, never on which other groups are
present, on processing order, or on wall-clock/randomness. This means
adding new groups to a growing dataset never reshuffles the split
assignment of groups already recorded in a previously-committed
DatasetManifest -- an important property given I-20's "Immutable files
and group assignments" sequence/ordering rule.

Because assignment is per-group rather than per-file, and because real
dataset sizes are typically small enough that hash-based bucketing does
not perfectly match target ratios, the resulting split sizes are only
approximately proportional to the configured ratios -- this is an
inherent, expected property of grouped/journey-safe splitting, not a bug.
"""
from __future__ import annotations

import hashlib
from typing import Dict, Iterable, List

DEFAULT_SPLIT_RATIOS: Dict[str, float] = {"train": 0.7, "validation": 0.15, "test": 0.15}
SPLIT_NAMES = ("train", "validation", "test")

_RATIO_SUM_TOLERANCE = 1e-9


class SplitError(Exception):
    """Raised for any split configuration or integrity failure."""


def _validate_ratios(ratios: Dict[str, float]) -> None:
    if set(ratios) != set(SPLIT_NAMES):
        raise SplitError(f"split ratios must cover exactly {SPLIT_NAMES}, got {sorted(ratios)}")
    for name, value in ratios.items():
        if value < 0:
            raise SplitError(f"split ratio for {name!r} must be non-negative, got {value}")
    total = sum(ratios.values())
    if abs(total - 1.0) > _RATIO_SUM_TOLERANCE:
        raise SplitError(f"split ratios must sum to 1.0, got {total}")


def _stable_unit_interval_position(group_id: str) -> float:
    """Map `group_id` deterministically onto [0, 1).

    Uses the full SHA-256 digest of the group_id (not Python's salted
    `hash()`, which is randomized per-process and would make assignment
    non-reproducible across runs/machines).
    """
    digest_int = int(hashlib.sha256(group_id.encode("utf-8")).hexdigest(), 16)
    modulus = 1 << 256
    return digest_int / modulus


def assign_splits(group_ids: Iterable[str], ratios: Dict[str, float] = DEFAULT_SPLIT_RATIOS) -> Dict[str, List[str]]:
    """Deterministically partition `group_ids` into train/validation/test.

    Raises SplitError if `ratios` is malformed, or if `group_ids` contains
    a duplicate (a group_id must be assigned exactly once -- a caller
    passing the same group_id twice is a bug upstream, not something to
    silently deduplicate here).
    """
    _validate_ratios(ratios)

    ordered_group_ids = list(group_ids)
    if len(set(ordered_group_ids)) != len(ordered_group_ids):
        raise SplitError("assign_splits received a duplicate group_id; each group_id must be assigned exactly once")

    # Cumulative boundaries in a fixed name order, so the same ratios
    # always produce the same bucket edges regardless of dict ordering.
    boundaries: List[tuple[str, float, float]] = []
    lower = 0.0
    for name in SPLIT_NAMES:
        upper = lower + ratios[name]
        boundaries.append((name, lower, upper))
        lower = upper

    result: Dict[str, List[str]] = {name: [] for name in SPLIT_NAMES}
    for group_id in ordered_group_ids:
        position = _stable_unit_interval_position(group_id)
        for name, lower_bound, upper_bound in boundaries:
            is_last = name == boundaries[-1][0]
            if lower_bound <= position < upper_bound or (is_last and position == upper_bound):
                result[name].append(group_id)
                break
        else:  # pragma: no cover - defensive; boundaries always cover [0, 1]
            raise SplitError(f"group_id {group_id!r} did not fall into any split bucket")

    for name in result:
        result[name].sort()
    return result


def _reject_unexpected_split_keys(splits: Dict[str, List[str]]) -> None:
    """Raise SplitError if `splits` has any top-level key besides SPLIT_NAMES.

    validate_splits_are_disjoint/validate_splits_cover_groups previously
    only ever read `splits.get(split_name, [])` for the three known
    names, so an externally-constructed or hand-edited splits dictionary
    carrying an extra key (e.g. a stray "holdout" bucket) had its
    group_ids silently ignored by both checks -- and by
    apply_splits_to_manifest, which would then discard that bucket's
    group assignments entirely without anyone being told. Any key
    outside SPLIT_NAMES is exactly as untrustworthy as a missing one: it
    must fail closed, not be quietly dropped.
    """
    unexpected_keys = set(splits) - set(SPLIT_NAMES)
    if unexpected_keys:
        raise SplitError(
            f"splits dictionary has unexpected key(s) outside {SPLIT_NAMES}: "
            f"{sorted(unexpected_keys)}; quarantine and stop the experiment"
        )


def validate_splits_are_disjoint(splits: Dict[str, List[str]]) -> None:
    """Raise SplitError if any group_id appears in more than one split, or
    if `splits` carries a key outside train/validation/test.

    A defensive check for externally-constructed or hand-edited splits
    dictionaries -- assign_splits cannot itself produce an overlapping or
    extra-keyed result, but a manifest loaded from disk or edited by
    another tool might.
    """
    _reject_unexpected_split_keys(splits)
    seen: Dict[str, str] = {}
    for split_name in SPLIT_NAMES:
        for group_id in splits.get(split_name, []):
            prior = seen.get(group_id)
            if prior is not None:
                raise SplitError(
                    f"group_id {group_id!r} appears in both {prior!r} and {split_name!r} splits; "
                    "quarantine and stop the experiment"
                )
            seen[group_id] = split_name


def validate_splits_cover_groups(group_ids: Iterable[str], splits: Dict[str, List[str]]) -> None:
    """Raise SplitError if `splits` and `group_ids` disagree on membership.

    Every group_id must appear in exactly one split, and no split may
    reference a group_id that was not supplied -- this is the "closure"
    check that a splits dict is complete and self-consistent, independent
    of validate_splits_are_disjoint.
    """
    validate_splits_are_disjoint(splits)
    expected = set(group_ids)
    actual = {group_id for split_name in SPLIT_NAMES for group_id in splits.get(split_name, [])}
    missing = expected - actual
    unexpected = actual - expected
    if missing or unexpected:
        raise SplitError(
            "splits do not exactly cover the supplied group_ids: "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )


def apply_splits_to_manifest(document: dict, splits: Dict[str, List[str]]) -> None:
    """Set `document["splits"]` from `splits`, mutating in place.

    Raises SplitError (via _reject_unexpected_split_keys) if `splits` has
    a key outside train/validation/test -- otherwise this function would
    silently write only the three known buckets and discard any other
    key's group assignments without telling the caller. Does not
    otherwise validate the resulting document -- call
    tools.dataset.manifest.validate_manifest afterward.
    """
    _reject_unexpected_split_keys(splits)
    document["splits"] = {name: sorted(splits.get(name, [])) for name in SPLIT_NAMES}
