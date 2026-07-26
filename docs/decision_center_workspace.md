# Human Decision Center — Workspace (P165)

> Integration only — the central human workspace over the committee packet.
> **Forbidden: approve_trade, execute, allocate.** Read-only except non-binding comments/actions.
> (P165 module `human_decision_center.py`; builds on the existing P93 `decision_center.py`. This doc is
> distinct from P93's `human_decision_center.md` to preserve it.)

## What it does — `jarvis/research_workflow/human_decision_center.py`
`build_decision_center(question)` assembles: Committee Packet (P161), Comments, Decision Log + Review History
(from the existing `rwf_runs` audit), Follow-up Research + Review Queue (`ops_events`, P107), and Research
Archive (`timeline`, P78).

`act(action, target, comment)` allows only `review / comment / request_followup / archive` — all non-binding
(recorded via `record_advisory` → ras_notes). **`approve_trade`, `execute`, `allocate` are explicitly rejected.**
Human decisions are recorded only through `decision_center.record_decision` (reviewer required).

## Reuse & no-duplication
investment_committee + decision_center.record_decision + ops_events + timeline + record_advisory. No new store.

## Governance
`is_advisory=True`, `is_decision=False`, `is_binding=False`. No approve/execute/allocate.

## Validation
`test_integration_p161_170.py`: four allowed actions, forbidden approve_trade/allocate rejected.

## Files
`jarvis/research_workflow/human_decision_center.py`, `console_api.py` (`/console/decision-center`), this doc.
