# I-18 legacy S1 manifest mapping

This owner-approved compatibility rule is intentionally strict. It permits the validated S1
writer artifact to migrate to `session_manifest_v1` without inventing evidence.

| Legacy S1 field | I-18 field | Rule |
|---|---|---|
| `complete: true` | `status: COMPLETE` | Permitted only when every other I-18 mandatory field is present and every chunk verifies. |
| `complete: false` | `status: INCOMPLETE` | Diagnostic-only; never eligible for normal replay. |
| ordered legacy chunk array | `chunks` | Preserve array order exactly. Copy relative path, byte size and lowercase SHA-256 only when present and verified. |

There are no defaults for `clock_id`, `boot_id`, `app_build`, `device_profile`, `streams`,
`loss_counts`, `config_hash` or `privacy_class`. These values must come from authenticated writer,
build and session metadata. A legacy manifest missing any mandatory value is classified
`LEGACY_METADATA_INCOMPLETE`, quarantined for diagnostic inspection, and rejected from normal
replay. Readers must not derive identifiers from local paths, infer clock domains, synthesize
zero loss, invent device/build identity, repair chunk order or upgrade `INCOMPLETE` to `COMPLETE`.

Normal replay eligibility requires all of the following:

1. the manifest validates against `contracts/schemas/session_manifest_v1.schema.json`;
2. `status` is `COMPLETE`;
3. every chunk path is relative and resolves inside the selected session root;
4. every declared file exists and its exact byte size and SHA-256 match;
5. stream identifiers, clock identifiers, sequence ranges and chunk order pass reader checks; and
6. no undeclared file or missing mandatory metadata is silently accepted.

`INCOMPLETE` and `EVIDENCE_DEGRADED` manifests may be inspected only through an explicitly
diagnostic path that keeps their status visible. They are never ordinary replay inputs.
