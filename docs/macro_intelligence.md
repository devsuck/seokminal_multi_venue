# Macro Intelligence Layer (P153)

> Integration only — connects the macro environment with research context. **No forecasting engine.** Read-only.

## What it does — `jarvis/research_workflow/macro_intelligence.py`
`build_macro_context(indicators)` → **MacroContextReport**
`{macro_state, indicators, historical_similarity, affected_assets, uncertainty}`.

Classifies interest rates, inflation, employment, and liquidity into states, derives an economic-cycle label
(TIGHTENING / EASING-RECESSION_RISK / MID_CYCLE / UNKNOWN), maps deterministically to affected assets, and
recalls historical similarity. Reuses the FRED/ECOS providers (catalog), `regime` detection, and
`event_stream`. It describes the current environment — **it does not forecast**.

## Reuse & no-duplication
FRED/ECOS providers + regime + event_stream + recall. No new store, no forecasting engine.

## Governance
`is_advisory=True`, `is_decision=False`.

## Validation
`test_integration_p151_160.py`: all report fields, valid macro state, no forecast, determinism.

## Files
`jarvis/research_workflow/macro_intelligence.py`, `console_api.py` (`/console/macro-intelligence`), this doc.
