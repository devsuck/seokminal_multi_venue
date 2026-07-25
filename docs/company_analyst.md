# Company Analyst Agent (P124)

> Integration only — analyzes financial changes, earnings, business events, competitive position. Analysis only.

## What it does — `jarvis/research_workflow/company_analyst.py`
`CompanyAnalyst.memo(company, financials, headlines, transactions)` → **Company Research Memo**
`{fundamentals, earnings, business_events, competitive_position, insider_activity, historical_context}`.

Uses `fundamental_pipeline` (P115), `earnings_intelligence` (P100), `news_pipeline` (P114),
`insider_flow` (P98), `recall`.

## Reuse & no-duplication
Existing pipelines/adapters + recall. No new engine/memory.

## Governance
`is_advisory=True`, `is_decision=False`, `is_trade_signal=False`.

## Validation
`test_integration_p121_130.py`: memo type, earnings present, not a signal.

## Files
`jarvis/research_workflow/company_analyst.py`, `console_api.py` (`/console/agent-workspace`), this doc.
