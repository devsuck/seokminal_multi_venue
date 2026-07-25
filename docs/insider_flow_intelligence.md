# Insider & Institutional Flow Intelligence (P98)

> Integration only — insider/institutional flow becomes a **research trigger**.
> **This is not a buy signal. It is a research trigger only.** Read-only, deterministic.

## Flow
`Transaction → Insider Event → Historical Context → Research Opportunity`
Sources: DART · SEC Form 4 · 13F · institutional holdings.

## What it does — `jarvis/research_workflow/insider_flow.py`
`analyze_transaction(txn, *, assistant)` → **InsiderEvent**
`{entity, transaction_type, size, source, historical_comparison, confidence, related_research}`.

Deterministic conviction logic:
- `BUY` + `prior_return < 0` + (role ∈ CEO/CFO/chairman **or** cluster ≥ 3 insiders) → `CONVICTION_BUY`
- clustered `BUY` → `CLUSTER_BUY`
- confidence `HIGH` on conviction, `MEDIUM` on cluster or size ≥ 1e6, else `LOW`.

Example: *drop, then CEO buys, sector undervalued, similar to a past setup* = an Insider Conviction
**research** event — a reason to investigate, never an instruction to act. Historical comparison via
`recall`. `stream(txns)` batches into a research-trigger queue.

## Reuse & no-duplication
Reuses `recall` (past setups) + event/opportunity framing. No new ledger, no new store.

## Governance
`is_research_trigger=True`, `is_trade_signal=False`, `is_advisory=True`, `is_decision=False`,
`requires_human_review=True`.

## Validation
`test_integration_p96_100.py`: CONVICTION_BUY + HIGH confidence + trade_signal False, CLUSTER_BUY,
stream triggers, AST safety.

## Files
`jarvis/research_workflow/insider_flow.py`, `console_api.py` (`/console/market-intel-feed`), this doc.
