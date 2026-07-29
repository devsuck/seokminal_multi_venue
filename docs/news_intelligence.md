# News Intelligence Layer (P97)

> Integration only — turns headlines/articles into **structured research events**.
> **Read-only, no separate news database, not a trade signal.**

## What it does — `jarvis/research_workflow/news_intelligence.py`
`analyze_headline(text, *, entity, assistant)` → Research Event
`{headline, event_type, origin, affected_companies, affected_sectors, relevance_score,
historical_similarity, related_research, impact_path}`.

Deterministic keyword classification →
`SUPPLY_CHAIN_CHANGE | EARNINGS_NEWS | MA_NEWS | REGULATORY | PRODUCT_NEWS | INSIDER_NEWS | GENERAL_NEWS`.

Affected companies/sectors come from the **existing** `MarketEventIntelligence`
(knowledge graph + supply chain relationship graph). Historical similarity + related research come
from `recall`. `relevance_score` = `HIGH/MEDIUM/LOW` from (#affected entities + recall hits).
`stream(headlines)` batches into a review queue.

## Reuse & no-duplication
Reuses `MarketEventIntelligence` (P60 graph) + `recall` (P44 memory). **No separate news
intelligence DB** — a headline becomes a research context object, nothing is stored.

## Governance
`is_advisory=True`, `is_decision=False`, `is_trade_signal=False`, `requires_human_review=True`.

## Validation
`test_integration_p96_100.py`: supply-chain classification + affected companies, earnings/regulatory
types, stream review queue, determinism, AST safety.

## Files
`jarvis/research_workflow/news_intelligence.py`, `console_api.py` (`/console/news-intel`), this doc.
