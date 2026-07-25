# Continuous Learning (P82)

> When research finishes, existing memory is updated automatically — through existing write paths.
> **Reuses `research_memory_intelligence`; no new storage.**

## What it does — `jarvis/research_workflow/continuous_learning.py`
`on_research_complete(backtest, portfolio, paper, commit)` orchestrates the existing write
engines so a finished research updates every channel at once:
- **Lessons / Failures / Successes** — `research_ingestion.ingest` (P53),
- **Risk** — `StrategyRiskReasoner.record_risk_report` → rmi_ lesson (P62),
- **Portfolio Effects** — `PortfolioIntelligence.record_portfolio_impact` (P61),
- **Paper Feedback** — `PaperTradingFeedback.record_feedback` (P63).

Because all writes land in `rmi_`, the **Recall Index, Knowledge Graph, and Priority** update
transparently. `learning_status()` reports per-channel accumulation (read-only).

## Reuse & no-duplication
Every write reuses an existing engine/ledger — no new storage, no new memory system. This module
is pure orchestration of already-permitted writes.

## Validation
`test_integration_p78_85.py`: `on_research_complete` touches ingestion+risk channels and writes
`rmi_` lessons; `learning_status` counts channels. `/console/continuous-learning` shape test.

## Files
`jarvis/research_workflow/continuous_learning.py`, `console_api.py`, this doc.
