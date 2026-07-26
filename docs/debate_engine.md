# Structured Debate Engine (P162)

> Integration only — challenges research conclusions to improve quality. **Not prediction.** Read-only.

## What it does — `jarvis/research_workflow/debate_engine.py`
`build_debate(question, spec, metrics)` → **DebateReport**:
`{bull_case, bear_case, risk_case, alternative_explanation, missing_evidence, historical_counterexamples}`.

Reuses the Research Critic (`research_reviewer`, P126) for bear/risk cases, `semantic_recall` (P133) for the
bull case and evidence, and `conflict_detection` (P135) for historical counterexamples. The purpose is to
improve research quality by surfacing the opposing side — not to predict outcomes.

## Reuse & no-duplication
research_reviewer + semantic_recall + conflict_detection + knowledge_graph. No new store.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`.

## Validation
`test_integration_p161_170.py`: six debate cases present.

## Files
`jarvis/research_workflow/debate_engine.py`, `console_api.py` (`/console/debate`), this doc.
