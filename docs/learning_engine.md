# Institutional Learning Engine (P136)

> Integration only — converts research outcomes into organizational lessons, stored via existing memory paths.

## What it does — `jarvis/research_workflow/learning_engine.py`
`ResearchLearningEngine.learn(backtest, paper, outcome)` → a structured **Lesson**:
`{what_happened, why, when_applicable, when_invalid}`.

The *why* comes from `validation_gap`/`forward_testing` (when paper is present); *when_invalid* from
`StrategyRiskReasoner` (main risk label / regime). The lesson is serialized and stored through the existing
`ResearchMemoryIntelligenceEngine.record_lesson` (rmi_lessons) — `commit=False` = preview. **No new store.**

## Reuse & no-duplication
`record_lesson` (rmi_) + validation_gap/forward_testing + risk reasoner. No new store.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`.

## Validation
`test_integration_p131_140.py`: four-part lesson structure, stored to rmi_lessons, preview by default.

## Files
`jarvis/research_workflow/learning_engine.py`, this doc.
