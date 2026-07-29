# Decision Support Engine (P65)

> Governed by `docs/CONSTITUTION.md`.
> **Unifies existing outputs into one object.** No new intelligence, no new store.
> Read-only, deterministic, human-approved. **Jarvis organizes evidence; it does not decide.**

## Problem it fixes

Risk Report, Portfolio Report, Council Memo, Validation, and Paper Feedback were separate
outputs. P65 composes them into a single self-explaining **Decision Memo**.

## What it does — `jarvis/research_workflow/decision_support.py`

`DecisionSupportEngine.build_memo(question, …)` gathers evidence (read-only) from every
subsystem via the shared `_evidence.gather_evidence` and assembles a `DecisionMemo` with **all
required sections**:

| Section | Source |
|---|---|
| Question | the request |
| Evidence | digest + source list of the full bundle |
| Supporting / Counter Arguments | Council lenses (SUPPORT/INFO vs CAUTION/OPPOSE) |
| Historical Similar Cases | `recall()` hits over experiments/successes/failures/lessons |
| Portfolio Impact | `PortfolioIntelligence.exposure_analysis` (when context provided) |
| Risk Summary | `StrategyRiskReasoner.risk_report` (main risk, strength, weakness) |
| Confidence + Breakdown | deterministic aggregate over validation / council / risk / history / paper |
| Remaining Unknowns | missing validations, no-paper-confirmation, insufficient basis |
| Suggested Next Research | top `ResearchQueueEngine` proposals |
| Requires Human Review | always `True` |

**Every recommendation explains itself**: `recommendation` (from the council) + a `rationale`
string naming confidence, main risk, historical-case count, and unknowns. `is_decision=False`.

## Confidence (deterministic)

Scores validation completeness (+2), council consensus (+1) vs conflict, risk-report confidence
(+0/1/2), historical evidence (+1 at ≥3 hits), paper confirmation (+1), minus repeat-failure risk
→ HIGH / MEDIUM / LOW with a per-factor `confidence_breakdown`.

## Reuse & recording

Composes Council, recall, failure intelligence, Portfolio, Risk, Validation, Paper, and Queue —
no engine rebuilt. `record_memo(…)` optionally appends a **non-binding** advisory note to the
existing `ras_` ledger (human approval still required). No new store.

## Tests (`tests/test_decision_and_explain.py` — decision half, 6)

all required sections present · explains itself (rationale + confidence + breakdown) · historical
cases · supporting/counter arguments · record → non-binding note · deterministic.

## Files

`research_workflow/decision_support.py`, `_evidence.py` (shared), `tests/…`, this doc.
