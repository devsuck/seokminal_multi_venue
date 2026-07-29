# Testing Guide

Testing is the primary safety net for a read-only research OS: it proves that
layers stay additive, deterministic, and non-executing. All tests run under
pytest and are hermetic.

## Test layout

Each layer owns its tests under `jarvis/<layer>/tests/`. A typical suite covers:

- model construction and `to_dict()` round-trips,
- ledger append and hash-chain verification,
- deterministic replay,
- forbidden-import / forbidden-execution AST scans,
- lifecycle transition validity.

## The `_iso` isolation fixture

Tests must never touch the real shared `_state/` directory. Each layer provides an
`_iso(tmp_path, monkeypatch)` fixture that monkeypatches the layer's
`state_path` so ledgers are written into an isolated temp directory:

```python
import pytest
import jarvis.autonomous_research_pipeline.ledger as ledger

@pytest.fixture
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ledger, "state_path",
        lambda name: str(tmp_path / name),
    )
    return tmp_path
```

Use this fixture in any test that appends to a ledger.

## Running tests

Full suite:

```bash
python -m pytest jarvis -q
```

A single layer, isolated from repo-wide conftest and cache for a fast, clean run:

```bash
python -m pytest jarvis/autonomous_research_os/tests -q --no-header --noconftest -p no:cacheprovider
```

## Security and forbidden scans

Each layer includes tests that parse its own source with the `ast` module and
assert that no forbidden import (order routers, deployment tooling, write-capable
brokers) and no forbidden execution primitive (subprocess, socket sends) appears.
These tests are the mechanical enforcement of the additive-only rule.

## Determinism and replay tests

Replay tests build an engine, run `verify.replay(engine, now)` twice with the same
inputs, and assert byte-identical output. Because IDs never embed wall-clock time,
the same inputs always yield the same records. See
`documentation/developer_guide/replay-guide.md`.

## Minimum-count discipline

Some suites assert a **minimum number of tests or records** to guard against
silent test loss during refactors. When you remove or rename tests, update the
minimum-count assertion deliberately rather than lowering it to make a run pass.
