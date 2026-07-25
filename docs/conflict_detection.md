# Knowledge Conflict Detection (P135)

> Integration only — finds contradicting conclusions. Read-only, deterministic.

## What it does — `jarvis/research_workflow/conflict_detection.py`
`detect_conflicts(topic)` compares `rmi_successes` vs `rmi_failures` for the same origin/topic and emits a
**Conflict Report** per contradiction (e.g. Study A: momentum WORKED vs Study B: momentum FAILED):
`{period, market_regime {a,b}, method_difference {a,b}, possible_explanation}`.

Period/regime/method hints are extracted deterministically from the record text; the explanation prefers a
regime or method difference (conditional conclusion) before falling back to sample/period/cost differences.

## Reuse & no-duplication
`rmi_successes` / `rmi_failures`. No new store.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`.

## Validation
`test_integration_p131_140.py`: report shape, checked counts.

## Files
`jarvis/research_workflow/conflict_detection.py`, `console_api.py` (`/console/knowledge-conflicts`), this doc.
