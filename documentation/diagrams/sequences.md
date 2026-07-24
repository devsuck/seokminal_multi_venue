# Diagram — Sequence Diagrams

## Committing a record (write path)

```mermaid
sequenceDiagram
  participant U as Caller / CLI
  participant E as Engine
  participant M as models (hashing)
  participant Lg as ledger (append-only)
  U->>E: verb(..., now, commit=True)
  E->>M: build record + deterministic ID + input_hash
  E->>Lg: read head record
  Lg-->>E: head.record_hash (or GENESIS)
  E->>M: seal (previous_hash, record_hash=content_hash)
  E->>Lg: append sealed record (open "a")
  E-->>U: frozen record (to_dict)
```

## Read-only observation (Research OS)

```mermaid
sequenceDiagram
  participant OS as autonomous_research_os
  participant Src as source ledger (rmgr_/rctl_)
  participant Own as aros_ ledgers
  OS->>Src: read JSONL (SOURCE_LAYERS)
  Src-->>OS: records (count)
  OS->>Own: append episode + view
  OS->>Own: append deterministic snapshot (is_binding=false)
  Note over Src: source bytes unchanged (read-only)
```

## Verification & replay

```mermaid
sequenceDiagram
  participant U as Caller / CLI
  participant V as verify
  participant Lg as ledger
  U->>V: verify_chain()
  V->>Lg: read all records
  V->>V: recompute record_hash, check previous_hash links
  V-->>U: {ok, broken_at, reason}
  U->>V: replay(engine, now)
  V->>V: compute summary twice
  V-->>U: {deterministic: true}
```

## Notes

These sequences apply uniformly across layers because they all share the ledger substrate. See
`documentation/architecture/data-flow.md`.
