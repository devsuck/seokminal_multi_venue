# Portfolio Construction Simulator (P92)

> Integration only — decision-support simulation of strategy combinations. **No automatic
> allocation; the human decides.** Reuses Portfolio Intelligence + cross-strategy. Deterministic.

## What it does — `jarvis/research_workflow/portfolio_sim.py`
`simulate(strategies)` analyzes **correlation, overlap, drawdown interaction, risk concentration
(HHI), regime exposure**, and produces an **expected profile** — return profile, risk band,
combined drawdown, and **stress scenarios** (concentration, high-correlation, weak diversification).

- Correlation/overlap reuse `PortfolioIntelligence.combination_analysis` (P61).
- Risk concentration is the Herfindahl index of weights; combined drawdown is a correlation-
  adjusted approximation.

No auto-allocation, no trade — `is_decision=False`.

## Reuse & no-duplication
Reuses P61 portfolio intelligence + P83 cross-strategy; no new portfolio engine.

## Validation
`test_integration_p86_95.py`: HHI + risk band + stress scenarios; two-strategy minimum.

## Files
`jarvis/research_workflow/portfolio_sim.py`, this doc.
