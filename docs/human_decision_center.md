# Human Decision Center (P93)

> Integration only — an investment-committee workspace. Combines thesis, evidence, counter
> arguments, risk, historical similarity, portfolio impact, confidence, and decision history.
> Human input (decision/reason/timestamp) is stored through the **existing audit system**.

## What it does — `jarvis/research_workflow/decision_center.py` + dashboard `committee` page
`committee_packet(question)` composes the P65 decision memo + the P90 seven-perspective council +
P62 risk into one packet, plus **decision history** read from the existing `rwf_runs`
HUMAN_DECISION audit. `record_decision(run_id, decision, reason, reviewer)` writes the human
decision via `WorkflowOrchestrator.record_human_decision` — **reviewer is required; the engine
never auto-approves**, and nothing new is stored.

## Reuse & no-duplication
Reuses P65 decision support, P90 council, P62 risk, and the existing `rwf_runs` audit — no new
ledger, no new engine.

## Validation
`test_integration_p86_95.py`: committee packet contains thesis/counter/risk/confidence/council/
decision_history; `is_decision=False`.

## Files
`jarvis/research_workflow/decision_center.py`, `console_api.py` (council-expanded + decision-memo),
`app/(console)/research-os/committee/page.tsx`, this doc.
