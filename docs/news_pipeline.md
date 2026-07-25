# News Research Pipeline (P114)

> Integration only — connects news sources into research context. **Read-only. No sentiment trading score.**

## Pipeline
`News API → News Intelligence → Event Classification → Research Context`

## What it does — `jarvis/research_workflow/news_pipeline.py`
`run(headlines, *, source)` reuses `news_intelligence.stream` (P97) and projects each event into a research
context extracting: **company · sector · event_type · importance · historical_similarity**. `importance` is
the relevance score (LOW/MEDIUM/HIGH) — deliberately **not** a sentiment trading score.

## Reuse & no-duplication
`news_intelligence.stream` (P97) → `MarketEventIntelligence` graph + `recall`. No separate news DB.

## Governance
`is_advisory=True`, `is_decision=False`, `is_trade_signal=False`.

## Validation
`test_integration_p111_120.py`: context extraction, no sentiment_score key, event classification.

## Files
`jarvis/research_workflow/news_pipeline.py`, `console_api.py` (`/console/live-intelligence`), this doc.
