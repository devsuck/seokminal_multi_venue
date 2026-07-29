# Market Data Pipeline (P113)

> Integration only — connects available market APIs into the Research OS. **Read-only, deterministic.**

## Flow
`Provider → Normalization → MarketEvent → event_intelligence → Research Workflow`

## What it does — `jarvis/research_workflow/market_pipeline.py`
`run(raw_bars, *, source)` maps raw market records (OHLCV/index/sector) into the `market_data_adapter.ingest`
path (P96), which normalizes to `MarketEvent`, routes through `event_stream.classify_event`, and produces a
human review queue. Supports **OHLCV · Volume · Volatility · Index · Sector**. `source`, `timestamp`, and raw
payload metadata are preserved (`raw_payload_metadata`).

Normalization is done by the existing adapter — the pipeline only shapes raw bars into metrics
(return from close/open, volume_ratio from volume/avg_volume) without distorting values.

## Reuse & no-duplication
`market_data_adapter.ingest` (P96) → `event_stream` → `MarketEventIntelligence` + `recall`. No new engine/store.

## Governance
`is_advisory=True`, `is_decision=False`. No trading/execution.

## Validation
`test_integration_p111_120.py`: metadata preservation, event classification, supported types, determinism.

## Files
`jarvis/research_workflow/market_pipeline.py`, `console_api.py` (`/console/live-intelligence`, `/console/research-feed`), this doc.
