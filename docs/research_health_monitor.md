# Research Health Monitor (P81)

> Deterministic operational metrics derived from existing ledgers. Read-only, no new store.

## What it does — `jarvis/research_workflow/health_monitor.py` + `/console/research-health`
Computes, deterministically:
- **Active Research** (open loops), **Waiting Human Review** (workflow runs past DECISION w/o
  HUMAN), **Validation Missing / Incomplete Research** (ring_ INCOMPLETE), **Knowledge Growth**
  (lessons+successes+memories), **Failure Distribution** (reused failure_intelligence),
  **Research Velocity** (activity proxy),
- **Coverage** — validation / portfolio / risk / memory (0..1),
- **Overall Health Score** (0–100, weighted) + band (HEALTHY/FAIR/ATTENTION) + trend.

## Reuse & no-duplication
Reads existing ledgers and `research_assistant.failure_intelligence`; adds no store, no engine.
Surfaced in the Cockpit's health panel (coverage meters + velocity + incomplete).

## Validation
`test_integration_p78_85.py`: score in [0,100], band valid, knowledge growth, coverage keys,
determinism. Endpoint shape test.

## Files
`jarvis/research_workflow/health_monitor.py`, `console_api.py`, Cockpit page, this doc.
