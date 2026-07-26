# Research Performance Tracking (P147)

> Integration only — measures research usefulness. Read-only, deterministic.

## What it does — `jarvis/research_workflow/research_outcome_tracker.py`
`ResearchOutcomeTracker.track(hypothesis, expected, actual, period)` → **Research Accuracy Report**
`{hypothesis, expected_outcome, actual_outcome, time_period, differences, accuracy, lesson}`.

Per-metric difference and direction match are computed deterministically; accuracy is the hit ratio, labelled
ACCURATE / PARTIAL / INACCURATE / PENDING. Example — *"AI semiconductor demand increases"* → later actual
market/company result → accuracy + a lesson. Historical context comes from `recall`.

## Reuse & no-duplication
Deterministic diff + recall (forward_testing/validation_gap pattern). No new store.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`.

## Validation
`test_integration_p141_150.py`: all report fields, accuracy label.

## Files
`jarvis/research_workflow/research_outcome_tracker.py`, this doc.
