# ADR 0006 — Deterministic Replay System

## Status

Accepted.

## Context

Auditability and testing require that the same history always reproduces the same derived state.
Any nondeterminism (wall-clock in IDs, unordered serialization, random iteration) would make
verification and reproduction impossible.

## Decision

The system is **deterministic end to end**:

- Identifiers are `tag + sha1(input_digest(...))[:12]` and never embed wall-clock time.
- Serialization always uses `sort_keys=True` and stable options.
- Each layer exposes `verify.replay(engine, now)`, which recomputes a summary/snapshot twice and
  asserts the two results are identical.
- CLIs expose a `replay` subcommand (`python -m jarvis.<layer> replay`) returning
  `deterministic: true`.

## Consequences

- **Reproducibility:** re-running against the same ledgers yields byte-identical output; caching
  and benchmarking rely on this.
- **Testable determinism:** benchmark and snapshot **checksums** depend only on inputs, so tests
  assert stability across runs and across injected clocks (`StepClock`).
- **Debuggability:** a determinism failure is a real defect (unsorted keys, clock leak) and is
  caught by replay tests immediately.
- **Constraint on new code:** contributors must avoid `Date.now()`-style values in IDs and must
  keep serialization stable; the coding standards enforce this.
