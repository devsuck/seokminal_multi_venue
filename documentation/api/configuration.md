# Configuration

Configuration is centralized in `jarvis.config`. The research OS needs almost none: it reads
ledgers from `_state/` and runs deterministically. The most important settings concern the
**autonomy gate** that keeps live execution off.

## Autonomy gate

```python
# jarvis/config.py (illustrative)
AUTONOMY_LEVEL = int(os.environ.get("JARVIS_AUTONOMY_LEVEL", "5"))
MIN_LIVE_LEVEL = 6

def live_execution_enabled() -> bool:
    return AUTONOMY_LEVEL >= MIN_LIVE_LEVEL
```

| Setting | Default | Meaning |
|---|---|---|
| `JARVIS_AUTONOMY_LEVEL` (env) | `5` | Current autonomy level |
| `MIN_LIVE_LEVEL` | `6` | Minimum level required for live execution |
| `live_execution_enabled()` | `False` | True only when `AUTONOMY_LEVEL >= MIN_LIVE_LEVEL` |

Because the default level (5) is below the minimum (6), **live execution is disabled by
default**. Research OS layers never read or change this gate; raising autonomy is an explicit,
human, environment-level action. See `documentation/adr/0004-no-live-execution.md`.

## Ledger location

Ledgers are written to a shared `_state/` directory resolved by
`jarvis.config.state_path(filename)`. In tests, this function is monkeypatched to a temporary
directory (the `_iso` fixture), so the real `_state/` is never touched.

## Determinism

- Identifiers never embed wall-clock time; a `now` timestamp passed to engines is stored in
  record fields only.
- Serialization uses `sort_keys=True`, so hashing and replay are stable.

## Environment variables (summary)

| Variable | Purpose |
|---|---|
| `JARVIS_AUTONOMY_LEVEL` | Sets the autonomy level (default 5; keep below 6 to disable live execution) |

No configuration is required to run the research, analysis, and documentation tooling. See
`documentation/operations/configuration.md` for the operations perspective.
