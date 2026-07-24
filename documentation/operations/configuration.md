# Configuration

The Autonomous Quant Research OS is configured through environment variables and
a shared state directory. Defaults are chosen so the system stays in a
research-only, non-trading posture with no manual tuning.

## Environment variables

- `JARVIS_AUTONOMY_LEVEL` — integer autonomy level. Default is `5`.
- `.env` files are supported via `python-dotenv`; process environment always wins.

Load a local `.env` by placing it at the repository root. Values there are read
at startup and can be overridden by real environment variables.

## The live execution boundary

Live execution is gated in earlier layers, not in the research OS itself. The
gate is `jarvis.config.live_execution_enabled()`:

```python
from jarvis.config import live_execution_enabled
# Returns AUTONOMY_LEVEL >= MIN_LIVE_LEVEL
```

The constant `MIN_LIVE_LEVEL = 6`, while the default `AUTONOMY_LEVEL = 5`
(sourced from `JARVIS_AUTONOMY_LEVEL`). Because `5 < 6`, live execution is
DISABLED by default. The research, analysis, and recording layers never raise the
level and never enable live execution. Reports are non-binding and VALIDATED
never means deployed.

To confirm the boundary on your machine:

```python
from jarvis import config
assert config.live_execution_enabled() is False
```

## The state directory

All ledgers resolve their path through `jarvis.config.state_path(name)`:

```python
from jarvis.config import state_path
ledger = state_path("research_manager")
```

This returns a path under the shared `_state/` directory. Ledgers are
append-only and SHA256 hash-chained, so each record commits to the previous one.
Treat `_state/` as ephemeral working data; deleting it resets local history.

## Determinism

Identifiers, checksums, and report contents must not depend on wall-clock time.
Time is injected explicitly (for example a `StepClock` or a passed-in `now`), so
repeated runs produce byte-identical output. Never introduce `time.time()` or
`datetime.now()` into ID or checksum construction — doing so breaks replay
verification described in `documentation/operations/running-replay.md`.
