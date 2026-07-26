# Investment Committee Workflow (P161)

> Integration only — an institutional research review process. **Never outputs BUY/SELL/EXECUTE/ALLOCATE.** Read-only.

## Workflow
`Research Report → Evidence Review → Risk Review → Opposing View → Committee Summary → Human Decision`

## What it does — `jarvis/research_workflow/investment_committee.py`
`build_committee_packet(question)` → **CommitteePacket**
`{research_summary, supporting_evidence, risk_summary, alternative_views, confidence, limitations,
questions_for_human, requires_human_review=True}`.

Reuses `decision_center.committee_packet` (P65/P93 — thesis/evidence/counter/risk/council/history) and
`debate_engine` (P162 — the opposing view / bull-bear-risk cases). The final "Human Decision" stage is left
for a person; the engine records decisions only through `decision_center.record_decision` (reviewer required).

## Reuse & no-duplication
decision_center + debate_engine + report_automation. No new store.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`. Never BUY/SELL/EXECUTE/ALLOCATE.

## Validation
`test_integration_p161_170.py`: all packet fields, no buy/sell output, human decision required.

## Files
`jarvis/research_workflow/investment_committee.py`, `console_api.py` (`/console/committee-packet`), this doc.
