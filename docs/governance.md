# Governance & Security (P168)

> Integration only — validates research governance. Read-only.

## What it does — `jarvis/research_workflow/governance.py`
`build_governance()` → **GovernanceReport** validating six checks:

`permissions · audit trail · append-only integrity · human checkpoints · architecture compliance · safety rules`

- **permissions** — `live_execution_enabled()` is False (research-only) + autonomy level
- **audit trail** — human decisions recorded through the existing `rwf_runs` audit
- **append-only integrity** — ledger count == 3, append-only hash chains
- **human checkpoints** — committee packet is `requires_human_review=True`, `is_decision=False`
- **architecture compliance / safety rules** — aggregates the existing per-layer safety scans
  (brain/agent/ops/intelligence/architecture)

Result: `COMPLIANT` or `REVIEW_REQUIRED`.

## Reuse & no-duplication
Existing validation framework (`*_safety`) + audit (`rwf_runs`) + config. No new store.

## Governance
`is_advisory=True`, `is_decision=False`.

## Validation
`test_integration_p161_170.py`: six checks, COMPLIANT.

## Files
`jarvis/research_workflow/governance.py`, `console_api.py` (`/console/governance`), this doc.
