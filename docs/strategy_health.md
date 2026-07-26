# Strategy Health Monitoring (P144)

> Integration only — monitors existing researched strategies. Read-only, not a signal.

## What it does — `jarvis/research_workflow/strategy_health.py`
`StrategyHealthMonitor.report(strategy, metrics)` → **StrategyHealthReport**
`{strategy, health_score, warnings, historical_context, review_needed}`.

Analyzes performance/validation via `quality_monitor` (P106), lifecycle state via `strategy_lifecycle`
(P105), risk changes via `StrategyRiskReasoner` (P62), regime compatibility via `regime`, and historical
similarity via `recall`+`mistake_check`. The health score is the quality score minus a warning penalty;
`review_needed` is set when warnings exist or health is low. `board()` reports all known strategies.

## Reuse & no-duplication
quality_monitor + strategy_lifecycle + risk + regime + recall. No new store.

## Governance
`is_advisory=True`, `is_decision=False`.

## Validation
`test_integration_p141_150.py`: all report fields, numeric health score.

## Files
`jarvis/research_workflow/strategy_health.py`, `console_api.py` (`/console/strategy-health`), this doc.
