# Audited schema inventory (WP-10.2)

The active allowlist was transcribed from the accepted
`SIH26168_IO_VNBD_Dataset_Feasibility_Audit_v1.1` and its 144-row schema
register. The audited upstream revision is
`118939602e3422d47b8ab0807b623751c3ac135b`.

| Schema identifier | Ordered column count |
| --- | ---: |
| `S18_NO_MAG_ORIENTATION` | 18 |
| `S24_XYZ` | 24 |
| `S24_XYZ_MALFORMED_DATE` | 24 |
| `S24_YPR` | 24 |
| `S24_YPR_TRAILING_EMPTY` | 25 |
| `V29_MAIN` | 29 |

Sanitized evidence hashes:

- audit Markdown: `8F16194BA3E0BC0B521B6E240C98B93D4AC9CD0DEDA9A24455172F915C55A742`
- schema register CSV: `774964395A57CBDA87EBF0A60E32F63CF1DA6DBCF3C6E5D9C6B99D5EA0B2DF87`
- audit manifest JSON: `838B4CB4766DE1B0CE2E135432B5D765A2FB90B63448F7DEA629C2D4A31DCD1A`

The audit decision remains `S0-BLOCKED` for dataset rights. Architecture
Revision 3 permits organizer-directed conditional private competition use, but
activating this structural allowlist does not claim unrestricted licensing or
an S0 pass. Raw archives, data rows, source paths, and private inventory output
remain outside Git.

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

The checked-in allowlist is now `ACTIVE`, with exact-value and unknown-schema
refusal tests in the normal dataset test suite. No real dataset belongs in CI.
