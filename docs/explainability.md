# Explainability Layer (P67)

> Governed by `docs/CONSTITUTION.md`.
> **Nothing appears as a black-box decision.** No new intelligence, no new store — read-only
> synthesis over existing evidence. Deterministic, human-approved.

## Problem it fixes

Conclusions must be auditable. P67 attaches an evidence chain to every conclusion so a human can
see exactly why it was reached — and why it might be wrong.

## What it does — `jarvis/research_workflow/explainability.py`

`ExplainabilityEngine.evidence_chain(topic, …)` gathers evidence (read-only) and connects the
fixed pipeline:

```
Experiment → Validation → Failure Lessons → Historical Memory →
Council Opinions → Portfolio Analysis → Risk Analysis → Final Recommendation
```

Each node carries a concrete summary and real record references. The result (`EvidenceChain`)
provides:

- **Evidence chain** — 8 ordered nodes + edges, each labeled from actual data.
- **`references_experiments`** — real experiment/run ids pulled from `recall()`, so the chain
  points at historical experiments (not a black box).
- **Confidence + breakdown** — the same deterministic aggregate as the Decision Memo.
- **Why this conclusion** — what the recommendation follows from.
- **Why it may be wrong** — counter-perspective rationales + primary risk + past failures on the
  topic.
- **Alternative interpretations** — from council conflicts (support ↔ caution pairs).
- **Missing evidence** — incomplete validations, no paper confirmation, no precedent.

`is_decision=False`, `requires_human_review=True`.

## Reuse & no-duplication

Reuses `recall`, failure intelligence, Council, Portfolio, Risk, and Validation through the shared
`_evidence.gather_evidence`. Writes nothing — pure read-only synthesis.

## Tests (`tests/test_decision_and_explain.py` — explainability half, 5)

**references historical experiments (`momentum study`)** · full 8-stage pipeline + edges · explains
all (why / why-may-be-wrong / alternatives / missing / breakdown) · not a black box (advisory,
human review) · incomplete backtest surfaces missing validation.

## The vision, realized

Together P64–P67 turn Jarvis from a collection of tools into a **research operating system**: it
orchestrates the subsystems, unifies their outputs into a self-explaining Decision Memo, preserves
research across sessions, and makes every conclusion traceable — while the human keeps every
decision.

## Files

`research_workflow/explainability.py`, `_evidence.py` (shared), `tests/…`, this doc.
