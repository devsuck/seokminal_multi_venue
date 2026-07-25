# Real-Time Research Event Stream (P86)

> Integration only — converts incoming information into **research events**, not trade signals.
> Reuses event_intelligence + recall + knowledge graph. Read-only; no second event database.

## What it does — `jarvis/research_workflow/event_stream.py` + endpoint via market cockpit
`classify_event(event)` runs the flow: **Data Event → classification → affected asset/sector →
historical recall → research context → human review queue**. Sources: market data, news, economic
calendar, macro, insider, earnings, supply chain. `stream(events)` batches them and produces a
human-review queue.

- **Classification** — deterministic keyword mapping to NEWS/EARNINGS/INSIDER/MACRO/SUPPLY_CHAIN/…
- **Affected entities** — reuses `MarketEventIntelligence.analyze_event` (supply-chain propagation).
- **Historical recall** — reuses `recall(origin/entity)`.
- **Research context** — a one-line brief; every event `requires_human_review`.

## Reuse & no-duplication
No second event DB — events flow into review-queue objects. Reuses P60 event intelligence + P44
recall. Deterministic, read-only, `is_decision=False`.

## Validation
`test_integration_p86_95.py`: event classified + affected entities (TSMC), batch stream.

## Files
`jarvis/research_workflow/event_stream.py`, surfaced through the Market cockpit, this doc.
