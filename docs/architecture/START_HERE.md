# Architecture and Implementation Start Here

Read the repository in this order before implementation work:

1. [`docs/DEVELOPMENT_STATUS.md`](../DEVELOPMENT_STATUS.md)
2. [Architecture Revision 3](SIH26168_High_Level_Architecture_Revision3.md)
3. [Development Design Baseline](SIH26168_Development_Design_Baseline_v1.md)
4. [Interface Inventory](SIH26168_Interface_Inventory_v1.md)
5. [ADR Register](SIH26168_ADR_Register_v1.md)
6. [Sanitized dependency-graph report](dependency-graph/GRAPH_REPORT.md)
7. [Sanitized dependency graph JSON](dependency-graph/graph.json)
8. The current GitHub work-package issue and assignment
9. The relevant module README
10. The relevant source and tests

## Evidence boundaries

- Architecture documents describe the intended design and governing boundaries.
- Executable source and tests describe the current implementation.
- Graphify describes extracted static relationships in a bounded snapshot.
- Work-package state describes assignment and review status.

None of these is, by itself, proof of completed scientific validation. Replay, architecture coverage, static connectivity, passing smoke tests, and issue status must not be represented as navigation accuracy or field evidence.

Architecture Revision 3 is authoritative over inferred graph relationships. In particular, C-07 exclusively owns S2 navigation state, operational biases, covariance, and evidence acceptance. ML and map components remain bounded proposal producers.
