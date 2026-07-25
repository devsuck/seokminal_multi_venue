# Agent Research Council + Market Event Intelligence (P59–P60)

> Governed by `docs/CONSTITUTION.md` and `docs/AGENTIC_RESEARCH_EVOLUTION.md`.
> **Integration over expansion** — reuses the existing 6 `perspectives()` lenses; NO new agents,
> NO new database.
> **Balanced memo, advisory only — human decides.** No trading / execution / broker / allocation.

## Part 1 — Research Council (P59–60)

Upgrades the existing multi-perspective system into a deliberating **council**:

```
Research question
   ↓  perspectives(topic)  ← reuses Quant / Risk / Macro / Supply / News / Critic (existing)
   ↓  (+ optional deterministic signals injected per lens, e.g. supply-chain risk)
Agreement / Conflict detection
   ↓
Balanced research memo + recommendation
```

`ResearchCouncilEngine(assistant=…).deliberate(question, signals=None) → CouncilMemo`:

- **Supportive** = lenses `SUPPORT`/`INFO`; **Cautionary** = `CAUTION`/`OPPOSE`.
- **Conflicts** = every (SUPPORT lens ↔ cautionary lens) pair — this is how the council
  *identifies disagreement* rather than averaging it away.
- **Recommendation** (deterministic):
  `CONFLICT — HUMAN REVIEW REQUIRED` · `CAUTION — prior failures` ·
  `PROCEED TO VALIDATION (human-gated)` · `INSUFFICIENT BASIS — hypothesis first`.
- **Signal injection**: other deterministic modules (e.g. Market Event Intelligence's
  supply-chain risk) can set/append a lens via `signals={lens:{stance,rationale}}` — so the
  Supply lens can carry "TSMC dependency risk" without inventing it inside the council.

Example (`"NVIDIA long thesis"`): Quant (momentum) supportive, Macro (liquidity) supportive,
Supply (TSMC dependency) cautionary, Risk (valuation) cautionary, Critic (confirmation bias)
cautionary → **conflict surfaced → human review**, emitted as a balanced memo. Memos may be
recorded as non-binding `ras_` advisory notes (reused ledger).

## Part 2 — Market Event Intelligence

Connects news / macro / supply-chain / company relationships into an **Event Impact Analysis**
that generates research candidates:

```
Event ("Taiwan earthquake")
   ↓ detect origin entity
Taiwan → TSMC → NVIDIA / AMD / Apple → SOXX / SMH (Semiconductor ETF)
   ↓ deterministic BFS over a static relationship graph
affected entities + impact chain (nodes/edges) + research candidates
```

`MarketEventIntelligence(relationships=None)`:
- `analyze_event(event, max_depth) → EventImpact{origin, affected_entities, impact_chain,
  candidates}` — propagates downstream through a small, **static, extensible reference graph**
  (not a ledger). Confidence falls with distance (direct=HIGH, 2-hop=MEDIUM, further=LOW).
- `generate_candidates(event)` → candidate dicts shaped exactly for the **Research Queue**
  (`{name, entity, reason, confidence}`), closing the loop: *event → candidate → queue → council*.
- `add_relationship(...)` extends the graph; `relationship_graph()` returns the graph view.

## The full vision, wired

```
Data → Research Memory (P53–P55)
     → Research Opportunities (P58 queue, fed by P60 events)
     → Multi-perspective Analysis (P59–60 council)
     → Experiment Design → Validation (P57) → Knowledge Growth
```

Every hop is advisory and human-gated; nothing in this bundle executes, trades, or allocates.

## Tests (34)

- Council (`test_council.py`, 13): 6 lenses present · **conflict detected → CONFLICT** ·
  balanced memo text · empty → INSUFFICIENT · signal injection overrides & adds a lens ·
  advisory · record note (non-binding) · deterministic · safety scans.
- Event intelligence (`test_event_intelligence.py`, 12): **Taiwan→TSMC→NVIDIA→ETF** ·
  chain edges · explicit origin · queue-shaped candidates · confidence by distance ·
  unknown event → no origin · graph extension · graph view · advisory · deterministic · safety.
- Integration (`research_ingestion/tests/test_p56_60_integration.py`, 3): discovery →
  human-approved import → recall · event → queue candidates · council synthesis.

## Files

`research_assistant/council.py` (new), `research_assistant/event_intelligence.py` (new),
`research_assistant/__init__.py` (exports), the three test files above, this doc.
