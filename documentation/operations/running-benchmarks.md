# Running Benchmarks

The benchmark layer (P14) produces deterministic performance reports so that
research runs can be compared over time without wall-clock noise. Benchmarks are
measurement only; they never trade or deploy.

## Running a suite

Benchmarks are driven from Python. Use the deterministic `StepClock` so timing is
reproducible:

```python
from jarvis.benchmark import run_suite, StepClock, compare_reports

report = run_suite('label', clock=StepClock())
```

`StepClock` advances by fixed steps instead of reading the system clock, which is
what makes each run byte-identical.

## Checksum stability

Every report carries a `checksum`. Running the same suite with the same
`StepClock` must yield the same checksum:

```python
a = run_suite('label', clock=StepClock())
b = run_suite('label', clock=StepClock())
assert a['checksum'] == b['checksum']
```

A changed checksum for unchanged code means a determinism leak. Diagnose it the
same way as replay drift; see `documentation/operations/running-replay.md`.

## History

Reports append to a hash-chained history so trends are auditable:

```python
from jarvis.benchmark import append_history, read_history

append_history(report)
history = read_history()
```

History persists under the shared `_state/` directory via
`jarvis.config.state_path`, so it is ephemeral working data.

## Detecting regressions

Compare a previous report to the current one to surface changes:

```python
from jarvis.benchmark import compare_reports

diff = compare_reports(prev, cur)
```

Use `compare_reports` in pre-release checks: a meaningful delta between the last
recorded report and a fresh run flags a performance regression for review before
it is accepted into history.
