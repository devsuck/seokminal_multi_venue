# Running Replay

Replay re-executes a layer's recorded decisions against its ledger and confirms
that the output is bit-for-bit reproducible. Deterministic replay is the core
guarantee that recorded research can be audited and trusted.

## Per-layer replay CLI

Each layer exposes a `replay` command through its module entrypoint:

```bash
python -m jarvis.<pkg> replay
```

For example, the research manager:

```bash
python -m jarvis.research_manager replay
```

A successful replay reports:

```bash
deterministic: true
```

## Programmatic replay

Replay can also be driven from Python by passing an engine and an explicit
`now`. Because time is injected rather than read from the wall clock, the same
inputs always yield the same result:

```python
from jarvis.research_manager import verify

result = verify.replay(engine, now)
assert result["deterministic"] is True
```

The injected `now` matters: supply the same timestamp used when the records were
created so identifiers and checksums line up.

## When replay is not deterministic

If replay reports `deterministic: false`, the recorded run and the recomputed run
diverged. Work through these causes in order:

1. Wall-clock leak. Search the layer for `time.time()`, `datetime.now()`, or
   `uuid` generation feeding into IDs or checksums. Time must be injected. See
   `documentation/operations/configuration.md`.
2. Unordered iteration. Dict or set ordering used in serialization can vary;
   sort keys before hashing.
3. Stale or partially written ledger. Inspect `_state/` for a truncated JSONL
   record; a broken hash chain surfaces here too.
4. Floating-point nondeterminism. Confirm numeric routines use fixed dtypes and
   avoid platform-dependent reductions.

After a fix, re-run the layer suite and the replay command to confirm
`deterministic: true` returns.
