# Research Critic (P75)

> Orchestration over expansion — inside `research_workflow`. Deterministic. **No automatic
> acceptance.** Advisory; the human decides. Reuses the failure taxonomy and risk heuristics.

## What it does — `research_critic.py`

Before any experiment is considered valuable, `critique(spec, metrics)` evaluates **eight
dimensions** and produces structured criticism with evidence:

| Dimension | Trigger (deterministic) |
|---|---|
| look_ahead | a feature name references the future (`forward`/`future`/`next_`/…) → **BLOCK** |
| survivorship | universe not marked point-in-time → WARN |
| data_leakage | label window overlaps a feature → WARN |
| overfitting | `sharpe − out_of_sample ≥ 0.5` → **BLOCK**; weak walk-forward → WARN |
| parameter_instability | `parameter_stability ≤ 0.3` → **BLOCK**; ≤ 0.5 → WARN |
| regime_dependence | `regime_dependent` or weak walk-forward → WARN |
| liquidity | high turnover / weekly-daily rebalance → WARN |
| cost_sensitivity | `cost_impact ≥ 0.3` → **BLOCK**; ≥ 0.15 → WARN |

Each `Critique` carries `severity` (PASS/WARN/BLOCK), a `finding`, and the `evidence` (the metric
or spec field that fired it). The report's **verdict** is BLOCK if any dimension blocks — so weak
research is blocked, exactly as required. Thresholds mirror `research_ingestion.auto_classify_
failure` / `StrategyRiskReasoner`, so the critic is consistent with the rest of the system.

**No auto-accept**: even a PASS verdict sets `requires_human_review=True`, `is_decision=False`.

## Reuse analysis

Reuses the metric thresholds and failure taxonomy already established in P53/P62. Adds the three
bias checks (look-ahead / survivorship / leakage) that operate on the plan's metadata. No new
engine, no new ledger.

## Validation

`tests/test_critic_prioritizer_loop.py`: 8 dimensions covered, **blocks weak research**, look-ahead
BLOCK on future features, no-auto-acceptance, determinism.

## Remaining gaps

- Survivorship/leakage checks are metadata-based (they flag "verify"), not data-level audits.
- Requires the spec/metrics as input; it does not itself fetch point-in-time data.

## Files

`research_workflow/research_critic.py`, tests, this doc. Surfaced via `/console/autonomous-runtime`.
