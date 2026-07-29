# Architecture Overview

The Autonomous Quant Research OS is a stack of **additive, research-only** layers under the
`jarvis/` Python package (111 subpackages). Each layer owns append-only, hash-chained JSONL
ledgers and exposes a deterministic, event-sourced engine plus (usually) a CLI. Higher layers
observe lower layers **read-only**. Nothing in the research stack executes trades.

## Design pillars

1. **Additive-only evolution.** A new phase adds packages; it never edits, renames, or deletes
   existing files, and never changes ledger schemas, public APIs, or ownership.
2. **Append-only, hash-chained ledgers.** Truth is a JSONL file. Each record links to the
   previous via `previous_hash` and seals itself with `record_hash = content_hash(record)`.
   `content_hash` excludes `{previous_hash, record_hash, report_hash}`.
3. **Event-sourced lifecycles.** State is derived by replaying events; transitions are guarded
   by an `ALLOWED_TRANSITIONS` map and `can_transition(frm, to)`.
4. **Determinism.** IDs are `tag + sha1(input_digest(...))[:12]` — no wall-clock. Replays
   produce byte-identical output.
5. **Read-only upstream.** A layer reads another layer's ledger files but never writes them —
   no import coupling to mutate state.
6. **Research / analysis / recording only.** No order, trade, broker, deploy, allocate,
   promote, or permission-mutation capability. Reports carry `is_binding=False`.

## Layer families

- **Execution platform boundary (P1–P8, pre-existing).** Includes `live_execution`, `execution`,
  `execution_control`, `permissions`. Live execution is human-gated and disabled by default
  (`live_execution_enabled()` requires `AUTONOMY_LEVEL >= 6`; default is 5).
- **Research & governance (P9–P11).** Research data, governance, memory, knowledge, and
  intelligence layers.
- **Autonomous research infrastructure (P12).** Pipeline, scheduler, coordinator, adaptive loop,
  evaluation, optimization, experience/memory, learning, manager, control plane.
- **Research OS (P13).** `autonomous_research_os` integrates every layer read-only, builds
  knowledge views and deterministic system snapshots.
- **Production hardening (P14).** `benchmark`, `cache`, `concurrency`, `resilience`, `profiling`,
  `diagnostics`.
- **Security & compliance (P15).** `security`, `compliance`, `integrity`, `sbom`, `dependency`,
  `license`, `threat_model`.
- **Documentation (P16).** `documentation` — validation + API generation tooling and this tree.

## Anatomy of a layer

A typical layer package contains:

```text
jarvis/<layer>/
  __init__.py     # public exports
  models.py       # frozen dataclasses, IDs, hashing, ALLOWED_TRANSITIONS
  ledger.py       # append-only ledger accessors (state_path based)
  engine.py       # deterministic, event-sourced engine
  verify.py       # chain/tamper/lifecycle/replay verification
  __main__.py     # argparse CLI (python -m jarvis.<layer>)
  tests/          # isolated pytest suite (_iso monkeypatch fixture)
```

## Where to go next

- Layer-by-layer detail: `documentation/architecture/layers.md`
- Ownership & read-only rules: `documentation/architecture/ownership-boundaries.md` and
  `documentation/architecture/read-only-boundaries.md`
- Ledger inventory: `documentation/architecture/ledger-ownership-map.md`
- Visual models: `documentation/diagrams/system-architecture.md`
