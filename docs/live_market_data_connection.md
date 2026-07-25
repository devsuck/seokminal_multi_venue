# Live Market Data Connection (P96)

> Integration only — an **adapter** that connects market data (KR/US/ETF/futures/crypto)
> into the existing Research OS event layer. **No trading, no signal.**
> Normalization and analysis are kept **separate**. Deterministic, read-only.

## Flow
`Market Data → Normalizer → MarketEvent → Event Intelligence → Research Context → Opportunity/Review Queue`

## What it does — `jarvis/research_workflow/market_data_adapter.py`
`normalize(raw, *, source)` turns one raw quote into a **MarketEvent**
`{source, asset, timestamp, event_type, metrics, confidence, related_entities}` —
**normalization only, no analysis**. Original `timestamp` and `source` are preserved verbatim.
Deterministic classification thresholds:

| Rule | event_type |
|---|---|
| volatility ≥ 0.4 | `VOLATILITY_SPIKE` |
| \|return\| ≥ 0.05 | `PRICE_SURGE` / `PRICE_DROP` |
| volume_ratio ≥ 2.0 | `VOLUME_SPIKE` |
| else | `MARKET_UPDATE` |

`to_research_event(mev, *, assistant)` hands the normalized event to the existing
`event_stream.classify_event` (P86) — which attaches affected entities, recall, and research
context. `ingest(raw_list, *, source, assistant)` batches this into a research-event stream
plus a human review queue.

## Reuse & no-duplication
Reuses `event_stream.classify_event` → `MarketEventIntelligence` + `recall`. **No new database** —
normalized MarketEvents flow into the existing event layer. The normalizer never analyzes; the
event intelligence never re-normalizes.

## Governance
Every payload `is_advisory=True`, `is_decision=False`; the review queue `requires_human_review=True`.
No `execute`/`trade`/broker imports.

## Validation
`test_integration_p96_100.py`: timestamp/source preservation, all event types, ingest→research
with human review, determinism, no-new-ledger (3), AST safety.

## Files
`jarvis/research_workflow/market_data_adapter.py`, `console_api.py` (`/console/market-intel-feed`), this doc.
