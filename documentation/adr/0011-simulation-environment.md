# ADR 0011 — Simulation Environment

## Status

Accepted.

## Context

Strategies must be evaluated before any human considers acting on them. Evaluation must be
deterministic and reproducible, and it must never touch live markets or place orders.

## Decision

Evaluation runs in a **deterministic simulation/replay environment**. Simulation and replay
produce stable outputs fingerprinted by SHA256 checksums; the same inputs always yield the same
result, which can be re-verified later. Simulation outputs are recorded as ordinary hash-chained
artifacts and are validated by `jarvis.integrity` (e.g. `verify_benchmark`, artifact checks).
No live orders are ever placed.

## Consequences

- **Reproducible evaluation:** a result can be recomputed and checksum-matched at any time,
  supporting audit and regression detection.
- **Safety:** simulation is fully offline; it has no path to execution.
- **Regression detection:** `jarvis.benchmark` compares runs to detect performance regressions;
  `jarvis.diagnostics` flags snapshot drift.
- **Boundary preserved:** "validated in simulation" is a recorded verdict, never a deployment
  (ADR 0003).
