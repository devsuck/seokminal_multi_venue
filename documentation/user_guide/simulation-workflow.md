# Simulation Workflow

This guide explains how deterministic simulation and replay-style evaluation are
recorded and re-verified in the Autonomous Quant Research OS. Simulations
produce deterministic outputs with stable checksums; there are never any live
orders. All results land in the append-only, hash-chained ledger at
`jarvis.config.state_path`.

## Determinism first

A simulation is reproducible by construction: given the same inputs and the same
deterministic IDs, a replay yields byte-identical outputs and therefore an
identical checksum. This is what makes evaluation results trustworthy as records.

```text
inputs (fixed) -> deterministic run -> output artifact -> SHA256 checksum
                                        ^                    |
                                        +---- replay --------+  (must match)
```

## 1. Record a simulation run

Evaluation is driven through `jarvis.autonomous_research_evaluation`, which the
research pipeline invokes as part of a cycle. The run is recorded as an artifact
with a deterministic ID.

```bash
python -m jarvis.autonomous_research_pipeline run --plan PLAN-3 --commit
```

Omitting `--commit` performs a dry-run: the simulation still computes its output
and checksum, but nothing is appended to the ledger.

## 2. Inspect the deterministic output

```python
import hashlib

def checksum(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()

# the same payload always yields the same digest
first = checksum(b"equity_curve,metrics,verdict")
second = checksum(b"equity_curve,metrics,verdict")
assert first == second   # deterministic
```

## 3. Re-verify a prior run

Because the ledger is hash-chained, re-verification confirms both that the run
was recorded honestly and that a replay reproduces it.

```bash
python -m jarvis.research_control verify
python -m jarvis.research_manager replay PLAN-3
```

## Guarantees

- No live orders, no venue connectivity, no allocation.
- Every simulation output has a stable SHA256 checksum.
- A replay that does not match the recorded checksum signals tampering or a
  non-deterministic input, which is treated as a defect to fix.
