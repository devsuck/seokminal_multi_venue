# Replay Guide

Deterministic replay is a core guarantee of the Autonomous Quant Research OS.
Because the OS only records and analyzes, every recorded artifact must be
reproducible: given the same inputs, a layer must produce byte-identical output
on every run, on every machine.

## What deterministic replay means

Replay re-executes a layer's recording logic over a fixed set of inputs and a
fixed logical `now`, and reproduces exactly the same records it produced before.
This works because:

- IDs are a tag plus a content hash — **no wall-clock time is ever hashed** into an ID.
- Models are frozen dataclasses, so records cannot drift after creation.
- Serialization is canonical (`json.dumps(..., sort_keys=True, ensure_ascii=False, default=str)`).

If any of these were violated, two replays would diverge and the artifact would no
longer be trustworthy.

## The `verify.replay(engine, now)` entry point

Each layer's `verify.py` exposes a replay function that takes an engine and a
logical timestamp and returns the reproduced output:

```python
from jarvis.autonomous_research_pipeline import verify, engine as eng

now = "2026-07-24T00:00:00Z"  # logical, not read from the clock
first = verify.replay(eng.build(), now)
second = verify.replay(eng.build(), now)
assert first == second  # byte-identical
```

Passing `now` explicitly keeps time an **input**, never an ambient side effect.

## Running replay from the CLI

Layers that ship a `__main__.py` expose replay directly:

```bash
python -m jarvis.autonomous_research_pipeline replay
```

The command prints the reproduced records (or a verification summary). Running it
twice must yield identical output.

## Why identical output matters

- **Auditability:** an auditor can re-derive any recorded result from scratch.
- **Integrity:** replay output is cross-checked against the hash-chained ledger, so
  tampering or accidental drift is detectable.
- **Safety:** determinism is what lets us prove the OS is observation-only — nothing
  in a replay depends on live market state, randomness, or the wall clock.

When you add logic to a layer, add a replay test that asserts equality across two
runs. See `documentation/developer_guide/testing-guide.md` for the pattern.
