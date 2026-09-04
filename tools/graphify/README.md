# Portable Graphify Workflow

This tooling keeps Graphify's raw machine-local output separate from the sanitized snapshot reviewed in Git.

## Configured tool

- Product: Graphify
- Python package: `graphifyy`
- Required version: `0.9.53`
- Existing raw graph update: `graphify update .`
- First raw graph bootstrap: `graphify extract . --code-only`
- Report/community refresh: `graphify cluster-only . --no-label`

The repository does not install Graphify or modify system configuration. Provision the exact configured version through the team's approved tool environment. The wrappers fail if the executable or exact package version cannot be identified.

## Run locally

From the repository root:

```powershell
tools/graphify/update_graph.ps1
```

If local policy requires signed scripts, invoke the checked-in file for this process only with `powershell -NoProfile -ExecutionPolicy Bypass -File tools/graphify/update_graph.ps1`. This does not change machine-wide execution policy.

If Graphify and Python are not on `PATH`, pass their executable names or paths as script parameters. The values are runtime inputs and are never written into the shared snapshot.

On Unix:

```sh
tools/graphify/update_graph.sh
```

The Unix wrapper uses the same Graphify commands and standard-library Python sanitizer. Override executable lookup with `GRAPHIFY_BIN` and `PYTHON_BIN` when required.

Both wrappers:

1. derive and validate the repository root;
2. validate the expected origin;
3. identify and enforce the exact Graphify version;
4. update or bootstrap ignored raw output;
5. refresh clustering and the raw report;
6. generate the deterministic sanitized snapshot;
7. verify paths, secrets, structure, metadata, ordering, and hashes;
8. print a concise Git change summary.

## CI mode

CI is `snapshot-validation-only`. It runs the deterministic sanitizer/verifier tests, verifies the committed snapshot, and runs the integrated repository policy without installing Graphify.

Full CI regeneration is deferred until the project has an approved, hash-locked transitive Graphify dependency set and licence inventory. This limitation is not represented as successful regeneration.

The committed dependency snapshot and bootstrap repository manifest are excluded from Graphify extraction to prevent a recursive generated-artifact/hash cycle.

## Maintenance boundary

Regenerate after meaningful architecture or multi-file changes affecting:

- `android/**`
- `core/**`
- `contracts/**`
- `tools/analyzer/**`
- `tools/dataset/**`
- `tools/training/**`
- `tools/maps/**`
- root CMake configuration
- Gradle build/settings files
- Android manifests
- native/JNI build configuration

Spelling-only documentation changes, issue templates, non-architectural comments, and purely presentational README corrections normally do not require regeneration.

Never use the graph alone to delete code. First combine graph traversal with text search, Android manifest and Gradle inspection, native/JNI symbol inspection, configuration/schema inspection, build/test evidence, and runtime-entry-point reasoning.
