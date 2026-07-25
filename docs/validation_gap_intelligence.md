# Validation Gap Intelligence (P104)

> Integration only — diagnoses the **backtest vs paper** gap across dimensions. Read-only, deterministic.

## What it does — `jarvis/research_workflow/validation_gap.py`
`analyze_gap(backtest, paper, *, spec=None, assistant=None)` → **Validation Intelligence Report** with
five gap dimensions:

`performance gap · risk gap · cost gap · regime gap · behavior gap`

Each is derived from existing engines and mapped to **possible causes** using the 9-way failure taxonomy
(`OVERFITTING, DATA_LEAKAGE, REGIME_CHANGE, COST_SENSITIVITY, LIQUIDITY, …`). Example finding:
*"Paper performance below expectation"* → possible causes: overfitting / regime change / underestimated cost.

## Reuse & no-duplication
- `forward_testing.analyze` (P94) — difference, slippage, cost error, regime mismatch, leakage
- `StrategyRiskReasoner` (P62) — risk gap via the failure taxonomy (MARKET/LIQUIDITY/MODEL/DATA/REGIME/CONCENTRATION)
- `research_assistant.recall` — historical similarity
- `classify_failure` (9-way taxonomy) — cause labelling

No new engine, no new store. Learning still flows to the existing `rmi_` ledgers.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`.

## Validation
`test_integration_p101_110.py`: five gap dimensions present, non-empty possible causes.

## Files
`jarvis/research_workflow/validation_gap.py`, `console_api.py` (`/console/validation-loop`), this doc.
