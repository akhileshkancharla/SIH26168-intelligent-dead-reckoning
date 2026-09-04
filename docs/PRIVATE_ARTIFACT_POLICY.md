# Private Artifact Policy

Raw machine-specific Graphify output is excluded from Git. A dependency-graph snapshot may be committed only after repository-relative path normalization, secret/private-data scanning, deterministic ordering, metadata validation, and checksum verification.

Raw IO-VNBD bytes or extracts, raw S1 recordings, exact routes, private analyzer evidence, PBF files, private SQLite graphs, device identifiers, credentials, signing keys, and unapproved weights must remain outside Git and CI. Only synthetic fixtures and hash-only references may enter the repository after review.
