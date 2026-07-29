# Market Regime Detection (P87)

> Integration only — classifies the market environment from indicators. Reuses existing regime
> detector (if configured), research memory, and strategy history. Deterministic, read-only.

## What it does — `jarvis/research_workflow/regime.py` + `/console/market-regime`
`detect_regime(indicators)` classifies into **Trend / Mean-Reversion / Risk-On / Risk-Off /
Inflation / Deflation / Liquidity Expansion / Liquidity Contraction / Volatility Shock**, with a
**confidence** score, **historical similar periods** (2008 / 2020Q1 / 2021 / 2022 / 2017
signatures), and **favorable / unfavorable strategies** (deterministic regime→strategy mapping),
plus strategies that historically **failed** in that regime (via `mistake_check`).

> Example — volatility 0.4 + liquidity − + risk-appetite − + inflation 0.05 → RISK_OFF +
> VOLATILITY_SHOCK + LIQUIDITY_CONTRACTION + INFLATION → matches **2008, 2022**; recommend
> defensive/quality, avoid high-beta momentum.

Without indicators it honestly returns **UNKNOWN**.

## Reuse & no-duplication
Reuses the existing `/console/regime` detector for indicators when available, recall for regime
failures; no new store, no market-data engine.

## Validation
`test_integration_p86_95.py`: label classification, historical matches (2008/2022), favorable/
unfavorable strategies, UNKNOWN without indicators.

## Files
`jarvis/research_workflow/regime.py`, `console_api.py` (market-regime), this doc.
