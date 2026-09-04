# Generated File Policy

The files under `docs/architecture/dependency-graph/` are committed, generated, sanitized architecture-support artifacts. Their metadata, hashes, and deterministic ordering must pass `tools/graphify/verify_graph.py`. Raw `graphify-out/` remains local and untracked. The dependency graph supports code review and knowledge transfer; it is not scientific evidence or architectural authority.

Generated files must identify their source schema, generator version, and deterministic command. Reviewers must reproduce generated output and reject unexplained drift. Architecture Revision 3 source documents are immutable imported records, not generated repository output.
