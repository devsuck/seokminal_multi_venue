# Full System Validation (P169)

> Validation of the complete lifecycle. Read-only, deterministic, no execution.

## The lifecycle
`External Data → Research Context → Agents → Experiment → Validation → Knowledge → Committee → Human Review → Institutional Memory`

## What it verifies — `jarvis/research_workflow/system_validation.py`
`validate_system()` runs seven checks:
1. **workflow_complete** — all per-layer validations pass (P120/130/140/150/160)
2. **committee_works** — a CommitteePacket is produced requiring human decision
3. **governance_passes** — governance is COMPLIANT (P168)
4. **monitoring_healthy** — production severity is not CRITICAL (P166)
5. **metrics_generated** — operational metrics assemble (P167)
6. **dashboard_integrated** — console surfaces + committee page
7. **no_duplicated_architecture** — ledger stays 3 and governance passes

## Result
All seven checks pass.

## Validation
`test_integration_p161_170.py`: seven checks.

## Files
`jarvis/research_workflow/system_validation.py`, `console_api.py` (`/console/system-validation`), this doc.
