# Research Report Automation (P145)

> Integration only — upgrades ResearchWriter into automated reports. Summary/explanation only, no recommendation.

## What it does — `jarvis/research_workflow/report_automation.py`
`ReportAutomation.generate(report_type, question, …)` produces a standard **8-section** report:

1. Research Question · 2. Summary · 3. Evidence · 4. Historical Context · 5. Risk · 6. Contradictions ·
7. Conclusion · 8. Next Research Step

Always includes **confidence** and **limitations**. Report types: daily_report, weekly_letter,
strategy_review, company_report. Built by reusing `ResearchWriter` (P127, 7-section) and adding a Summary and
a Contradictions section (from `conflict_detection`, P135).

## Reuse & no-duplication
ResearchWriter + semantic_recall + conflict_detection. No new store.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`. No investment recommendation.

## Validation
`test_integration_p141_150.py`: exactly 8 sections including contradictions, confidence + limitations.

## Files
`jarvis/research_workflow/report_automation.py`, `console_api.py` (`/console/research-organization`), this doc.
