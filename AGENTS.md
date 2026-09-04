# Repository Agent Instructions

## Graphify knowledge-transfer workflow

1. Read `docs/architecture/START_HERE.md` before implementation changes.
2. Inspect the relevant Architecture Revision 3 components and I-01 through I-22 interfaces.
3. Inspect `docs/architecture/dependency-graph/GRAPH_REPORT.md` and the sanitized `graph.json` snapshot.
4. Query or traverse relevant upstream and downstream dependencies before editing an important module.
5. Inspect the actual source, tests, manifests, resources, and build configuration before drawing conclusions.
6. Never use Graphify alone as proof that code is unused.
7. Account for JNI symbols, Android callbacks and manifests, reflection, generated code, dependency injection, resources, and serialized contracts that static extraction can miss.
8. Regenerate the sanitized graph after meaningful architectural or multi-file changes. Isolated spelling or comment-only changes do not require regeneration.
9. Never commit raw `graphify-out/`; commit only the verified sanitized snapshot.
10. Architecture Revision 3 overrides generic Graphify inference.
11. S2 C-07 remains the sole owner of navigation state, operational biases, covariance, and evidence acceptance.
12. ML and map components produce bounded proposals and cannot directly overwrite the navigation core.

Before deleting code or performing a major refactor, combine graph traversal with text search, Android manifest and Gradle inspection, native/JNI symbol inspection, configuration and schema inspection, build/test evidence, and runtime-entry-point reasoning.
