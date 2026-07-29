# Running Tests

The project uses pytest. Tests are the primary correctness gate and every layer
ships its own suite under `jarvis/<pkg>/tests`.

## Full regression

Run the entire suite before any release or after cross-cutting changes:

```bash
python -m pytest jarvis -q
```

The `-q` flag reduces noise to a single progress line plus a summary. A clean run
ends with a line like `NNN passed`.

## Single-layer runs

When iterating on one layer, run just its suite for a fast feedback loop:

```bash
python -m pytest jarvis/<pkg>/tests -q --no-header --noconftest -p no:cacheprovider
```

Flag by flag:

- `--no-header` — suppress the pytest platform/plugin banner for terse output.
- `--noconftest` — skip `conftest.py` discovery so the layer runs in isolation,
  independent of repo-wide fixtures.
- `-p no:cacheprovider` — disable the cache plugin so no `.pytest_cache`
  artifacts are written; keeps per-layer runs side-effect free.

Replace `<pkg>` with a layer name, for example:

```bash
python -m pytest jarvis/benchmark/tests -q --no-header --noconftest -p no:cacheprovider
```

## Security and forbidden-import scans

Some suites assert compliance invariants — most notably that the research OS
never imports or calls anything that could trade, order, deploy, or allocate.
These forbidden-import scans run as ordinary tests. A failure means new code
crossed the research-only boundary; remove the offending import rather than
weakening the test. Related tooling is described in
`documentation/operations/generating-reports.md`.

## Interpreting counts

- `passed` — assertions held.
- `failed` — a real regression; read the traceback for the failing assertion.
- `skipped` — usually an optional dependency or environment guard.
- `xfailed` / `xpassed` — expected failures and their surprises; investigate any
  `xpassed`.

Non-deterministic failures across identical runs indicate a determinism leak; see
`documentation/operations/running-replay.md` for diagnosis.
