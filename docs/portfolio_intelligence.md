# Portfolio Intelligence Layer (P61)

> Governed by `docs/CONSTITUTION.md`.
> **Integration over expansion** — added *inside* the existing `portfolio_research` package;
> observations persist through the shared `rmi_` memory. NO new database, NO new package.
> **Decision support only.** No trading, no execution, no capital allocation — human decides.

## Problem it fixes

Research stopped at `Strategy → performance metrics`. P61 adds `Strategy → portfolio context →
risk impact`: how does a *new* idea change the portfolio it would join?

## What it does — `jarvis/portfolio_research/intelligence.py`

`PortfolioIntelligence` (deterministic; inputs are caller-supplied exposures/returns — not live data):

### Exposure analysis — `exposure_analysis(new_strategy, portfolio)`
For each dimension (**sector / asset / country / factor**) computes the post-inclusion exposure
`after = before·(1−w) + w·new` at intended weight `w`, the delta, and a **concentration flag**
(`after ≥ 40%` and rising). Adds **correlation exposure** (explicit or Pearson from returns →
HIGH/MEDIUM/LOW). Emits risk flags and a verdict.

> Example — *Semiconductor Momentum* at 20%: existing semiconductor 35% → **44%**, correlation
> **HIGH** → flag "Concentration increase", verdict "diversification limited, human review".

### Strategy combination analysis — `combination_analysis(strategies)`
Pairwise **correlation** (Pearson from returns, or a supplied matrix), **overlap** (Jaccard of
holdings), **drawdown similarity**, and **regime overlap** → a `diversification` verdict per pair
(`BENEFIT` < 0.3 corr · `REDUNDANT` ≥ 0.6 · `MODERATE`).

> Example — Momentum vs Value, correlation 0.1 → **BENEFIT** (potential diversification).

### Portfolio memory — `record_portfolio_impact(strategy, experiment_id, impact, …)`
Connects **Strategy → Experiment → Portfolio Effect → Lesson** by writing the observation as an
`rmi_` lesson (reused backbone), so `recall()` and the assistant surface it later. No new store.

## Validation & safety

Append-only + hash-chained (via `rmi_`); deterministic; advisory (`is_decision=False`,
`requires_human_review=True`); no `execute/trade/deploy/allocate/approve`; no
broker/execution/live imports (AST-scanned).

## Tests (`portfolio_research/tests/test_portfolio_intelligence.py`, 12)

concentration increase (semiconductor example) · low-correlation diversifies · combination
BENEFIT / REDUNDANT · Pearson from returns · **portfolio memory → recall finds it** · advisory ·
deterministic · forbidden-import/def/leak scans.

## Files

`portfolio_research/intelligence.py` (new), `portfolio_research/__init__.py` (exports),
`tests/test_portfolio_intelligence.py` (new), this doc. Existing `portfolio_research` engine
unchanged.
