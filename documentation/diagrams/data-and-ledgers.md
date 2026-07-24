# Diagram — Entity Relationships, Ledgers & Knowledge Graph

## Ledger record & hash chain (entity relationships)

```mermaid
erDiagram
  LEDGER ||--o{ RECORD : contains
  RECORD ||--|| RECORD : "previous_hash → record_hash"
  RECORD {
    string id_field "TAG:sha1[:12]"
    string input_hash "sha256"
    string previous_hash "sha256 or GENESIS"
    string record_hash "sha256 = content_hash(record)"
  }
  RECORD ||--o{ ARTIFACT : "parent_artifact (lineage)"
```

## Ledger relationships (read-only cross-layer)

```mermaid
flowchart LR
  RMGR[("rmgr_* research_manager")]
  RCTL[("rctl_* research_control")]
  AROS[("aros_* autonomous_research_os")]
  RMGR -. read .-> AROS
  RCTL -. read .-> AROS
  AROS --> SNAP["deterministic snapshot (is_binding=false)"]
```

## Knowledge graph & lineage

```mermaid
flowchart TB
  P["plan / experiment"] --> T1["task / artifact A"]
  P --> T2["task / artifact B"]
  T1 --> C["artifact C (parent = A)"]
  T2 --> C
  C -. traversal: ancestors / topo-order / cycle-check .-> Q["deterministic queries"]
```

## Notes

Provenance lives in the ledgers themselves via `parent_artifact` links; `jarvis.integrity`
verifies chains and lineage, and `jarvis.diagnostics` flags broken lineage. See
`documentation/architecture/ledger-ownership-map.md` and
`documentation/adr/0007-knowledge-graph.md`.
