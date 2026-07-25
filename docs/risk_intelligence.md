# Risk Intelligence Layer (P62)

> Governed by `docs/CONSTITUTION.md`.
> **Integration over expansion** — added *inside* the existing `research_risk_intelligence`
> package; reuses the risk engine, the research_assistant failure taxonomy, and `rmi_` memory.
> NO new database. **Advisory only** — no trading / execution / capital allocation.

## Problem it fixes

Every strategy recommendation should answer **"What can make this fail?"** P62 adds a dedicated
risk-reasoning layer that turns metrics into failure scenarios and a strategy Risk Report.

## What it does — `jarvis/research_risk_intelligence/failure_reasoning.py`

`StrategyRiskReasoner` (deterministic):

### Failure scenarios — `failure_scenarios(strategy, metrics)`
Generates "what can make this fail" across the **six risk categories** —
**Market / Liquidity / Model / Data / Regime / Concentration** — each with a `scenario`,
`trigger` (the metric that drives it), and `severity`.

> Example — Momentum: (1) Sudden volatility expansion · (2) Market regime reversal ·
> (3) Crowded positioning · (4) Transaction-cost increase — plus Model & Data checks.

### Risk Report — `risk_report(strategy, metrics)`
`StrategyRiskReport{ strength, weakness, main_risk (+label), confidence, scenarios,
category_flags }`. Strategy type is inferred from the name (trend / mean-reversion / factor /
volatility / generic); the main risk is the profile's, promoted to any HIGH-severity category.
Confidence comes from validation completeness + Sharpe.

> Example — TSMOM: strength **Trend persistence**, weakness **Fast reversals**, main risk
> **Regime transition**, confidence per validation coverage.

### Memory — `record_risk_report(report, experiment_id, …)`
Persists the report as an `rmi_` lesson (reused), so `recall("<strategy>")` and the assistant
retrieve its risk profile later. No new store.

## Validation & safety

Append-only + hash-chained (`rmi_`); deterministic; advisory; no
`execute/trade/deploy/allocate/approve`; no broker/execution/live imports (AST-scanned).

## Tests (`research_risk_intelligence/tests/test_failure_reasoning.py`, 12)

six categories covered · momentum's 4 named scenarios · TSMOM report (trend / reversals /
REGIME) · high-cost promotes LIQUIDITY HIGH · incomplete metrics → LOW confidence · factor →
CONCENTRATION HIGH · **record → recall finds it** · advisory · deterministic · safety scans.

## Files

`research_risk_intelligence/failure_reasoning.py` (new; `StrategyRiskReport` named to avoid
collision with the package's existing `RiskReport`), `__init__.py` (exports),
`tests/test_failure_reasoning.py` (new), this doc. Existing risk engine unchanged.
