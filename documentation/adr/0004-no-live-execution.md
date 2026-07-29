# ADR 0004 — No Live Execution (by Default)

## Status

Accepted.

## Context

The underlying platform *can* place live orders through its execution boundary
(`jarvis.live_execution`, `jarvis.execution`). Autonomous research must never flip that switch,
and even the platform's own live path must default to off and require explicit human arming.

## Decision

Live execution is gated by a single configuration function,
`jarvis.config.live_execution_enabled()`, which returns `AUTONOMY_LEVEL >= MIN_LIVE_LEVEL`.
`MIN_LIVE_LEVEL = 6` and the default `AUTONOMY_LEVEL = 5` (overridable only via the
`JARVIS_AUTONOMY_LEVEL` environment variable). Therefore **live execution is disabled by
default**. The research OS layers never read or modify this gate and never call the execution
boundary.

## Consequences

- **Fail-safe default:** with no configuration, the system cannot execute; it can only research
  and record.
- **Explicit, auditable enablement:** raising autonomy is an out-of-band, human, environment-level
  action — never something a research layer performs.
- **Regression guard:** the compliance security checklist asserts `live_execution_enabled == False`
  and that `AUTONOMY_LEVEL` is unchanged by any additive phase.
- **Separation of concerns:** research produces advisory records; a human/gated process decides
  whether to act, keeping the dangerous capability behind an explicit boundary.
