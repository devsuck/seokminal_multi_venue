# Data Flow

Data flows **upward** through the stack: lower layers record domain events; higher layers
observe, aggregate, verify, and report. No data flows back down as a mutation.

## The write path (within a layer)

1. A caller invokes an engine method (e.g. `create_research_plan`, `collect_health`).
2. The engine builds a frozen dataclass record with a **deterministic ID**
   (`tag + sha1(input_digest(...))[:12]`) and an `input_hash`.
3. If `commit=True`, the engine seals the record: `previous_hash = head.record_hash` (or
   `GENESIS`), then `record_hash = content_hash(record)`.
4. The sealed record is appended to the layer's own JSONL ledger via `state_path`.

Without `commit=True`, engines run as a **dry-run**: they compute the record and return it but
write nothing. This keeps tests and previews side-effect free.

## The read path (across layers)

1. A higher layer resolves a source file via its `SOURCE_LEDGERS` / `SOURCE_LAYERS` map.
2. It reads the JSONL file (read-only), parsing complete lines into dicts.
3. It aggregates counts, verifies chains, or records an observation **episode** in its own
   ledger — never touching the source.

## End-to-end example

```text
research_manager        →  records plan/task/progress events (rmgr_*)
research_control        →  observes system state, health, anomalies (rctl_*)
autonomous_research_os  →  READ-ONLY connects both, records episodes,
                           builds a knowledge view, emits a deterministic snapshot (aros_*)
integrity / diagnostics →  READ-ONLY verify chains, detect drift, validate artifacts
documentation           →  READ-ONLY introspects packages, validates docs
```

## Determinism guarantees

- IDs never include wall-clock time, so the same logical operation yields the same ID.
- `verify.replay(engine, now)` recomputes a summary/snapshot twice and asserts equality.
- Benchmark and snapshot **checksums** depend only on inputs, not timing.

## Non-binding outputs

Every report/snapshot/view carries `is_binding=False`. Anomaly alerts carry
`is_actionable=False`. These flags make explicit that analysis records are advisory: they are
observations, never instructions to execute. See
`documentation/diagrams/data-and-ledgers.md` for the visual model.
