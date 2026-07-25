# Forward Testing Intelligence (P94)

> Integration only — upgrades paper-trading feedback. Compares backtest expectation vs paper
> reality and feeds learning into existing memory. Reuses the paper feedback system + critic.

## What it does — `jarvis/research_workflow/forward_testing.py`
`analyze(backtest, paper)` reuses `PaperTradingFeedback.compare` (P63) and adds:
**performance difference, slippage, cost-assumption errors, regime mismatch, data-leakage
suspicion**, producing a structured **learning feedback** string. `record_learning(...)` persists
via the existing paper-feedback path (`rmi_`), so the lesson flows into recall / knowledge graph /
priority — future research improvement, no new store.

> Example — expected 15% / paper 3% with higher realized cost → cost-assumption error +
> data-leakage suspicion → learning lesson recorded.

## Reuse & no-duplication
Reuses P63 paper feedback + P75 critic thresholds; no new store, no new engine.

## Validation
`test_integration_p86_95.py`: cost error + leakage detection + findings + learning feedback.

## Files
`jarvis/research_workflow/forward_testing.py`, this doc.
