# Dependency Graph Snapshot

This directory contains a generated and sanitized Graphify snapshot for repository knowledge transfer. Raw machine-specific output remains in the ignored `graphify-out/` directory.

## Contents

- `GRAPH_REPORT.md`: bounded human-readable architecture and dependency findings.
- `graph.json`: canonical machine-readable graph with sorted nodes, edges, and object keys.
- `metadata.json`: provenance, tool/configuration identity, counts, and limitations.
- `SHA256SUMS.txt`: hashes for every committed snapshot artifact except the checksum file itself.

`graph.html` is intentionally local-only because deterministic portable HTML has not been established.

## Regeneration

Configured Graphify version: `0.9.53`.

- Windows: `tools/graphify/update_graph.ps1`
- Unix: `tools/graphify/update_graph.sh`
- Verify only: `python tools/graphify/verify_graph.py`

The wrappers do not install Graphify. They fail unless the configured version can be identified exactly. See [`tools/graphify/README.md`](../../../tools/graphify/README.md) for environment details.

## Maintenance policy

Regenerate after meaningful architectural or multi-file changes affecting Android, the C++ core, contracts, analyzer, dataset, training, maps, root CMake, Gradle settings/build files, Android manifests, or native/JNI build configuration.

Regeneration is generally unnecessary for spelling-only documentation changes, issue templates, non-architectural comments, or purely presentational README corrections.

Before deletion or major refactoring, combine graph traversal with text search, Android manifest and Gradle inspection, native/JNI symbol inspection, configuration/schema inspection, build and test evidence, and runtime-entry-point reasoning.

## Evidence boundary

Graphify is supporting static evidence, not architectural authority or scientific evidence. Architecture Revision 3 controls interpretation.

CI mode: `snapshot-validation-only`. CI validates the committed snapshot and deterministic tooling tests; it does not install or execute Graphify.
