# Market Analyst Agent (P123)

> Integration only — summarizes market condition, identifies relevant events, provides context. Analysis only.

## What it does — `jarvis/research_workflow/market_analyst.py`
`MarketAnalyst.memo(topic, events, market)` → **Market Research Memo**
`{market_condition (regime+labels), relevant_events, context, opportunities}`.

Uses `regime.detect_regime`, `market_cockpit.build_market_cockpit`, `event_stream.stream`,
`opportunity_discovery.discover`, `news_pipeline`.

## Reuse & no-duplication
market_intelligence + event_stream + regime. No new engine/memory.

## Governance
`is_advisory=True`, `is_decision=False`, `is_trade_signal=False`.

## Validation
`test_integration_p121_130.py`: memo type, regime present, not a signal.

## Files
`jarvis/research_workflow/market_analyst.py`, `console_api.py` (`/console/agent-workspace`), this doc.
