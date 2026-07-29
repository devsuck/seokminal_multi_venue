# Research Critic Agent (P126)

> Integration only — upgrades the existing critic to challenge research. Analysis only, no auto-acceptance.

## What it does — `jarvis/research_workflow/research_reviewer.py`
`ResearchReviewer.review(spec, metrics)` → **Research Review** evaluating five required dimensions:

`bias · overfitting · missing evidence · weak assumptions · validation quality`

Built by composing:
- `ResearchCritic` (P75) — 8-dimension PASS/WARN/BLOCK critique (look-ahead, survivorship, leakage,
  overfitting, parameter instability, regime, liquidity, cost)
- `quality_monitor` (P106) — grade, weaknesses, missing validations
- `StrategyRiskReasoner` (P62) — main risk via the failure taxonomy

Verdict is `PASS / WARN / BLOCK`; a BLOCK requires human resolution (no automatic acceptance).

## Reuse & no-duplication
research_critic + quality_monitor + risk failure_reasoning + 9-way failure taxonomy. No new engine.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`.

## Validation
`test_integration_p121_130.py`: five dimensions present, blocks an overfit spec.

## Files
`jarvis/research_workflow/research_reviewer.py`, `console_api.py` (`/console/agent-workspace`), this doc.
