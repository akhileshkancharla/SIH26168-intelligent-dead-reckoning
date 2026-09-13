# Candidate schema inventory (WP-10.2)

The accepted `SIH26168_IO_VNBD_Dataset_Feasibility_Audit_v1.1` is named in
`docs/architecture/SIH26168_ARCHITECTURE_MANIFEST_v1.json`, but is not shipped.
The six identifiers must be transcribed from that audit or ratified by the owner
against a replacement inventory. Public source descriptions are supporting
evidence only: https://github.com/onyekpeu/IO-VNBD and
https://pmc.ncbi.nlm.nih.gov/articles/PMC7907232/ .

Run the following only in an approved private workspace, using reviewed units
in exact header order and a pinned source revision. The illustrative units below
are synthetic, not an IO-VNBD schema:

```text
python -m tools.dataset.schema_inventory PRIVATE_FILE --delimiter , --units-json '["s","m/s^2"]' --timestamp-semantics "elapsed seconds; synthetic example" --source-revision SYNTHETIC_REVISION
```

The tool reads the first CSV record and emits ordered columns, explicit units,
delimiter, declared timestamp semantics and a deterministic SHA-256 fingerprint.
It does not infer clock synchronization, validate data rows, calculate archive
hashes, download datasets, or activate the allowlist. File paths and data rows
are excluded from its output. Headers and operator-supplied metadata can still
be sensitive: keep the output private until sanitized and reviewed. Errors may
include local paths; do not publish unreviewed command logs.

Collect candidate descriptors for every file in the approved private revision;
group identical fingerprints and reconcile all differences with S0 evidence.
Do not force the observed count to six. Record archive/file hashes separately
in the existing private I-20 manifest pipeline. Confirm units and timestamp
semantics independently, then have the owner approve the six exact identifiers
and their mapping to fingerprints. Commit only reviewed structural evidence.

After approval, populate `config/io_vnbd_schema_allowlist.json`, set ACTIVE,
and add exact shipped-value tests including unknown-schema refusal. Until then,
the existing template remains inactive. Synthetic inventory tests run in the
normal dataset test suite; no real dataset belongs in CI.
