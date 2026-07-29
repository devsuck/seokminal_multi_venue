# Morning Market Briefing (P142)

> Integration only — generates the Daily Market Brief. Read-only, not a signal.

## What it does — `jarvis/research_workflow/morning_briefing.py`
`MorningBriefingGenerator.generate()` → **Daily Market Brief** with six sections:

1. Market Condition · 2. Current Regime · 3. Major Events · 4. Research Opportunities · 5. Risk Factors ·
6. Previous Lessons

Always includes **confidence, evidence, limitations**. Uses `market_cockpit` (market intelligence),
`regime`, `event_stream`, `opportunity_discovery`, and the knowledge brain (`semantic_recall` +
`knowledge_quality`) for previous lessons.

## Reuse & no-duplication
market_intelligence + regime + event_stream + knowledge brain. No new store.

## Governance
`is_advisory=True`, `is_decision=False`, `is_trade_signal=False`.

## Validation
`test_integration_p141_150.py`: six sections, confidence + limitations, not a signal.

## Files
`jarvis/research_workflow/morning_briefing.py`, `console_api.py` (`/console/morning-briefing`), this doc.
