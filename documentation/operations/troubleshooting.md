# Troubleshooting

Common problems and concrete fixes. When in doubt, start from a clean virtual
environment and a clean `_state/` directory.

## Import errors

Symptom: `ModuleNotFoundError` for `jarvis` or a dependency.

Fix: confirm the environment is active and the package is installed editable with
dev extras:

```bash
source .venv/bin/activate
pip install -e '.[dev]'
python -c "import jarvis; print('ok')"
```

## `_state/` pollution

Symptom: stale or conflicting ledger records cause replay mismatches or
integrity failures.

Fix: the directory is ephemeral working data. Reset it:

```bash
rm -rf _state/
```

Records are recreated on the next run. Never commit `_state/`.

## Non-deterministic replay

Symptom: replay reports `deterministic: false` or benchmark checksums differ
between identical runs.

Fix: remove wall-clock and unordered-iteration leaks. Time must be injected
(`StepClock`, or a passed-in `now`), and serialized keys must be sorted before
hashing. Full diagnosis is in `documentation/operations/running-replay.md`.

## Disk full from `_state/`

Symptom: writes fail with `No space left on device`.

Fix: ledgers are append-only and grow over time. Clean history you no longer
need:

```bash
rm -rf _state/
```

Then re-run only the layers whose history you must retain.

## Failing forbidden-import scan

Symptom: a security or compliance test fails claiming a forbidden import.

Fix: the research OS must never import trading, ordering, deployment, or
allocation paths. Live execution is disabled by default
(`live_execution_enabled()` is `False`). Remove the offending import; do not
weaken the test. See `documentation/operations/configuration.md`.

## Broken documentation links or format

Symptom: `python -m jarvis.documentation validate` reports errors.

Fix: ensure each file's first line is a single H1, all code fences are balanced,
and cross-file references use inline code (for example
`documentation/operations/installation.md`) rather than relative Markdown links.
Regenerate with `python -m jarvis.documentation gen` and validate again.
