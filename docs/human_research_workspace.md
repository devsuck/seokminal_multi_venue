# Human Research Workspace (P146)

> Integration only — the human researcher's control center. **No investment approval, no trade execution.** Read-only.
> (Distinct from P80's `research_workspace.md` "AI Research Workspace".)

## What it does — `jarvis/research_workflow/research_workspace.py`
`build_workspace()` assembles: Research Inbox + Review Queue (from `ops_events`, P107), Agent Outputs (from
`agent_capability`, P121), Follow-up Tasks, and Research History (from `timeline`, P78).

`act(action, target, comment)` performs a **non-binding** action — `review / comment / request_revision /
archive`. comment/request_revision/archive record an advisory note via `record_advisory` (ras_notes,
`is_binding=False`); review just marks. **Forbidden actions**: approve_investment, execute_trade,
allocate_capital.

## Reuse & no-duplication
ops_events + agent_capability + timeline + record_advisory. No new ledger.

## Governance
`is_advisory=True`, `is_decision=False`, `is_binding=False`. No approve/execute.

## Validation
`test_integration_p141_150.py`: four allowed actions, forbidden approve/execute, unknown action rejected.

## Files
`jarvis/research_workflow/research_workspace.py`, `console_api.py` (`/console/research-workspace`), this doc.
