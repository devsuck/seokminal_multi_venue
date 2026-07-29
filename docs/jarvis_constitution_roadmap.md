# Jarvis Constitution-aligned Roadmap (post P1–P45)

> Governed by `docs/CONSTITUTION.md` (takes precedence). Direction shift:
> **stop stacking new layers → consolidate, deepen memory, make the assistant central.**
> Grounded in `docs/maintainability_review.md` (144 packages, research_* ≈ 48% of LOC, heavy over-fragmentation).
> (Separate from the trading-research `docs/roadmap.md`, which is unrelated to the Jarvis package.)

## Alignment snapshot (Constitution vs current)

| Principle | Status |
|---|---|
| No execution / human decides | ✅ strong |
| Reproducible · auditable · lineage | ✅ strong (hash-chained ledgers) |
| Local-first | ✅ (P42 local runtime) |
| Simplicity / integration over expansion | ❌ violated (25 additive phases → 144 modules) |
| Memory = second brain | ❌ weak (scattered, empty ledgers) |
| Assistant as primary interface | ❌ weak (a panel, not conversational) |
| ~6 workspaces | ⚠️ partial (37 pages + 2 IAs) |

## Phases (in order)

**C0 — Governance gate.** Commit the Constitution. Extend `integration_audit` with a `gate` command:
fragmentation thresholds + the Constitution's 5 questions as a machine-checkable checklist. Prevents regrowth.

**C1 — Consolidation facades (non-destructive).** Thin read-only `jarvis/facades/` over the biggest
over-fragmented families: coordination (9→1), oversight (5→1), observability (3→1), self_improvement (4→1).
Underlying packages unchanged. One door instead of many.

**C2 — Memory backbone.** Extend `research_assistant` with `recall(topic)` — deterministic unified retrieval
across scattered knowledge ledgers. Makes "Have we tried momentum? Why did it fail?" actually work.

**C3 — Assistant becomes central.** Extend `research_assistant` with `ask(question)` (deterministic intent
routing) + read-only `/console/assistant` + a dashboard Assistant panel. Conversational entry point.

**C4 — Six workspaces.** Extend `research_navigation` to the Constitution IA
(Home/Research/Experiments/Knowledge/Assistant/System) + reflect in endpoint/page.

**C5 — Research loop.** `jarvis/research_loop/` — read-only model of the canonical workflow
(observation→hypothesis→proposal→**human approval**→execution→validation→report→knowledge→memory)
with an explicit, non-auto-passable approval gate, referencing existing ledgers.

## Non-negotiables (every phase)

- Additive / non-destructive; frozen system never deleted (facades, not removals).
- READ ONLY over existing ledgers; no execute/trade/deploy/allocate/approve.
- Deterministic · reproducible · hash-chained · tested. Human approval preserved.
- Prefer extending existing modules over new packages (Integration Before Expansion).
