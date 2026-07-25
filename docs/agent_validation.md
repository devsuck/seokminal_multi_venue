# Agent System Validation (P130)

> Validation of the research-agent chain. Read-only, deterministic, no execution.

## The chain
`User Research Goal → Director → Specialist Agents → Critic → Report → Human Review`

## What it verifies — `jarvis/research_workflow/agent_validation.py`
`validate_agents()` runs five checks:
1. **agents_use_existing_engines** — every agent's `used_engines` is populated
2. **no_duplicated_intelligence** — ledger stays 3; agents never call the ledger-write primitive directly (AST)
3. **no_autonomous_decisions** — the full chain output is `is_decision=False` + `requires_human_review`
4. **memory_updated_correctly** — writes route to existing rwf_sessions + ras_notes, `commit=False` preview
5. **dashboard_displays_workflow** — the agent workspace surface assembles

`agent_safety()` AST-scans all agent modules: no new database/ledger/engine/memory, analysis only, no
`execute/trade/place_order/allocate/approve`, no broker/exchange.

## Result
All five checks pass; safety clean; ledger stays 3.

## Validation
`test_integration_p121_130.py`: all five checks, safety no-new-ledger.

## Files
`jarvis/research_workflow/agent_validation.py`, `console_api.py` (`/console/agent-validation`), this doc.
