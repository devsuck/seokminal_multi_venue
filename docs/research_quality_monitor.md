# Research Quality System (P106)

> Integration only — monitors research quality to **prevent weak research accumulation.** Read-only, deterministic.

## What it does — `jarvis/research_workflow/quality_monitor.py`
`ResearchQualityMonitor.evaluate(backtest)` produces a **Quality Score** and evaluates six core dimensions:

`sample size · out-of-sample · walk-forward · cost sensitivity · parameter stability · reproducibility`

It reuses `quality_score.score_research` (P84) — which itself reuses `research_ingestion.validate_backtest`
and `recall` — for the weighted 0–100 score, grade, and missing validations, then adds sample-size scoring
and a **weak-research gate**:

- `gate = ACCEPT` when score ≥ 65 and validation is complete
- `gate = NEEDS_MORE_EVIDENCE` otherwise, with `weaknesses` (dimensions < 0.5) listed

This is how weak research is stopped from accumulating: it is flagged, not stored as accepted.

## Reuse & no-duplication
`quality_score.score_research` (P84) + `validate_backtest`. No new store, no execution.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`.

## Validation
`test_integration_p101_110.py`: six core dimensions present, gate value, deterministic score.

## Files
`jarvis/research_workflow/quality_monitor.py`, `console_api.py` (`/console/validation-loop`), this doc.
