# ADR 0001 — Append-Only Ledgers

## Status

Accepted.

## Context

The system records research plans, experiments, evaluations, decisions, health, and
observations. These records must be auditable and must never be silently rewritten. Mutable
storage (in-place updates, deletes) makes tampering and accidental corruption easy and
undermines reproducibility.

## Decision

Every layer persists to **append-only JSONL ledgers**. Records are only ever appended; there is
no update, delete, or overwrite API. Files are addressed through `jarvis.config.state_path(name)`
and opened exclusively in append mode (`open(path, "a")`). State is derived by reading the full
history (event sourcing), not by mutating rows.

## Consequences

- **Auditability:** the complete history is preserved; you can always see how a state was
  reached.
- **Safety:** no code path can erase or rewrite prior records; corruption is additive and
  detectable.
- **Recovery:** if a ledger is truncated or a bad line appended, `jarvis.resilience` recovers
  the valid prefix into a new file without touching the original.
- **Cost:** ledgers grow monotonically; large-ledger diagnostics (`jarvis.diagnostics`) warn
  when a file exceeds a threshold. This is an accepted trade-off for integrity.
- Combined with ADR 0002 (hash chaining), append-only storage yields tamper-evident history.
