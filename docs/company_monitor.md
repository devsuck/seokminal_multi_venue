# Company Monitoring System (P143)

> Integration only — continuously tracks research companies. **No buy/sell signal.** Read-only.

## What it does — `jarvis/research_workflow/company_monitor.py`
`CompanyMonitor.update(company)` → **CompanyUpdateReport**
`{company, events, impact, historical_context, research_priority}`.

Monitors financial changes, earnings events, news events, ownership changes, and industry events by reusing
the `CompanyAnalyst` (P124) — which composes `fundamental_pipeline`, `earnings_intelligence`, `news_pipeline`,
`ownership_pipeline`. Impact direction (POSITIVE/NEGATIVE/NEUTRAL) and a research priority (HIGH/MEDIUM/LOW)
are derived deterministically.

## Reuse & no-duplication
CompanyAnalyst + the P114–116 pipelines. No new store.

## Governance
`is_advisory=True`, `is_decision=False`, `is_trade_signal=False`.

## Validation
`test_integration_p141_150.py`: all report fields, priority, not a signal.

## Files
`jarvis/research_workflow/company_monitor.py`, `console_api.py` (`/console/company-monitor`), this doc.
