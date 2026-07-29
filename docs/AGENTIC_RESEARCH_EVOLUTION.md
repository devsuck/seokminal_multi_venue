# Jarvis Agentic Research Evolution Architecture

> Read before modifying Agent, Strategy, Research, Knowledge or Trading-related systems.
> Companion to `docs/CONSTITUTION.md` (which takes precedence). This document sets the agentic
> research direction; the Constitution sets the non-negotiable guardrails (no execution, human decides,
> integration over expansion).

## Mission

Jarvis is an **AI Quant Research Operating System** — a research engine (not a trading bot) that can:
generate hypotheses · create rule-based strategies · run simulations · analyze failures · identify root
causes · modify strategies · retest · store knowledge · **avoid repeating previous mistakes**. It should
behave like a quantitative research team.

## Agent capability

Agents operate on rule-based strategy generation and may modify parameters · filters · entry/exit
conditions · position rules · risk constraints. **Agents must NOT blindly optimize for returns.**

## Research loop (never skip failure analysis)

Observation → Hypothesis → Strategy Definition → Backtest → Validation → **Failure Analysis** →
Root Cause Classification → Strategy Revision → Out-of-Sample Testing → Knowledge Update.

## Failure intelligence

A failed strategy is valuable information. Every failed experiment must create structured knowledge:
Experiment ID · Hypothesis · Strategy Logic · Market Period · Performance · **Failure Type** ·
**Root Cause** · Lessons Learned · Related Experiments.

Failure categories: Overfitting · Data leakage · Regime change · Transaction cost sensitivity ·
Liquidity problem · Poor hypothesis · Timing issue · Risk concentration · Parameter instability.

Learn "**Why** did this fail?", not only "Did this fail?".

## Research memory graph

Connect: Market Event → Macro Condition → Company → Supply Chain → Strategy → Experiment → Outcome →
Knowledge. (e.g. Taiwan earthquake → semiconductor disruption → TSMC → NVIDIA → momentum strategy →
experiment result → future research memory.)

## Supply chain intelligence

Evolve Company→Company into Company → Supplier → Customer → Country → Commodity → Event → Market Impact,
and use the graph to generate research ideas.

## Agent collaboration

Specialized agents (Macro · Quant · News · Supply Chain · Risk · **Critic**) provide different
perspectives; a final conclusion should consider conflicting views.

## Strategy evaluation (never return-only)

Sharpe · Drawdown · Stability · Walk-forward · Out-of-sample · Transaction costs · Regime robustness ·
Parameter sensitivity · Random-baseline comparison.

## Do NOT prioritize

More news APIs · more chart features · more technical indicators. **The advantage comes from connecting
existing information into better research decisions — not collecting more.**

## Competitive advantage

Research speed · institutional memory · alternative-data combination · automated hypothesis generation ·
massive experiment capacity · **failure knowledge accumulation**. Every experiment should improve future
decisions.

---

## Implementation note (how this maps to the existing platform)

Per the Constitution ("Integration Before Expansion") and `docs/maintainability_review.md`, most of this
architecture **already exists** and must be integrated, not rebuilt:

| Doc requirement | Already in platform | Action |
|---|---|---|
| Research loop | `research_loop` (C5, human-approval gate) | integrate |
| Research memory retrieval | `research_assistant.recall()` (C2) | integrate |
| Knowledge / memory graph | `research_kg`, `knowledge`, `research_memory_intelligence` | integrate (facade later) |
| Supply chain graph | dashboard `/infra` (LKG), trading-repo supply graph | integrate |
| Agent collaboration | `agents`, `research_agent_coordination`, `research_council` (→ C1 `coordination` facade) | integrate, do NOT add 6 new agent modules |
| Strategy evaluation | `backtest_runner`, `research_validation`, validation modules | integrate |
| **Failure intelligence (9-category taxonomy + root cause + related)** | **GAP — only partial (OVERFITTING/REGIME in continuous_learning)** | **BUILD (as an extension, not a new module)** |

The genuine gap is **Failure Intelligence**: a canonical research-failure taxonomy with root-cause
classification that feeds `recall()` so the system can *avoid repeating mistakes*. Implemented by
extending `research_assistant` (which already reads the failure ledgers and owns recall) — no new module.
Everything else is integration of existing capabilities; building parallel versions would violate the
Constitution.
