# Research Queue Engine (P58)

> Governed by `docs/CONSTITUTION.md` and `docs/AGENTIC_RESEARCH_EVOLUTION.md`.
> **Integration over expansion** — reuses `ResearchAssistantEngine` (READ ONLY over the
> existing ledgers); NO new database.
> **Jarvis proposes; humans decide.** Every proposal requires human approval before anything runs.
> No trading / execution / broker / capital allocation.

## Problem it fixes

Until now a human had to *ask* the research question. P58 lets Jarvis **propose what to research
next**, deterministically, from what it already remembers — turning accumulated memory into a
prioritized Research Opportunity Queue.

## Inputs → candidates (deterministic)

`ResearchQueueEngine(assistant=…).generate(regime, events, limit)` builds proposals from:

| Source | Candidate kind | Logic |
|---|---|---|
| **Unexplored combinations** | `COMBINATION` | atomic signals extracted from experiment names/notes; pairs that were each tested *individually* but **never together** → propose the combo (e.g. "Insider + Supply Chain Momentum") |
| **Previous failures** | `FAILURE_FIX` | top failure categories (`failure_intelligence`) → propose a robustness study targeting that weakness |
| **Market regime** | `REGIME` | when a regime is supplied → propose a regime-fit re-evaluation |
| **Recent events** | `EVENT` | event-impact candidates (from Market Event Intelligence) → propose event-linked studies |

Each `ResearchProposal` = `{ name, kind, reason, confidence (LOW/MEDIUM/HIGH),
expected_value (LOW/MEDIUM/HIGH), basis[], requires_human_approval=True }`. The queue is ranked
by expected value then confidence, deduplicated by deterministic `proposal_id`.

## Example

```
Research Proposal: Insider + Supply Chain Momentum
Reason:            individual signals 'insider'·'supply' tested; combination unexplored
Confidence:       MEDIUM      Expected Value: HIGH
Requires human approval: yes
```

## Human gate & recording

Proposals are advisory (`is_decision=False`). `record_proposals(queue, commit=True)` appends
them as **non-binding advisory notes** to the existing `ras_` ledger (reused — no new store),
each `is_binding=False`, `requires_human_review=True`. Nothing executes.

## Tests (`research_assistant/tests/test_research_queue.py`, 14)

generates candidates · unexplored-combination present · failure-driven (HIGH at ≥3 fails) ·
event-driven · regime-driven · all advisory + human-approval · deterministic · record →
non-binding `ras_` notes · empty memory → 0 (no crash) · forbidden-import/def/leak + no
execution methods.

## Files

`research_assistant/research_queue.py` (new), `research_assistant/__init__.py` (exports),
`tests/test_research_queue.py` (new), this doc.
